# Docs

- Place HTML docs and site assets here.
- Usage:
  - Tutor: `python -m logos.tutor --lesson mean_reversion --plot --explain-math`
  - Backtest (demo): `python -m logos.cli backtest --symbol BTC/USD --strategy mean_reversion`
- Contracts:
  - Generate strategies index: `python -m logos.tools.generate_strategies_index --out strategies/index.json --version v1`
- Artifacts:
  - Global logs: `logos/logs/app.log`
  - Per-run: `runs/<id>/{config.yaml, metrics.json, provenance.json, session.md, trades.csv, equity.png, logs/run.log}`
  - Lessons: `runs/lessons/<lesson>/<timestamp>/{transcript.txt, glossary.json, plots/*.png}`
  - Research workflows: see `docs/WALK_FORWARD.md` for walk-forward & tuning guidance
  - CI smoke: run `make phase5-smoke` (and see workflow `Phase 5 Research Smoke`) for walk-forward/tuning fixtures
  - Portfolio smoke: run `make phase6-smoke` (workflow `Phase 6 Portfolio Smoke`) to exercise allocators and risk overlays