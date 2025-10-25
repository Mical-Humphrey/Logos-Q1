# Data Tooling & Feature Store

Phase 8 introduces deterministic data plumbing so research runs reproduce exactly across machines.

## Data CLI

Fetch price data while respecting the fixture-first policy:

```bash
python -m logos.data.cli fetch \
  --symbol MSFT \
  --asset-class equity \
  --start 2024-01-01 \
  --end 2024-02-01 \
  --interval 1d
```

The command writes a CSV and metadata JSON under `data/cache/<asset-class>/`. Use `--output-interval` to resample (e.g. `1h`) after loading fixtures. Synthetic data remains opt-in via `--allow-synthetic`.

## Feature Store

`FeatureStore` version-stamps features with a fingerprint that blends the data hash, code hash, parameter bundle, and lineage inputs. Example:

```python
from logos.data import ColumnSpec, DataContract, FeatureStore

contract = DataContract(
    name="daily-bars",
    columns=(
        ColumnSpec("Open", "float"),
        ColumnSpec("Close", "float"),
        ColumnSpec("Volume", "int", nullable=True),
    ),
)
store = FeatureStore()
version = store.register(
    "msft-medium-horizon",
    df,
    contract=contract,
    params={"horizon": 20},
    code_hash="ae3b42b5",
    sources=["data/cache/equity/MSFT_1d.csv"],
)
```

`FeatureStore.load(name)` returns the DataFrame plus metadata so downstream jobs can verify lineage.

## Contracts & Time-Safe Joins

`DataContract` validates schema, nullability, and index ordering. `time_safe_join` provides a backward-only merge helper that blocks feature leakage. Use `tolerance` (e.g. `"1h"`) when gaps are expected.
