# CSV Ingestion Guard

The ingestion guard protects the raw data inbox before files enter the
processing pipeline. It combines the chunked CSV reader, JSON Schema
validation, and quarantine utilities to keep malformed or stale inputs
from contaminating downstream jobs.

## Behaviour

1. The guard streams a CSV with `core.io.chunked_reader.read_csv_chunked`,
   enforcing row and byte limits while recording a preview sample.
2. Each row can be validated against an optional JSON Schema. Validation
   errors automatically route the input to the quarantine bucket.
3. A timestamp column is tracked to ensure the newest record is not older
   than a configurable staleness threshold.
4. Results are logged to a JSONL telemetry file so dashboards or alerts can
   observe accepted versus quarantined files.

## CLI Usage

```bash
python -m tools.ingest_guard \
  --schema schemas/prices.schema.json \
  --timestamp-column timestamp \
  --stale-seconds 3600 \
  input_data/raw/*.csv
```

Exit code is non-zero when any file is quarantined or missing. Telemetry
defaults to `logos/logs/ingest_telemetry.jsonl` and quarantined files land
under `input_data/quarantine/`.
