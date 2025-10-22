# Phase 2 Artifact Index

This index captures the deterministic artifacts that back Phase 2 verification. Use it as the
single source of truth for regression outputs, adapter dry-runs, and baseline references.

---

## Baseline Contract (Phase 2)
- Version gate: each baseline root contains a `BASELINE_VERSION` file; the harness expects `phase2-v1`.
- Volatile metadata ignored during JSON comparison: `run_id`, `generated_at`, `provenance.generated_at`, `provenance.git.commit`, `provenance.git.branch`, `tool_version`, `hostname`, `pid`.
- Metrics tolerance: absolute difference ≤ `1e-09`; all other numeric values remain exact.
- Window metadata (`window.start_iso`, `window.end_iso`, `window.tz`), seed, strategy IDs, and adapter modes continue to compare strictly.

---

## Baseline Smoke Bundle (tests/fixtures/regression/smoke)
| Artifact | Path | sha256 |
| --- | --- | --- |
| Snapshot | tests/fixtures/regression/smoke/snapshot.json | `5a2c19d88e195d91e729d4a2856739e7f02e58af3c6e73f54b6f046887769601` |
| Equity curve | tests/fixtures/regression/smoke/equity_curve.csv | `d96f942b1021166f8aebd26019deb170eab5170a269de4936182bf4340e7cc3c` |
| Metrics | tests/fixtures/regression/smoke/metrics.json | `e61cedeaa8aece3b598ebe92594eb2b793e666ed6f9843208f4f36a9424a576b` |

> Verification: `sha256sum <file>` should match the value above. Baselines change only via the
> governance process captured in `README.md` and `docs/LIVE-RUNBOOK.md`.

---

## Regression CLI Outputs (runs/live/reg_cli)
All runs use dataset `tests/fixtures/live/regression_default`, seed `7`, and clock window
`2024-01-01T09:29Z`–`09:32Z`.

### Paper Broker (FR-002 · FR-006)
| Artifact | Path | sha256 |
| --- | --- | --- |
| Snapshot | runs/live/reg_cli/0007-regression-smoke/snapshot.json | `102684f89d9b2aa028116b980c7e0f0136276c347228fcc4e4f72a903dae972e` |
| Equity curve | runs/live/reg_cli/0007-regression-smoke/artifacts/equity_curve.csv | `d96f942b1021166f8aebd26019deb170eab5170a269de4936182bf4340e7cc3c` |
| Metrics | runs/live/reg_cli/0007-regression-smoke/artifacts/metrics.json | `e61cedeaa8aece3b598ebe92594eb2b793e666ed6f9843208f4f36a9424a576b` |

*Notes:* Matches smoke baseline for equity/metrics; snapshot includes additional config metadata
(clock, adapter mode).

### CCXT Dry-Run Adapter (FR-007)
| Artifact | Path | sha256 |
| --- | --- | --- |
| Snapshot | runs/live/reg_cli/0007-ccxt-dry-run/snapshot.json | `c39b34822b0d82c4b2bba98d739f88fff0ecdab2877af83798ff912d23aab8b9` |
| Equity curve | runs/live/reg_cli/0007-ccxt-dry-run/artifacts/equity_curve.csv | `1f1afaab620a8fdc2d67468b295b5badf5eb8299d603bb0a84f378be951708e6` |
| Metrics | runs/live/reg_cli/0007-ccxt-dry-run/artifacts/metrics.json | `7cb386eff59344935289c1f1c6b62fb2073913c298b45ab000f7755820ccf27c` |
| Adapter logs | runs/live/reg_cli/0007-ccxt-dry-run/artifacts/adapter_logs.jsonl | `a8b2334aad6045a1bd8da97d9c2cd69f2bf73d0f5d03a7d1285277cd654b8976` |

*Notes:* No fills are recorded; adapter log lines document credential validation and dry-run mode
handshake.

### Alpaca Dry-Run Adapter (FR-007)
| Artifact | Path | sha256 |
| --- | --- | --- |
| Snapshot | runs/live/reg_cli/0007-alpaca-dry-run/snapshot.json | `5be0a1e963dcdbd24db15ab2cabf1a1193b4d9eb82b1cbe6d20121be843bccdb` |
| Equity curve | runs/live/reg_cli/0007-alpaca-dry-run/artifacts/equity_curve.csv | `1f1afaab620a8fdc2d67468b295b5badf5eb8299d603bb0a84f378be951708e6` |
| Metrics | runs/live/reg_cli/0007-alpaca-dry-run/artifacts/metrics.json | `8145d5441b49f3e60510b5f1f468883226997228189e1406169ae32500448f97` |
| Adapter logs | runs/live/reg_cli/0007-alpaca-dry-run/artifacts/adapter_logs.jsonl | `f25ef34fbe23df76261f1b0d3eb9b8539a15a6469db0bd09ac73000322dd6149` |

*Notes:* Mirrors CCXT behaviour — equity remains flat, confirming dry-run execution with zero
orders.

---

## Live Session Artifact Layout (FR-006 · FR-005)
| Component | Path Pattern | Description |
| --- | --- | --- |
| State files | `runs/live/sessions/<session_id>/state.json` & `state.jsonl` | Restart snapshots + structured events |
| CSV exports | `runs/live/sessions/<session_id>/{orders,trades,positions,account}.csv` | Deterministic journal outputs |
| Session digest | `runs/live/sessions/<session_id>/session.md` | Final summary (guard triggers, seed, equity) |
| Logs | `runs/live/sessions/<session_id>/logs/run.log` | Per-session logging handler |
| Daily rollups | `runs/live/trades/<symbol>_<YYYYMMDD>.csv` | Aggregated trade history |

---

## Verification Workflow
1. Run the regression matrix commands from `README.md`.
2. Compare sha256 digests via `sha256sum` against the tables above.
3. Record any intentional drift in a review issue; update this index and `CHANGELOG.md` once
   approved.
