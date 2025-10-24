# Phase 2 Artifacts — Baseline and Seed

- Baseline Version: `phase2-v1`
- Canonical Seed: `7`
- Dataset (smoke): `tests/fixtures/live/regression_default`

## Commands

Smoke regression (paper broker):
```bash
python -m logos.live.regression --adapter-mode paper \
  --label regression-smoke --seed 7 \
  --dataset tests/fixtures/live/regression_default \
  --output-dir runs/live/reg_cli
```

Full QA stack:
```bash
make phase2-qa
```

Refresh smoke baselines:
```bash
make phase2-refresh-smoke
# Or run the script directly:
bash scripts/phase2/refresh-baselines.sh --smoke --seed 7
```

Notes:
- All runs must be offline with fixtures.
- If the seed changes (e.g., to `424242`), refresh all baselines immediately and update this file in the same PR.