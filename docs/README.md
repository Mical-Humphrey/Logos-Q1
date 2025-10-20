# Docs

- Place HTML docs and site assets here.
- Usage:
  - Tutor: `python -m logos.tutor --lesson mean_reversion --plot --explain-math`
  - Backtest (demo): `python -m logos.cli backtest --symbol BTC/USD --strategy mean_reversion`
- Artifacts:
  - Global logs: `logos/logs/app.log`
  - Per-run: `runs/<id>/{config.yaml, metrics.json, trades.csv, equity.png, logs/run.log}`
  - Lessons: `runs/lessons/<lesson>/<timestamp>/{transcript.txt, glossary.json, plots/*.png}`