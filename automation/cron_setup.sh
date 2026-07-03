#!/usr/bin/env bash
# Edge Engine — cron schedule per sport's information rhythm (spec §7).
# BUILD PHASE 3 — the full pipeline these entries call is not built yet.
# Phase 1: only the odds pulls below are functional.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="python3"

read -r -d '' CRONTAB <<EOF || true
# ---- Edge Engine (times in ET; set CRON_TZ or adjust for your machine) ----
CRON_TZ=America/New_York
# 9:00 AM — overnight data pull, injury sweep, first scan
0 9 * * *  cd $REPO_DIR && $PY -m src.run_daily >> logs/daily.log 2>&1
# 11:30 AM — MLB lineups drop -> rerun + morning rundown        (Phase 2+)
30 11 * * * cd $REPO_DIR && $PY -m src.ingest.odds --pull >> logs/odds.log 2>&1
# 4:30 PM — NBA early lineup confirmations -> rerun             (Phase 4+)
30 16 * * * cd $REPO_DIR && $PY -m src.ingest.odds --pull >> logs/odds.log 2>&1
# 3:00 AM — grade yesterday, log closing lines, update CLV      (Phase 3+)
0 3 * * *  cd $REPO_DIR && $PY -m src.ingest.odds --pull >> logs/odds.log 2>&1
EOF

mkdir -p "$REPO_DIR/logs"
echo "$CRONTAB"
echo
read -r -p "Install these cron entries? [y/N] " yn
if [[ "$yn" == [Yy]* ]]; then
    (crontab -l 2>/dev/null | grep -v "Edge Engine" ; echo "$CRONTAB") | crontab -
    echo "installed."
else
    echo "skipped — copy the entries above into 'crontab -e' when ready."
fi
