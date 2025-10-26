# 2‑Week Paper Soak — Super Explicit Linux Guide

This soak harness will paper‑trade and generate a daily report (`runs/soak/reports/YYYY‑MM‑DD/report.md`).  
By default it runs a quick 5 minute test; pass `--full` to run 14 days x 24h.

What you’ll run:
- Orchestrator: `scripts/test_2_week.sh`
- Reporter: `tools/soak_report.py`
- Your paper session: a command you provide (or the default works if you use `logos.cli`)

The orchestrator also creates a user‑space logrotate config (no sudo) under `runs/soak/logrotate*` and rotates its own logs.

---

## 0) Requirements

- Linux server (Ubuntu/Debian/CentOS OK)
- git, Python 3.10+ (`python3 --version`)
- Optional: tmux (recommended for long sessions)
- Disk: at least 5–10 GB free in the project volume

Install basics (Ubuntu example):
```bash
sudo apt update
sudo apt install -y git python3 python3-venv tmux
```

---

## 1) Clone and prepare a virtualenv

Create a working directory and clone:
```bash
sudo mkdir -p /opt/Logos-Q1
sudo chown -R "$USER":"$USER" /opt/Logos-Q1

cd /opt/Logos-Q1
git clone https://github.com/Mical-Humphrey/Logos-Q1.git .
```

Create a venv and install:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip

# If your repo uses requirement files:
pip install -r requirements.txt
# (Optional) Dev extras:
[ -f requirements/dev.txt ] && pip install -r requirements/dev.txt || true

# If you don’t have requirements files, install the package instead:
# pip install -e .
```

---

## 2) Make the soak scripts executable

```bash
chmod +x scripts/test_2_week.sh tools/soak_report.py
```

---

## 3) Check the CLI entrypoint

Before wiring the soak harness to anything, make sure the current CLI exposes the subcommand you expect. Activate the virtualenv and confirm that `python -m logos.cli` lists `paper`.

```bash
source .venv/bin/activate
python -m logos.cli --help | head -n 20
python -m logos.cli paper --help
```

You can test a short 10-second paper run manually to see a heartbeat session under `runs/paper/sessions/...`:

```bash
python -m logos.cli paper --offline --duration-sec 10 --heartbeat-sec 2
```

## 4) Decide your paper‑run command

You MUST provide the exact command that starts a paper session, unless the default suits you.

- Default used by the harness:
```bash
python -m logos.cli paper --offline --duration-sec ${DAY_RUNTIME_SEC}
```

- If your command differs, you can either export it:
```bash
export RUN_CMD="python -m logos.cli paper --offline --duration-sec 300"
```
…or pass it inline via `--run-cmd "…"` when invoking the script.

Tip: Test your command manually for 60 seconds to confirm it runs and writes artifacts into `runs/`:
```bash
bash -lc "$RUN_CMD"
# Ctrl+C to stop
```

---

## 5) Quick dry run (5 minutes, default)

This verifies the harness and your command on this machine.

Option A — If your command matches the default:
```bash
./scripts/test_2_week.sh
```

Option B — Specify your command inline:
```bash
./scripts/test_2_week.sh --run-cmd "python -m logos.cli paper --offline --duration-sec 300"
```

Check the report:
```bash
sed -n '1,120p' runs/soak/reports/$(date -u +%F)/report.md
```

What “good” looks like:
- Report exists with reasonable metrics
- Orchestrator log at `runs/soak/logs/YYYY-MM-DD.log`
- No restarts in the daily summary unless intentional

---

## 6) Full 2‑week soak

Run the harness for 14 days x 24h per day. You can run it directly or inside tmux.

Minimal, foreground:
```bash
./scripts/test_2_week.sh --full
```

Recommended (wrap in tmux so your SSH disconnects don’t stop the orchestrator):
```bash
tmux new -s logos-soak
source .venv/bin/activate
./scripts/test_2_week.sh --full
# Detach from tmux: Ctrl-b then d
# Reattach later: tmux attach -t logos-soak
```

Notes:
- The harness itself can launch your app inside tmux (child session) when `--use-tmux 1` (default).  
  Wrapping the harness in tmux as shown above is just additional safety for your SSH session.

---

## 7) Useful flags and environment overrides

- `--full`                     Run 14 days x 24h
- `--days N`                   Custom number of days (default 1)
- `--day-seconds S`            Seconds per day (default 300 for quick run)
- `--run-cmd "CMD"`            Set your paper run command inline
- `--use-tmux 0|1`             Launch child in tmux (default 1)
- `--runs-dir PATH`            Override the runs/ directory (default: `<repo>/runs`)
- `--no-artifacts-tar`         Skip creating `app_artifacts.tgz` to reduce IO

Environment variables (same names as flags) also work, e.g.:
```bash
export RUNS_DIR=/data/logos/runs
export USE_TMUX=1
```

Python selection:
```bash
# The harness tries .venv first; override if needed:
export PYTHON_BIN=python3
```

---

## 8) Daily check and stopping

Check today’s orchestrator log and report:
```bash
tail -n 200 runs/soak/logs/$(date -u +%F).log
sed -n '1,120p' runs/soak/reports/$(date -u +%F)/report.md
```

Stopping:
- If you wrapped the harness in tmux:
  - Reattach: `tmux attach -t logos-soak`
  - Stop: Ctrl+C inside the harness, then exit
  - Or kill the tmux session: `tmux kill-session -t logos-soak`
- If you ran in the foreground: Ctrl+C

What is rotated:
- The harness rotates its own logs under `runs/soak/logs/` using a user‑space logrotate config in `runs/soak/logrotate*`.  
  No sudo required; if `logrotate` isn’t installed, logs are still split by day.

---

## 9) Notes and assumptions

- “Logos‑aware but tolerant”: If your app writes `metrics.json` files into `runs/`, the report aggregates them. If not, you still get orchestrator stats.
- No network or disk failure injections are performed unless you explicitly enable them (advanced; disabled by default).
- Auto‑restart: When `--use-tmux 0`, the harness restarts your process if it crashes. In tmux mode, the harness can’t see the PID, so it won’t auto‑restart the child; use non‑tmux mode if you require auto‑restart. In practice, tmux + a stable app is fine.
- Old hardware: On low‑RAM or slow disks, consider `--no-artifacts-tar` to reduce IO.

---

## 10) Troubleshooting

- “No metrics.json found” in report:
  - Ensure your paper run writes metrics under `runs/` on that day.
  - Confirm your `--run-cmd` is the paper mode and points to the correct config.
- “Python not runnable”:
  - Activate your venv: `source .venv/bin/activate`
  - Or set `export PYTHON_BIN=python3`
- “Command not found” for tmux:
  - Install tmux or run with `--use-tmux 0` (or install: `sudo apt install -y tmux`)

---