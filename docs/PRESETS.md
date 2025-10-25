# Preset Library (Phase 12)

The preset library provides curated configuration bundles for common investment postures. Presets remain read-only helpers: operators must review and copy settings into their own configuration files before running live sessions.

## Preset Bundles

| Bundle | Objective | Strategies | Risk Notes |
| --- | --- | --- | --- |
| `conservative` | Capital preservation with modest growth | Mean reversion on large-cap equities, FX carry hedged with cash | Targets low drawdown; annualized volatility capped via conservative position sizing. |
| `balanced` | Blended growth and defensive overlay | Equity mean reversion + crypto momentum + FX pairs diversification | Maintains diversification across asset classes; cooldowns on correlated strategies. |
| `aggressive` | High conviction trend capture | Crypto momentum + short-term breakout + equity pairs overlays | Highest turnover and volatility; requires close monitoring of drift reports. |

Filesystem layout: `configs/presets/<bundle>/<component>.yaml`

- `portfolio.yaml` – baseline strategy weights and capital allocation.
- `strategies.yaml` – per-strategy parameters (lookbacks, thresholds, risk caps).
- `risk.yaml` – guard rails, cooldowns, and adapter toggles.
- `sources.yaml` – data feed configuration and backtest fixture references.

## Using Presets Safely

1. Copy the preset directory into a user-specific workspace (do not edit in place):
   ```bash
   cp -r configs/presets/conservative configs/custom/my_conservative
   ```
2. Update credentials/secrets in the copied files as needed.
3. Validate with the CLI:
   ```bash
   python -m logos.cli validate --config configs/custom/my_conservative/portfolio.yaml
   ```
4. Run paper rehearsals before enabling live adapters:
   ```bash
   python -m logos.run --mode paper --label conservative-smoke
   ```

## Expected Behaviors

- **Conservative**: Daily turnover < 10%; drawdown guard triggers at -5% and escalates to risk review.
- **Balanced**: Weekly rebalance using Phase 11 meta allocator proposals (still human approved).
- **Aggressive**: Momentum sleeves use higher `RateLimiter` thresholds; plan for more frequent monitoring alerts.

## Accessibility & Documentation

Each preset bundle includes `README.md` with:
- Strategy descriptions and rationale.
- Links to relevant tutorials in `docs/LEARNING_PATH.md`.
- Contact points for governance sign-off before live promotion.

A quick reference card is available via `docs/LEARNING_PATH.md` → “Preset Quest.”
