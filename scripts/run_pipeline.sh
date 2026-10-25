#!/usr/bin/env bash
# Run the M&A pipeline with logging, a lock file and a non-zero exit code on failure.
# Suitable for cron:  0 7 * * 1  /path/to/mna-deal-tracker/scripts/run_pipeline.sh >> /dev/null 2>&1
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

LOCK_FILE="/tmp/mna-deal-tracker.lock"
LOG_DIR="data/logs"
mkdir -p "$LOG_DIR"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [run_pipeline] $*"; }

# Prevent two runs from writing to the database at the same time.
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    log "Another run is in progress; exiting."
    exit 0
fi

# Use the project virtualenv when it exists.
if [[ -f ".venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

if [[ -z "${SEC_USER_AGENT:-}" ]]; then
    log "WARNING: SEC_USER_AGENT is not set. SEC requires 'Name email@example.com'."
fi

log "Starting pipeline (args: ${*:-none})"
start=$(date +%s)
if python -m mna_tracker.pipeline "$@"; then
    log "Finished successfully in $(( $(date +%s) - start ))s"
else
    status=$?
    log "Pipeline FAILED with exit code $status (see $LOG_DIR/pipeline.log)"
    exit "$status"
fi
