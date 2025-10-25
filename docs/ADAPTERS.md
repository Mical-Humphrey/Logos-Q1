# Adapter Go-Live Playbook

Phase 9 hardens the CCXT, Alpaca, and Oanda connectors with consistent safety rails. This playbook guides the transition from paper rehearsals to controlled live activation.

## Scope at a Glance
- `logos.adapters.ccxt_hardened.CCXTHardenedAdapter` for spot crypto venues accessed through CCXT.
- `logos.adapters.alpaca.AlpacaAdapter` for Alpaca equities accounts (paper + live).
- `logos.adapters.oanda.OandaAdapter` for Oanda v20 FX accounts.
- Shared guard rails reside in `logos.adapters.common` (`RetryConfig`, `RateLimiter`, `IdempotentCache`, audit logging).

## Go-Live Checklist
1. Confirm paper accounts operated without critical errors for the prior 14 consecutive calendar days; archive the `runs/` artifacts for traceability.
2. Validate the environment secrets for each venue (API keys, passphrases, account ids) are loaded from the secure store and never hard-coded in configs.
3. Review Phase 7.5 gating: ensure live order switches and kill-switch controls remain engaged; designate the change window and approvers.
4. Pin dependency versions (`ccxt`, `alpaca-trade-api`, `oandapyV20`) to the approved hashes and document them in the deployment ticket.
5. Run `pytest tests/unit/adapters -q` from a clean virtualenv to prove adapters still satisfy the retry/idempotency contracts.
6. Execute dry-run orchestration against paper endpoints using the desired production presets (see `configs/presets/`) and capture audit logs via `adapter.audit_log`.
7. Compare reconciliation reports (`adapter.reconcile()`) across paper and local caches; resolve any outstanding `missing_remote` or `untracked_remote` ids.
8. Obtain sign-off from operations and risk that the go-live checklist is complete; attach paper soak evidence and the dry-run logs.
9. Schedule the live activation window, temporarily tightening `RateLimiter` thresholds if required, and verify alerting hooks for adapter error classifications.
10. Flip the live gating control under dual control, monitor the first order burst, and confirm audit logs stream to the observability sink before declaring success.

## Paper Soak Plan (14 Days)
- Days 1-3: Run daily paper sessions for all adapters using production presets; verify reconciliation reports are empty by session close.
- Days 4-6: Introduce network perturbation drills (simulated timeouts/retries) and confirm retry logs classify errors as expected.
- Days 7-9: Perform paired cancel/replace scenarios to validate `IdempotentCache` conflict handling and ensure no duplicate exchange orders are emitted.
- Days 10-12: Capture end-to-end audit logs and aggregate metrics for rate-limit utilisation; hand summaries to operations.
- Days 13-14: Conduct final readiness review, freeze configuration values, and publish the go-live ticket with sign-offs from engineering, operations, and risk.

## Log and Artifact Expectations
- Store adapter audit logs under the corresponding `runs/<timestamp>_<venue>_<strategy>/` directory for each session.
- Record reconciliation outputs and retry traces in the deployment ticket to support future incident reviews.
- Escalate any deviation from baseline metrics through the established incident response channel prior to attempting live activation.

## References
- Technical primer: `docs/ADAPTER_HARDENING.md`
- Spec: `specs/009-adapters/spec.md`
- Unit tests: `tests/unit/adapters/`