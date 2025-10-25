# Adapter Hardening (Phase 9)

Phase 9 introduces hardened connectors for the primary execution venues supported by Logos. Each adapter ships with the same guard rails so orchestration and live runners can operate deterministically:

- **Retry discipline** – adapters apply exponential backoff using `logos.adapters.common.retry` and a venue-specific classifier that separates retryable transport failures from fatal venue rejections.
- **Sliding-window rate limiting** – each venue uses `RateLimiter` defaults that reflect realistic API ceilings; overrides are accepted for integration tests.
- **Idempotent order flow** – `IdempotentCache` binds a client order id to its payload and prevents accidental replays with mutated parameters. The cache also stores the most recent exchange response for reconciliation.
- **Audit log hooks** – adapters retain a lightweight in-memory trail so higher layers can export telemetry and simplify manual investigations.

## Adapter Modules

| Module | Description |
| --- | --- |
| `logos.adapters.ccxt_hardened.CCXTHardenedAdapter` | Hardened wrapper for CCXT spot venues. Wraps `create_order`, `cancel_order`, and `fetch_open_orders` with retry, rate limit, and idempotent replay. |
| `logos.adapters.alpaca.AlpacaAdapter` | Paper/live equities trading against Alpaca REST. Supports standard order flags, idempotent cancel by client id, and reconciliation via `list_orders`. |
| `logos.adapters.oanda.OandaAdapter` | FX adapter for Oanda v20 REST. Handles signed unit conversions, client extensions, cancel semantics, and pending-order reconciliation. |

## Usage Checklist

1. Construct the venue client with existing credentials (config presets are under `configs/presets/*`).
2. Instantiate the adapter, optionally overriding `retry_config`, `rate_limiter`, or `sleeper` for tighter backoff during testing.
3. Use deterministic `client_id` values so the cache can enforce idempotency across restarts. The adapters auto-generate ids if you omit them.
4. Call `reconcile()` periodically during live trading to detect divergence between the local cache and the venue's open orders.
5. Review `adapter.audit_log` when debugging operator reports; integrate with structured logging if persistent storage is required.

Refer to `tests/unit/adapters/` for concrete stubs and fixtures that illustrate the expected client surface area.

## Operational Playbook

See `docs/ADAPTERS.md` for the go-live checklist, paper soak plan, and operator workflow that gate production activation for the hardened adapters.
