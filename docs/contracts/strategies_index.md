# Strategies Index Contract v1

The `strategies/index.json` artifact is generated via:

```bash
python -m logos.tools.generate_strategies_index --out strategies/index.json --version v1
```

Key guarantees:

- `version` is fixed to `v1`; the generator rejects unknown versions.
- `generated_at` is emitted as UTC ISO 8601 (`...Z`).
- `strategies` are sorted by `strategy_id` for determinism.
- Each `strategy_id` is unique; schema validation fails on duplicates.
- Optional additive data belongs inside `ext` objects (both top-level and per-strategy).
- The serialized document must stay at or below **307,200 bytes (300 KiB)**. The generator enforces this size guard, logs a structured error, and aborts if the limit is exceeded.

Downstream services should validate inputs with `core.contracts.validate_strategies_index` to ensure forward compatibility with the established schema.
