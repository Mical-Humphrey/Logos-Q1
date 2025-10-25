from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count
from typing import Any, Callable, Dict, List, Optional

try:  # pragma: no cover - optional dependency
    from oandapyV20.exceptions import V20Error  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    V20Error = None  # type: ignore

try:  # pragma: no cover - optional dependency
    import requests
except Exception:  # pragma: no cover - optional dependency
    requests = None  # type: ignore

from .common import (
    AdapterError,
    FatalAdapterError,
    IdempotentCache,
    OrderConflictError,
    RateLimiter,
    RetryConfig,
    RetryableError,
    retry,
)


def _classify_oanda_error(exc: BaseException) -> BaseException:
    if isinstance(exc, (RetryableError, FatalAdapterError)):
        return exc
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return RetryableError(str(exc))
    if requests is not None and isinstance(  # type: ignore[attr-defined]
        exc, requests.exceptions.RequestException
    ):
        return RetryableError(str(exc))
    if V20Error is not None and isinstance(exc, V20Error):  # type: ignore[arg-type]
        status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        if status in {"RATE_LIMIT"}:
            return RetryableError(str(exc))
        if isinstance(status, int) and status >= 500:
            return RetryableError(str(exc))
        return FatalAdapterError(str(exc))
    return FatalAdapterError(str(exc))


def _ensure_payload_units(side: str, units: float) -> float:
    signed = abs(units)
    if side.lower() == "buy":
        return signed
    if side.lower() == "sell":
        return -signed
    raise OrderConflictError(f"Unsupported side '{side}'")


@dataclass
class OandaAdapter:
    client: Any
    account_id: str
    retry_config: RetryConfig = field(default_factory=RetryConfig)
    rate_limiter: RateLimiter = field(
        default_factory=lambda: RateLimiter(max_calls=120, period=60.0)
    )
    sleeper: Callable[[float], None] = field(default=lambda _: None)

    def __post_init__(self) -> None:
        self._cache = IdempotentCache()
        self._seq = count(1)
        self._logs: List[Dict[str, Any]] = []

    def _log(
        self, action: str, payload: Dict[str, Any], response: Dict[str, Any]
    ) -> None:
        self._logs.append({"action": action, "payload": payload, "response": response})

    @property
    def audit_log(self) -> List[Dict[str, Any]]:
        return list(self._logs)

    def _classify(self, exc: BaseException) -> BaseException:
        return _classify_oanda_error(exc)

    def _ensure_rate_limit(self) -> None:
        self.rate_limiter.acquire()

    def _next_client_id(self) -> str:
        return f"oanda-{next(self._seq):06d}"

    def submit_order(
        self,
        *,
        instrument: str,
        units: float,
        side: str,
        order_type: str,
        price: Optional[float] = None,
        client_id: Optional[str] = None,
        time_in_force: str = "FOK",
        position_fill: str = "DEFAULT",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        cid = client_id or self._next_client_id()
        signed_units = _ensure_payload_units(side, units)
        order_payload: Dict[str, Any] = {
            "instrument": instrument,
            "units": signed_units,
            "type": order_type.upper(),
            "timeInForce": time_in_force.upper(),
            "positionFill": position_fill,
            "clientExtensions": {"id": cid},
        }
        if price is not None:
            order_payload["price"] = price
        if extra:
            for key, value in sorted(extra.items()):
                order_payload[key] = value

        request_payload = {"order": order_payload}

        def resolver() -> Dict[str, Any]:
            self._ensure_rate_limit()

            def op() -> Dict[str, Any]:
                return dict(
                    self.client.create_order(self.account_id, request_payload)  # type: ignore[attr-defined]
                )

            return retry(
                op,
                retry_config=self.retry_config,
                classify=self._classify,
                sleeper=self.sleeper,
            )

        response = self._cache.remember(cid, request_payload, resolver)
        response.setdefault("clientExtensions", {}).setdefault("id", cid)
        self._log("submit_order", request_payload, response)
        return response

    def cancel_order(self, client_id: str) -> Dict[str, Any]:
        cached = self._cache.get(client_id)
        if cached is None:
            raise FatalAdapterError(f"Unknown client id {client_id}")
        order_id = (
            cached.get("id")
            or cached.get("orderId")
            or cached.get("order", {}).get("id")
        )
        if not order_id:
            raise FatalAdapterError("Unable to determine exchange order id for cancel")

        def op() -> Dict[str, Any]:
            self._ensure_rate_limit()
            return dict(self.client.cancel_order(self.account_id, order_id))

        response = retry(
            op,
            retry_config=self.retry_config,
            classify=self._classify,
            sleeper=self.sleeper,
        )
        response.setdefault("client_id", client_id)
        self._cache.update(client_id, response)
        self._log(
            "cancel_order", {"client_id": client_id, "order_id": order_id}, response
        )
        return response

    def reconcile(self) -> Dict[str, List[str]]:
        def op() -> List[Dict[str, Any]]:
            self._ensure_rate_limit()
            pending = self.client.list_pending_orders(self.account_id)
            return [dict(order) for order in pending]

        try:
            orders = retry(
                op,
                retry_config=self.retry_config,
                classify=self._classify,
                sleeper=self.sleeper,
            )
        except AdapterError:
            orders = []
        remote_ids = {
            order.get("clientExtensions", {}).get("id") or order.get("id")
            for order in orders
        }
        local_ids = set(self._cache.keys())
        missing_remote = sorted(local_ids - set(filter(None, remote_ids)))
        untracked_remote = sorted(
            cid for cid in remote_ids if cid and cid not in local_ids
        )
        report: Dict[str, List[str]] = {
            "missing_remote": missing_remote,
            "untracked_remote": untracked_remote,
        }
        self._log("reconcile", {}, report)
        return report
