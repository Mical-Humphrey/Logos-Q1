from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count
from typing import Any, Callable, Dict, List, Optional

# Importing ccxt lazily keeps dependency optional for environments without the
# exchange library installed.  Individual adapters will surface a clear error
# if instantiation happens while the module is missing.
try:  # pragma: no cover - exercised via adapter usage
    import ccxt  # type: ignore
except Exception:  # pragma: no cover - fallback path validated in tests
    ccxt = None  # type: ignore

from .common import (
    AdapterError,
    FatalAdapterError,
    IdempotentCache,
    RateLimiter,
    RetryConfig,
    RetryableError,
    retry,
)


def _classify_ccxt_error(exc: BaseException) -> BaseException:
    if isinstance(exc, (RetryableError, FatalAdapterError)):
        return exc
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return RetryableError(str(exc))
    if ccxt is not None:
        if isinstance(exc, (ccxt.NetworkError,)):  # type: ignore[attr-defined]
            return RetryableError(str(exc))
        if isinstance(exc, (ccxt.RateLimitExceeded,)):  # type: ignore[attr-defined]
            return RetryableError(str(exc))
        if isinstance(exc, (ccxt.BaseError,)):  # type: ignore[attr-defined]
            return FatalAdapterError(str(exc))
    return FatalAdapterError(str(exc))


@dataclass
class CCXTHardenedAdapter:
    client: Any
    retry_config: RetryConfig = field(default_factory=RetryConfig)
    rate_limiter: RateLimiter = field(
        default_factory=lambda: RateLimiter(max_calls=5, period=1.0)
    )
    sleeper: Callable[[float], None] = field(default=lambda _: None)

    def __post_init__(self) -> None:
        self._cache = IdempotentCache()
        self._seq = count(1)
        self._logs: List[Dict[str, Any]] = []

    def _log(
        self, action: str, payload: Dict[str, Any], response: Dict[str, Any]
    ) -> None:
        record = {
            "action": action,
            "payload": payload,
            "response": response,
        }
        self._logs.append(record)

    @property
    def audit_log(self) -> List[Dict[str, Any]]:
        return list(self._logs)

    def _classify(self, exc: BaseException) -> BaseException:
        return _classify_ccxt_error(exc)

    def _ensure_rate_limit(self) -> None:
        self.rate_limiter.acquire()

    def _next_client_id(self) -> str:
        return f"ccxt-{next(self._seq):06d}"

    def submit_order(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: Optional[float] = None,
        client_id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        cid = client_id or self._next_client_id()
        payload: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "amount": amount,
        }
        if price is not None:
            payload["price"] = price
        if params:
            payload.update({f"param:{k}": v for k, v in sorted(params.items())})

        def resolver() -> Dict[str, Any]:
            self._ensure_rate_limit()

            def op() -> Dict[str, Any]:
                request_params = dict(params or {})
                request_params.setdefault("clientOrderId", cid)
                if order_type.lower() == "market":
                    return self.client.create_order(
                        symbol, order_type, side, amount, None, request_params
                    )
                return self.client.create_order(
                    symbol, order_type, side, amount, price, request_params
                )

            return retry(
                op,
                retry_config=self.retry_config,
                classify=self._classify,
                sleeper=self.sleeper,
            )

        response = self._cache.remember(cid, payload, resolver)
        response.setdefault("clientOrderId", cid)
        response.setdefault("symbol", symbol)
        self._log("submit_order", {**payload, "client_id": cid}, response)
        return response

    def cancel_order(self, client_id: str) -> Dict[str, Any]:
        cached = self._cache.get(client_id)
        if not cached:
            raise FatalAdapterError(f"No cached order for client_id {client_id}")
        order_id = cached.get("id") or cached.get("orderId")
        if not order_id:
            raise FatalAdapterError("Cached order missing exchange id")

        def op() -> Dict[str, Any]:
            self._ensure_rate_limit()
            return self.client.cancel_order(order_id, cached.get("symbol"))

        response = retry(
            op,
            retry_config=self.retry_config,
            classify=self._classify,
            sleeper=self.sleeper,
        )
        response.setdefault("clientOrderId", client_id)
        self._cache.update(client_id, response)
        self._log(
            "cancel_order", {"client_id": client_id, "order_id": order_id}, response
        )
        return response

    def reconcile(self) -> Dict[str, List[str]]:
        def op() -> List[Dict[str, Any]]:
            self._ensure_rate_limit()
            return self.client.fetch_open_orders()

        try:
            open_orders = retry(
                op,
                retry_config=self.retry_config,
                classify=self._classify,
                sleeper=self.sleeper,
            )
        except AdapterError:
            open_orders = []
        remote_ids = {
            order.get("clientOrderId")
            or order.get("client_order_id")
            or order.get("id")
            for order in open_orders
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
