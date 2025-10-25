# Walk-Forward & Tuning Runbook

This guide explains how to run walk-forward validation and parameter tuning with the Logos research toolkit introduced in Phase 5.

## Walk-Forward Validation

The walk-forward engine evaluates a strategy across rolling windows, enforcing guard rails on out-of-sample performance and stress tests. It produces CSV, JSON, Markdown, and HTML artifacts per run.

### CLI Usage

```bash
python -m logos.research.walk_forward \
  momentum \                 # strategy factory name
  AAPL \                     # symbol
  2020-01-01 \               # inclusive start
  2022-01-01 \               # exclusive end
  --interval 1d \
  --asset-class equity \
  --params fast=12 slow=40 \
  --window-size 252 \
  --train-fraction 0.6 \
  --min-oos-sharpe 0.5 \
  --max-oos-drawdown -0.4 \
  --output-dir runs/research/walk_forward/demo
```

Key options:

- `--params`: supply `key=value` overrides for the strategy preset.
- `--window-size` and `--train-fraction`: control the in-sample / out-of-sample split per window.
- `--allow-synthetic`: permit synthetic prices when historical data is missing.
- `--tz`: timezone for interpreting `start` / `end` boundaries (default `UTC`).

Outputs live under the resolved `--output-dir` (or `runs/research/walk_forward/<slug>` if omitted):

- `windows.csv`: per-window metrics and guard flags.
- `summary.json`: configuration, aggregate metrics, guard counts.
- `overview.md`: human-friendly Markdown summary.
- `overview.html`: formatted HTML report suitable for sharing.

## Parameter Tuning

The tuning engine performs a grid search, evaluates guard metrics, and can register the best model candidate in the model registry.

### CLI Usage

```bash
python -m logos.research.tune \
  momentum \                 # strategy name
  AAPL \                     # symbol
  2020-01-01 \               # inclusive start
  2022-01-01 \               # exclusive end
  --grid fast=10,20,30 slow=40,60,80 \
  --min-oos-sharpe 0.5 \
  --max-oos-drawdown -0.4 \
  --registry runs/research/model_registry.json \
  --register-note "WF refresh" \
  --promote
```

Additional flags:

- `--grid`: one or more `key=v1,v2,...` entries defining the tuning grid.
- `--oos-fraction`: portion of the data held back for OOS validation (default `0.25`).
- `--missing-data-stride`: stride for stress-testing the strategy with intermittent missing signals.
- `--registry`: optional JSON file tracking the model lineage.
- `--promote`, `--promote-min-oos-sharpe`, `--promote-max-oos-drawdown`: gate and promote the best candidate to `champion` status.
- `--data-hash` / `--code-hash`: annotate registry entries with provenance details.

Outputs mirror the walk-forward run:

- `trials.csv`: all evaluated trials.
- `trials_top.csv`: top-N trials sorted by Sharpe (configurable via `--top-n`).
- `summary.json`, `overview.md`, `overview.html`: aggregate summaries.

## Model Registry

`logos.research.registry.ModelRegistry` stores model candidates with lineage and promotion status. Records include strategy parameters, evaluation metrics, guard diagnostics, and optional provenance hashes. Promoting a new champion automatically archives the previous one, preserving lineage for audits.

To inspect the registry, open the JSON file or use the Python API:

```python
from logos.research.registry import ModelRegistry

registry = ModelRegistry("runs/research/model_registry.json")
champion = registry.champion()
print(champion.params if champion else "No champion")
```

## Suggested Workflow

1. **Tune parameters** to discover promising candidates and write them to the registry.
2. **Validate via walk-forward** using the tuned parameters, reviewing guard failures and stress metrics.
3. **Promote** successful candidates through the CLI or the Python API, recording hash provenance for reproducibility.
4. **Archive artifacts** (HTML/Markdown/CSV) alongside production deployment packages for compliance and audit trails.
