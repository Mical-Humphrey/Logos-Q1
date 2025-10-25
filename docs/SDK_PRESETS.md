# Strategy SDK Presets

This guide shows how to run the three reference strategy presets that ship with the Strategy SDK. Each preset works offline using bundled fixtures so you can reproduce results.

## Available Presets

| Name | Asset Examples | Core Idea |
| ---- | -------------- | --------- |
| `mean_reversion` | equities, crypto, forex | Trade extremes in rolling z-score of closing price |
| `momentum` | equities, crypto | Follow trend via moving-average crossover |
| `carry` | forex, rates proxies | Express rolling carry using multi-period return |

All presets expose the same contract:

- `fit(df)` prepares rolling state.
- `predict(df)` produces raw exposure signals.
- `generate_order_intents(signals)` clamps exposure to `exposure_cap`.
- `explain()` returns a structured dict describing the last decision.

## Quick CLI Usage

Each preset has a YAML snippet under `configs/presets/`. Run a backtest by passing the strategy name and optional parameters:

```bash
logos run backtest \
  --symbol MSFT \
  --strategy momentum \
  --interval 1h \
  --start 2023-06-01 \
  --end 2023-08-31 \
  --params "fast=20,slow=60,exposure_cap=1.0"
```

Explain the latest trade by reusing the dataset with the `--explain` flag in `logos tutor` or manually:

```python
import pandas as pd
from logos.strategies import STRATEGY_EXPLAINERS
from logos.data_loader import get_prices
from logos.window import Window

window = Window.from_bounds(start="2023-06-01", end="2023-08-31")
df = get_prices("MSFT", window, interval="1h", asset_class="equity", allow_synthetic=True)
explain = STRATEGY_EXPLAINERS["momentum"](df)
print(explain["reason"])
```

## Default Parameters

- `mean_reversion`: `lookback=20`, `z_entry=2.0`, `exposure_cap=1.0`
- `momentum`: `fast=20`, `slow=50`, `exposure_cap=1.0`
- `carry`: `lookback=30`, `entry_threshold=0.01`, `exposure_cap=1.0`

You can override parameters via CLI `--params key=value` pairs or by editing the YAML presets.

## Safety and Guards

Preset helpers validate inputs:

- Datetime indexes and required price columns enforced by `ensure_price_frame`.
- NaN exposure rejected via `guard_no_nan`.
- Windows and thresholds must be positive; otherwise a `StrategyError` is raised.
- Exposure output is clamped to ±`exposure_cap`.

When a dataset is too short or all indicators are NaN, the presets abort with an actionable error instead of trading.
