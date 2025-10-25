# Deployment & Operations Playbook (Phase 10)

Phase 10 packages Logos for predictable day-two operations: containerized deployment, basic monitoring, and backup hygiene. This runbook summarizes the workflow for provisioning, observing, and maintaining the stack.

## Compose Stack

```
cd deploy
cp .env.example .env  # adjust secrets and thresholds
docker compose up -d
```

Services:
- `runner` – executes paper/adapters according to `RUNNER_CMD` (defaults to `python -m logos.run --mode paper`).
- `monitor` – runs `scripts/ops/monitor.py` on a configurable interval; emits webhook alerts.
- `backup` – executes `scripts/ops/backup.sh` on the cadence defined by `BACKUP_INTERVAL`.
- `janitor` – prunes stale run artifacts and rotated logs per retention variables.

Volumes:
- `runs_data`, `configs_data`, `logs_data`, `backups_data` persist cross-container state.

## Environment & Secrets

Populate `deploy/.env` from the template:
- `RUNNER_CMD` controls the orchestration command the runner executes.
- `LOGOS_ALERT_WEBHOOK` / `LOGOS_ALERT_CHANNEL` configure Slack/Telegram style incoming webhooks. Leave blank to run in dry-run mode.
- `LOGOS_SENTINEL_FILE`, `LOGOS_SENTINEL_STALE_SECONDS`, `LOGOS_DISK_THRESHOLD` tune monitor thresholds.
- `BACKUP_DEST`, `BACKUP_INTERVAL`, `BACKUP_RETENTION_DAYS` govern backup cadence and rotation.
- `JANITOR_INTERVAL`, `JANITOR_KEEP_DAYS`, `JANITOR_LOG_RETENTION_DAYS` manage janitor cadence and retention windows.

Store API keys and adapter credentials outside the repo (e.g., Docker secrets, bind-mounted files). Point the runner to those paths via additional environment variables or config presets.

## Monitoring & Alerts

`scripts/ops/monitor.py` performs three checks each cycle:
1. Sentinel file freshness – verifies the configured heartbeat file is updated within the accepted age.
2. Disk pressure – alerts when disk usage over `LOGOS_DISK_THRESHOLD` percent.
3. Error detection – tails the configured log for new `ERROR` or `Traceback` entries since the previous cycle.

Alerts post to the webhook provided; otherwise messages print to stdout for testing. Adjust polling cadence with `MONITOR_INTERVAL`.

## Backup & Restore

Backups land in `BACKUP_DEST` with timestamped archives containing `runs/` and `configs/`.

Manual execution:
```
./scripts/ops/backup.sh
./scripts/ops/restore.sh backups/logos_backup_20250101_120000.tar.gz ./restore_target
```

The backup service honors `BACKUP_INTERVAL` (seconds) and prunes archives older than `BACKUP_RETENTION_DAYS`.

## Janitor Hygiene

`./scripts/ops/janitor.sh` removes run directories older than `JANITOR_KEEP_DAYS` and log files older than `JANITOR_LOG_RETENTION_DAYS`. The compose service executes the script on the configured interval.

## Operational Drills

- **Two-week soak**: run the compose stack in paper mode for 14 days, confirm backups accumulate daily and janitor rotation keeps the footprint bounded. Monitor alerts should remain quiet; each triggered alert is investigated and documented.
- **Quarterly restart drill**: once per quarter, tear down the stack (`docker compose down`), restore from the most recent backup, and verify the runner resumes deterministic execution with identical configs. Document the drill in `docs/OPS.md` or team wiki.
- **Webhook validation**: prior to go-live, trigger a manual alert (e.g., stop updating the sentinel file) to ensure notification channels reach the correct on-call destination.

## Troubleshooting Cheatsheet

- `docker compose logs -f monitor` – inspect alert reasons and stack traces within the monitor loop.
- `docker compose run --rm runner python scripts/ops/monitor.py` – run checks once in dry-run mode.
- `find runs -maxdepth 1 -type d` – verify janitor retention settings locally before widening intervals.
- Ensure scripts remain executable (`chmod +x scripts/ops/*.sh`) after cloning on new hosts.
