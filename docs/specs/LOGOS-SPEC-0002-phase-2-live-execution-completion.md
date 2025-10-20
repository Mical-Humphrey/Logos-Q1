# Feature Specification: Phase 2 - Live Execution Completion

**Feature Branch**: `001-complete-live-loop`  
**Created**: 2025-10-20  
**Status**: Draft  
**Input**: User description: "Phase 2 - Live Execution Completion (Core Loop, Risk, Feeds, Artifacts, Adapters). Deliver the end-to-end paper trading loop with deterministic data and full safety. Complete the strategy-to-order translator; finish the paper broker (deterministic fills, FIFO inventory, realized/unrealized PnL, order lifecycle, event logging); add deterministic minute-bar feeds (cache replay for tests, yfinance for equities, CCXT public for crypto) with freshness/retry/backoff. Wire max-notional/exposure/drawdown/stale-data/kill-switch risk guards; persist state.json/state.jsonl; reconcile open orders; emit full session artifacts (orders.csv, trades.csv, positions.csv, account.csv, session.md). Integrate runner to prove end-to-end paper session. Finalize CCXT/Alpaca dry-run adapters; IB as documented stub. Keep pytest -q green without network credentials; docs/runbook refreshed."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Execute deterministic paper session (Priority: P1)

An operator can run `python -m logos.live trade` in paper mode, consume deterministic feeds, and
receive the full artifact bundle plus restart-ready state files without touching real brokers.

**Why this priority**: End-to-end reproducibility is the cornerstone for safe live deployment and is
required before adapters or docs matter.

**Independent Test**: Run the CLI against bundled fixtures; verify artifacts, state recovery, and
absence of real network usage.

**Acceptance Scenarios**:

1. **Given** deterministic fixture data and paper configuration, **When** the operator runs the live
   CLI, **Then** the session completes with artifacts in `runs/live/sessions/<id>/` and logs in
   `logos/logs/`.
2. **Given** a paused session state, **When** the operator restarts the CLI with the saved
   `state.json`, **Then** positions, orders, and metrics resume without duplication or loss.

---

### User Story 2 - Enforce safety and risk controls (Priority: P2)

A risk reviewer can rehearse the live loop in paper mode and observe each guardrail (notional,
exposure, drawdown, stale data, kill switch) triggering expected halts and reporting.

**Why this priority**: The project constitution mandates safety-first live trading; risk guards must
activate before exposing real capital.

**Independent Test**: Inject scenarios that exceed caps or simulate stale data, confirming the
runner stops safely and emits actionable messages.

**Acceptance Scenarios**:

1. **Given** configured max-notional and exposure limits, **When** generated orders exceed those
   caps, **Then** the runner blocks submissions, logs the violation, and records it in
   `session.md`.
2. **Given** a stale-data threshold and kill-switch path, **When** data freshness fails or the
   kill-switch file is touched, **Then** the session halts and writes a final summary describing the
   trigger.

---

### User Story 3 - Validate deterministic feeds and adapters (Priority: P3)

A data engineer can replay cached minute bars, swap to mocked yfinance/CCXT pollers, and confirm
adapters validate credentials without contacting live endpoints.

**Why this priority**: Deterministic feeds unlock reproducible tests and offline CI, while adapter
validation ensures controlled progression toward real trading.

**Independent Test**: Run feed loaders and adapter dry runs in isolation, using fixtures to
simulate network responses and credential checks.

**Acceptance Scenarios**:

1. **Given** cached fixtures in `data/cache/`, **When** feeds replay minute bars, **Then** they emit
   identical sequences across runs and record freshness metadata.
2. **Given** mocked credential inputs, **When** CCXT or Alpaca adapters run in dry-run mode,
   **Then** they confirm configuration health without sending orders or leaking secrets.

---

### Edge Cases

- Feeds encounter partially written cache files or truncated CSV rows during refresh.
- Restart occurs while orders are mid-lifecycle (e.g., partially filled) and inventory must reconcile.
- Risk guards trigger simultaneously (e.g., drawdown plus stale data) and the runner must record all
  causes without racing.
- Adapter configuration is missing optional sandbox credentials and should emit actionable errors.

## Determinism, Safety & Compliance *(mandatory)*

### Reproducibility & Deterministic Execution
- Provide fixture bundles in `data/cache/` for equities, crypto, and forex minute bars; tests use
  these fixtures exclusively.
- Expose a shared seed via `logos.paths.env_seed()` for any stochastic behavior and persist the
  seed value inside `session.md`.
- Disable outbound network calls in fast tests by default; integration tests that mock yfinance or
  CCXT must assert mocked endpoints were invoked instead of the real network.

### Live Trading Safety
- All new behaviors are validated in paper mode; any CLI toggle enabling `--live` requires explicit
  `--i-acknowledge-risk` confirmation and remains outside the sprint scope.
- Unit tests cover each risk guard, and an integration rehearsal triggers caps, stale data, and the
  kill switch to prove safe shutdowns.
- The config validator blocks missing credentials or unsafe defaults before the runner starts.

### Streamlit UI Accessibility & Performance *(fill or mark N/A with justification)*
- N/A: The dashboard remains read-only per Phase 3 scope; this effort only updates backend session
  data consumed by the UI. No new UI surfaces are introduced.

### Documentation & Artifact Updates
- Update `README.md`, `docs/MANUAL.html`, and `docs/LIVE-RUNBOOK.md` with the final live workflow,
  safety checklist, and recovery steps.
- Document adapter dry-run expectations and seed handling in `docs/LIVE-RUNBOOK.md`.
- Ensure artifacts continue to land in `runs/live/sessions/<id>/`, `logos/logs/`, and
  `data/cache/`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST translate backtest strategy signals into quantized `OrderIntent`
  objects that honor symbol precision, lot sizing, and notional caps.
- **FR-002**: The system MUST provide a deterministic paper broker that tracks FIFO inventory and
  computes realized and unrealized PnL for every order lifecycle state.
- **FR-003**: The system MUST load minute-bar data from deterministic caches and support mocked
  polling of yfinance and CCXT sources with freshness tracking and retry/backoff logic.
- **FR-004**: The system MUST enforce risk guardrails (max-notional, exposure, drawdown,
  stale-data rejection, kill switch) that halt the runner and emit structured events when triggered.
- **FR-005**: The system MUST persist `state.json` and `state.jsonl` snapshots that allow session
  restarts without duplicate trades or lost orders.
- **FR-006**: The system MUST produce session artifacts (`orders.csv`, `trades.csv`, `positions.csv`,
  `account.csv`, `session.md`) inside `runs/live/sessions/<id>/` for every run.
- **FR-007**: The system MUST provide CCXT and Alpaca adapters that confirm credential readiness in
  dry-run mode without sending live orders, while documenting the IB stub status.
- **FR-008**: The system MUST block configurations that rely on real network credentials during
  automated tests and CI, ensuring `pytest -q` succeeds offline.

### Key Entities *(include if feature involves data)*

- **OrderIntent**: Represents a quantized order request derived from strategy signals, including
  symbol metadata, side, quantity, and risk annotations.
- **PaperFillRecord**: Captures deterministic fill events, linking orders to FIFO inventory updates
  and realized/unrealized PnL snapshots.
- **SessionState**: Persists the live runner snapshot (positions, outstanding orders, seed,
  timestamps) in JSON form for restart and audit use.
- **SessionArtifactBundle**: Collection of CSV/Markdown outputs written per run for operators and
  dashboards.

### Assumptions

- Live order submission remains out of scope; all integrations operate in paper or dry-run modes.
- Existing backtest signals already produce deterministic outputs; no changes are required beyond
  translating to `OrderIntent` instances.
- Environment variables and `.env` files can supply sandbox credentials for adapter validation
  during manual testing.

## Success Criteria *(mandatory)*

### Measurable Outcomes

  start to artifact review, without manual directory cleanup.
  the runner within 5 seconds of detection.
  translator, broker, feeds, risk guards, and state persistence.
  providing step-by-step safety checklists for paper rehearsals and restarts.
