# Portfolio Risk Guardrails

This document summarizes the Phase 6 portfolio sizing and safety overlays that
now backstop live and paper trading sessions.

## Allocators

- **Volatility Parity** – inverse-volatility weighting using an EWMA covariance
  estimate with shrinkage toward the diagonal.
- **Risk Budgeting** – iterative risk parity solver that nudges weights toward
  target risk contributions while keeping allocations long-only and normalized.
- **Configuration** – defaults: 20-day lookback, 0.94 decay, 0.5 correlation
  shrinkage, and a 20% rebalance drift tolerance.

## Risk Overlays

- **Gross / Per-Asset / Class Caps** – blocks orders that would expand exposure
  beyond configured thresholds while allowing reductions to pass.
- **Per-Trade Notional & Drawdown Caps** – prevents single orders exceeding a
  fraction of NAV and halts trading when portfolio or strategy drawdowns breach
  daily limits.
- **Cooldowns** – a rejection triggered by portfolio drawdown activates a
  session-level cooldown timer, pausing new risk additions.

## Capacity & Turnover

- **ADV Tracking** – maintains a rolling cash-volume history to approximate
  average daily notional and turn it into participation ratios per order.
- **Warnings vs Blocks** – emits `risk_warning` log entries once turnover or
  participation crosses warning thresholds and blocks orders beyond hard caps.

## Integration Points

- `logos/live/runner.py` surfaces projected exposures, turnover, and capacity to
  the risk layer and records cooldown state.
- `logos/live/risk.py` shells the raw `RiskLimits` configuration into portfolio
  decisions and relays warnings back to the runner.
- `logos/portfolio/smoke.py` offers a synthetic sanity check that the allocator
  outputs and risk overlays are internally consistent.

## Testing

- Unit coverage lives under `tests/unit/portfolio/` exercising allocators,
  capacity helpers, and the overlay decision tree.
- `pytest tests/test_live_runner.py` validates warning propagation inside the
  live loop with mocked market data and paper fills.
