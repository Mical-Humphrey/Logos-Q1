How to run this on your Linux server (super explicit)

SSH to the server. Create the working directory:
sudo mkdir -p /opt/Logos-Q1
sudo chown -R "USER" /opt/Logos-Q1   #USER is the username of what you're going to run it as

Clone, create venv, install:
cd /opt/Logos-Q1
git clone https://github.com/Mical-Humphrey/Logos-Q1.git .
cd /opt/Logos-Q1/Logos-Q1            # kinda dumb I know lol
python3 -m venv .venv && source .venv/bin/activate
pip install -U pip && pip install -r requirements.txt && pip install -r requirements/dev.txt

Make the 2 soak test files executable:
chmod +x scripts/test_2_week.sh tools/soak_report.py

Decide the exact paper-run command and export RUN_CMD:
export RUN_CMD="python -m logos.cli run --mode paper --config configs/paper.yaml"

Quick dry run (5 minutes):
export SOAK_DAYS=1; export DAY_RUNTIME_SEC=300; export USE_TMUX=1
./scripts/test_2_week.sh
Check runs/soak/reports/YYYY-MM-DD/report.md

Start the full 2-week soak in tmux:
tmux new -s logos-soak
source .venv/bin/activate
export RUN_CMD="..." (your command)
unset SOAK_DAYS; unset DAY_RUNTIME_SEC; export USE_TMUX=1
./scripts/test_2_week.sh
Detach: Ctrl+B then D

Check daily:
tail -n 200 runs/soak/logs/$(date -u +%F).log
sed -n '1,120p' runs/soak/reports/$(date -u +%F)/report.md
Stop anytime:
tmux attach -t logos-soak, Ctrl+C
Or kill the tmux session: tmux kill-session -t logos-soak
Notes and assumptions

This harness is “Logos-aware but tolerant.” If your app writes metrics.json into runs/, the report will aggregate it; if not, you still get orchestrator stats and logs.
No network or disk injections are performed unless you explicitly enable them via env vars.
The script restarts your paper process if it crashes (non-tmux mode); in tmux mode we don’t inspect the PID, so prefer non-tmux if you want automatic restart. In practice, tmux + a stable app is fine.
If your app uses a different runs directory, set RUNS_DIR accordingly: export RUNS_DIR=/data/logos/runs before running the script.