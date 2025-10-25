from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count
from typing import Any, Callable, Dict, Iterable, List, Optional

try:  # pragma: no cover - optional dependency
    from alpaca_trade_api.rest import APIError  # type: ignore
except Exception:  # pragma: no cover - fallback when library missing
    APIError = None  # type: ignore

try:  # pragma: no cover - optional dependency
    import requests
except Exception:  # pragma: no cover - optional dependency
    requests = None  # type: ignore

from .common import (
    AdapterError,
    FatalAdapterError,
    IdempotentCache,
    RateLimiter,
    RetryConfig,
    RetryableError,
    retry,
)


def _classify_alpaca_error(exc: BaseException) -> BaseException:
    if isinstance(exc, (RetryableError, FatalAdapterError)):
        return exc
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return RetryableError(str(exc))
    if requests is not None and isinstance(  # type: ignore[attr-defined]
        exc, requests.exceptions.RequestException
    ):
        return RetryableError(str(exc))
    if APIError is not None and isinstance(exc, APIError):  # type: ignore[arg-type]
        status = getattr(exc, "status_code", None)
        if status in {429} or (status is not None and status >= 500):
            return RetryableError(str(exc))
        return FatalAdapterError(str(exc))
    return FatalAdapterError(str(exc))


def _order_to_dict(order: Any) -> Dict[str, Any]:
    if isinstance(order, dict):
        return dict(order)
    if hasattr(order, "_raw"):
        return dict(order._raw)  # type: ignore[attr-defined]
    if hasattr(order, "__dict__"):
        return dict(vars(order))
    return {"id": getattr(order, "id", None)}


@dataclass
class AlpacaAdapter:
    client: Any
    retry_config: RetryConfig = field(default_factory=RetryConfig)
    rate_limiter: RateLimiter = field(
        default_factory=lambda: RateLimiter(max_calls=180, period=60.0)
    )
    sleeper: Callable[[float], None] = field(default=lambda _: None)

    def __post_init__(self) -> None:
        self._cache = IdempotentCache()
        self._seq = count(1)
        self._logs: List[Dict[str, Any]] = []

    def _log(self, action: str, payload: Dict[str, Any], response: Dict[str, Any]) -> None:
        self._logs.append({"action": action, "payload": payload, "response": response})

    @property
    def audit_log(self) -> List[Dict[str, Any]]:
        return list(self._logs)

    def _classify(self, exc: BaseException) -> BaseException:
        return _classify_alpaca_error(exc)

    def _ensure_rate_limit(self) -> None:
        self.rate_limiter.acquire()

    def _next_client_id(self) -> str:
        return f"alpaca-{next(self._seq):06d}"

    def submit_order(
        self,
        *,
        symbol: str,
        qty: float,
        side: str,
        order_type: str,
        time_in_force: str = "gtc",
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        client_id: Optional[str] = None,
        extended_hours: Optional[bool] = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        cid = client_id or self._next_client_id()
        order_kwargs: Dict[str, Any] = {
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "type": order_type,
            "time_in_force": time_in_force,
            "client_order_id": cid,
        }
        if limit_price is not None:
            order_kwargs["limit_price"] = limit_price
        if stop_price is not None:
            order_kwargs["stop_price"] = stop_price
        if extended_hours is not None:
            order_kwargs["extended_hours"] = extended_hours
        if extra:
            for key, value in sorted(extra.items()):
                order_kwargs[key] = value

        def resolver() -> Dict[str, Any]:
            self._ensure_rate_limit()

            def op() -> Dict[str, Any]:
                return _order_to_dict(self.client.submit_order(**order_kwargs))

            return retry(
                op,
                retry_config=self.retry_config,
                classify=self._classify,
                sleeper=self.sleeper,
            )

        response = self._cache.remember(cid, order_kwargs, resolver)
        response.setdefault("client_order_id", cid)
        self._log("submit_order", order_kwargs, response)
        return response

    def cancel_order(self, client_id: str) -> Dict[str, Any]:
        cached = self._cache.get(client_id)
        if cached is None:
            raise FatalAdapterError(f"Unknown client id {client_id}")

        def op() -> Dict[str, Any]:
            self._ensure_rate_limit()
            self.client.cancel_order_by_client_order_id(client_id)
            return {"client_order_id": client_id, "status": "canceled"}

        response = retry(
            op,
            retry_config=self.retry_config,
            classify=self._classify,
            sleeper=self.sleeper,
        )
        self._cache.update(client_id, response)
        self._log("cancel_order", {"client_id": client_id}, response)
        return response

    def reconcile(self) -> Dict[str, Iterable[str]]:
        def op() -> List[Dict[str, Any]]:
            self._ensure_rate_limit()
            return [_order_to_dict(order) for order in self.client.list_orders(status="open")]

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
            order.get("client_order_id") or order.get("clientOrderId") or order.get("id")
            for order in orders
        }
        local_ids = set(self._cache.keys())
        missing_remote = sorted(local_ids - set(filter(None, remote_ids)))
        untracked_remote = sorted(
            cid for cid in remote_ids if cid and cid not in local_ids
        )
        report = {
            "missing_remote": missing_remote,
            "untracked_remote": untracked_remote,
        }
        self._log("reconcile", {}, report)
        return report
