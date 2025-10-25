#!/usr/bin/env bash
set -euo pipefail

# Quantitative trading soak test (paper) for 14 days with daily reports.
# This orchestrator:
#  - Starts the Logos paper session in a child process (or tmux) for each day
#  - Monitors the process and restarts if it crashes (counting restarts)
#  - Optionally injects safe failures (off by default)
#  - Generates a daily report using tools/soak_report.py
#  - Repeats for 14 consecutive days
#
# IMPORTANT: You MUST set RUN_CMD to the command that starts your paper session.
#
# Examples you might use (pick ONE that matches your project):
#   RUN_CMD="python -m logos.cli run --mode paper --config configs/paper.yaml"
#   RUN_CMD="poetry run logos run --mode paper --config configs/paper.yaml"
#   RUN_CMD="./scripts/quickstart_paper.sh"
#
# By default, we use a placeholder that will fail with a helpful message until you set it.

# ----------- USER CONFIGURATION (EDIT THESE) -----------------

RUN_CMD="${RUN_CMD:-}"           # REQUIRED: command to start a paper session
SESSION_NAME="${SESSION_NAME:-logos-paper}"
SOAK_DAYS="${SOAK_DAYS:-14}"     # Two weeks = 14 days
DAY_RUNTIME_SEC="${DAY_RUNTIME_SEC:-86400}"  # 24h per day (you can reduce for a quick dry run)
ROOT_DIR="${ROOT_DIR:-$(pwd)}"   # Repo root
RUNS_DIR="${RUNS_DIR:-$ROOT_DIR/runs}"           # Where your app writes run artifacts
SOAK_DIR="${SOAK_DIR:-$RUNS_DIR/soak}"           # Where this harness will store soak artifacts
REPORTS_DIR="${REPORTS_DIR:-$SOAK_DIR/reports}"  # Daily reports
LOG_DIR="${LOG_DIR:-$SOAK_DIR/logs}"             # Orchestrator logs
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"  # Python for report script (or "python3")

# Optional: use tmux for isolation (recommended on servers)
USE_TMUX="${USE_TMUX:-1}"   # 1=yes (use tmux), 0=no (run child process directly)

# Failure injection toggles (default OFF for safety)
INJECT_NET_FLAP="${INJECT_NET_FLAP:-0}"     # Requires sudo to toggle iptables briefly
INJECT_DISK_PRESS="${INJECT_DISK_PRESS:-0}" # Creates a temporary large file then deletes
INJECT_RESTART="${INJECT_RESTART:-0}"       # Sends a SIGTERM to child once to test restart

# Net flap parameters (only if INJECT_NET_FLAP=1). Blocks egress for 60s at T+4h by default
NET_FLAP_AFTER_SEC="${NET_FLAP_AFTER_SEC:-14400}"   # 4h
NET_FLAP_DURATION_SEC="${NET_FLAP_DURATION_SEC:-60}"

# Disk pressure parameters (only if INJECT_DISK_PRESS=1)
DISK_PRESS_AFTER_SEC="${DISK_PRESS_AFTER_SEC:-28800}" # 8h
DISK_PRESS_SIZE_GB="${DISK_PRESS_SIZE_GB:-1}"

# Restart injection (only if INJECT_RESTART=1)
RESTART_AFTER_SEC="${RESTART_AFTER_SEC:-21600}" # 6h

# ------------------------------------------------------------

die() { echo "[soak] ERROR: $*" >&2; exit 2; }
ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

check_prereqs() {
  mkdir -p "$RUNS_DIR" "$SOAK_DIR" "$REPORTS_DIR" "$LOG_DIR"
  if [[ -z "${RUN_CMD}" ]]; then
    cat >&2 <<EOF
[soak] RUN_CMD is not set.
Set RUN_CMD to the exact command that starts your PAPER session. Examples:
  export RUN_CMD="python -m logos.cli run --mode paper --config configs/paper.yaml"
  export RUN_CMD="./scripts/quickstart_paper.sh"
Then re-run: scripts/test_2_week.sh
EOF
    exit 2
  fi
  if [[ ! -x "$PYTHON_BIN" && "$PYTHON_BIN" != "python3" ]]; then
    echo "[soak] WARN: PYTHON_BIN '$PYTHON_BIN' not found/executable. Falling back to 'python3'."
    PYTHON_BIN="python3"
  fi
  "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1 || die "Python is not runnable"
print("ok")
PY
}

start_session_tmux() {
  local day_dir="$1" log_file="$2"
  local session="soak_${SESSION_NAME}"
  tmux has-session -t "$session" 2>/dev/null && tmux kill-session -t "$session" || true
  tmux new-session -d -s "$session" -c "$ROOT_DIR" "bash -lc '$RUN_CMD >> \"$log_file\" 2>&1'"
  echo "$session"
}

start_session_fork() {
  local day_dir="$1" log_file="$2"
  ( cd "$ROOT_DIR" && bash -lc "$RUN_CMD" ) >> "$log_file" 2>&1 &
  echo $!
}

inject_net_flap() {
  echo "$(ts) [soak] NET_FLAP: Blocking egress for ${NET_FLAP_DURATION_SEC}s (requires sudo iptables)"
  if sudo iptables -A OUTPUT -j DROP; then
    sleep "$NET_FLAP_DURATION_SEC"
    sudo iptables -D OUTPUT -j DROP || true
    echo "$(ts) [soak] NET_FLAP: restored"
  else
    echo "$(ts) [soak] NET_FLAP: FAILED to apply iptables (skipping)"
  fi
}

inject_disk_pressure() {
  local day_dir="$1"
  local filler="$day_dir/.filler.bin"
  echo "$(ts) [soak] DISK_PRESS: Creating ${DISK_PRESS_SIZE_GB}GB filler"
  fallocate -l "${DISK_PRESS_SIZE_GB}G" "$filler" 2>/dev/null || dd if=/dev/zero of="$filler" bs=1M count=$((DISK_PRESS_SIZE_GB*1024)) status=none || true
  sleep 10
  rm -f "$filler"
  echo "$(ts) [soak] DISK_PRESS: Removed filler"
}

inject_restart() {
  local pid="$1"
  echo "$(ts) [soak] RESTART: Sending SIGTERM to child"
  kill -TERM "$pid" || true
}

monitor_child() {
  local child_pid="$1" end_epoch="$2" restarts_file="$3" log_file="$4"
  local restarted=0
  while [[ "$(date +%s)" -lt "$end_epoch" ]]; do
    if ! kill -0 "$child_pid" 2>/dev/null; then
      echo "$(ts) [soak] Child process exited unexpectedly. Restarting..."
      echo "$(ts) restart" >> "$restarts_file"
      # restart child
      ( cd "$ROOT_DIR" && bash -lc "$RUN_CMD" ) >> "$log_file" 2>&1 &
      child_pid=$!
      restarted=$((restarted+1))
    fi
    sleep 5
  done
  echo "$child_pid"
}

collect_report() {
  local day_iso="$1" day_dir="$2" log_file="$3" restarts_file="$4"
  local out_dir="$REPORTS_DIR/$day_iso"
  mkdir -p "$out_dir"

  # Copy orchestrator log
  cp -f "$log_file" "$out_dir/orchestrator.log"

  # Collate app logs produced under RUNS_DIR for this day (if your app writes runs/YYYY-MM-DD/)
  # We gather any files modified on that date into a tarball for convenience.
  local tarlist="$day_dir/_tarlist.txt"
  find "$RUNS_DIR" -type f -newermt "${day_iso} 00:00:00" ! -newermt "${day_iso} 23:59:59" > "$tarlist" || true
  if [[ -s "$tarlist" ]]; then
    tar -czf "$out_dir/app_artifacts.tgz" -T "$tarlist" || true
  fi

  # Generate daily report (Markdown + JSON)
  "$PYTHON_BIN" tools/soak_report.py \
    --runs-dir "$RUNS_DIR" \
    --day "$day_iso" \
    --orchestrator-log "$log_file" \
    --restarts-log "$restarts_file" \
    --out-dir "$out_dir" || echo "[soak] WARN: soak_report.py failed"
}

main() {
  check_prereqs

  echo "[soak] Starting 2-week paper soak ($SOAK_DAYS days)."
  for (( d=1; d<=SOAK_DAYS; d++ )); do
    local day_iso
    day_iso="$(date -u +%F)" # YYYY-MM-DD UTC
    local day_dir="$SOAK_DIR/$day_iso"
    mkdir -p "$day_dir"
    local log_file="$LOG_DIR/${day_iso}.log"
    local restarts_file="$day_dir/restarts.log"
    : > "$log_file"
    : > "$restarts_file"

    echo "$(ts) [soak] DAY $d/$SOAK_DAYS started. Logs: $log_file"

    local end_epoch=$(( $(date +%s) + DAY_RUNTIME_SEC ))

    # Start child
    local child_pid=""
    local tmux_session=""
    if [[ "$USE_TMUX" == "1" ]]; then
      tmux_session="$(start_session_tmux "$day_dir" "$log_file")"
      # best-effort: find child PID for signals (optional)
      sleep 2
      child_pid="$(pgrep -f "$RUN_CMD" | head -n1 || true)"
    else
      child_pid="$(start_session_fork "$day_dir" "$log_file")"
    fi
    if [[ -z "${child_pid}" ]]; then
      echo "[soak] WARN: could not determine child PID; restart injection will be skipped."
    fi

    # Schedule injections (background), all optional and safe-off by default
    if [[ "$INJECT_NET_FLAP" == "1" ]]; then
      ( sleep "$NET_FLAP_AFTER_SEC"; inject_net_flap ) >> "$log_file" 2>&1 &
    fi
    if [[ "$INJECT_DISK_PRESS" == "1" ]]; then
      ( sleep "$DISK_PRESS_AFTER_SEC"; inject_disk_pressure "$day_dir" ) >> "$log_file" 2>&1 &
    fi
    if [[ "$INJECT_RESTART" == "1" && -n "${child_pid:-}" ]]; then
      ( sleep "$RESTART_AFTER_SEC"; inject_restart "$child_pid" ) >> "$log_file" 2>&1 &
    fi

    # Monitor child until end-of-day; restart if it crashes
    if [[ -n "${child_pid:-}" && "$USE_TMUX" == "0" ]]; then
      child_pid="$(monitor_child "$child_pid" "$end_epoch" "$restarts_file" "$log_file")"
    else
      # if using tmux we can't easily monitor; we just wait for end-of-day
      while [[ "$(date +%s)" -lt "$end_epoch" ]]; do sleep 5; done
    fi

    # Stop child gracefully at end-of-day
    if [[ "$USE_TMUX" == "1" && -n "$tmux_session" ]]; then
      tmux send-keys -t "$tmux_session" C-c || true
      sleep 3
      tmux kill-session -t "$tmux_session" || true
    elif [[ -n "${child_pid:-}" ]]; then
      kill -TERM "$child_pid" 2>/dev/null || true
      sleep 5
      kill -KILL "$child_pid" 2>/dev/null || true
    fi

    # Collect and generate the daily report
    collect_report "$day_iso" "$day_dir" "$log_file" "$restarts_file"
    echo "$(ts) [soak] DAY $d/$SOAK_DAYS complete. Report: $REPORTS_DIR/$day_iso"
    # Wait until date flips to avoid overlapping day windows
    while [[ "$(date -u +%F)" == "$day_iso" ]]; do sleep 5; done
  done

  echo "[soak] Completed $SOAK_DAYS-day soak."
}

main "$@"