#!/usr/bin/env bash
# Pulse Engine 24/7 supervisor: restarts run.py if it ever exits/crashes.
# Usage:  bash scripts/run_forever.sh
# Stop:   Ctrl+C (twice within 5s), or:  pkill -f run_forever; pkill -f run.py
set -u
cd "$(dirname "$0")/.."
if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
mkdir -p logs
echo "[run_forever] starting Pulse Engine supervisor (logs/run.out)"
LAST_EXIT=0
while true; do
  python run.py >> logs/run.out 2>&1
  LAST_EXIT=$?
  echo "[run_forever] run.py exited ($LAST_EXIT) at $(date) — restarting in 10s" | tee -a logs/run.out
  sleep 10
done
