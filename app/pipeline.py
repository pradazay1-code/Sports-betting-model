"""Pipeline runners — invoked from GitHub Actions.

Each is a thin orchestrator. They mutate the DB and then write JSON snapshots
into docs/ so the static dashboard has something to read after the workflow
commits.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path

from app.config import CFG, SPORTS, MARKETS
from app.ingest import backfill, ingest_date, ingest_today_context
from app.models.trainer import train_all
from app.picks import generate
from app.sources.odds import fetch_all as fetch_odds_all
from app.store import (
    connection,
    fetch_picks_on,
    fetch_games_on,
    init_db,
)
from app.tracker import grade, history
from app.utils import get_logger, now_iso, today_local

LOG = get_logger("pipeline")


def _summary_payload(on_date: str) -> dict:
    picks = fetch_picks_on(on_date)
    games_by_sport = {s: fetch_games_on(s, on_date) for s in SPORTS}
    return {
        "generated_at": now_iso(),
        "on_date": on_date,
        "picks": [_pick_dict(p) for p in picks],
        "by_sport": {s: [_game_dict(g) for g in games] for s, games in games_by_sport.items()},
        "history_30d": history(days=30),
        "model_summary": _model_summary(),
    }


def _pick_dict(p: dict) -> dict:
    out = dict(p)
    try:
        out["rationale"] = json.loads(out["rationale"]) if out.get("rationale") else {}
    except Exception:
        pass
    out["recommended_stake_units"] = round(out.get("kelly_stake", 0.0) * CFG.bankroll, 2)
    return out


def _game_dict(g: dict) -> dict:
    out = dict(g)
    try:
        out["extra"] = json.loads(out["extra"]) if out.get("extra") else {}
    except Exception:
        pass
    return out


def _model_summary() -> list[dict]:
    with connection() as conn:
        rows = [dict(r) for r in conn.execute(
            """SELECT sport, market, MAX(finished_at) finished_at,
                      rows, mae, brier, log_loss
               FROM model_runs
               GROUP BY sport, market
               ORDER BY sport, market"""
        ).fetchall()]
    return rows


def write_dashboard_json(on_date: str) -> None:
    CFG.docs_dir.mkdir(parents=True, exist_ok=True)
    payload = _summary_payload(on_date)
    (CFG.docs_dir / "picks.json").write_text(json.dumps(payload, indent=2, default=str))
    (CFG.docs_dir / "latest.json").write_text(json.dumps({
        "on_date": on_date,
        "generated_at": payload["generated_at"],
        "n_picks": len(payload["picks"]),
        "n_games": sum(len(v) for v in payload["by_sport"].values()),
    }, indent=2))


# ---- entry points used by workflows ------------------------------------


def run_daily_picks() -> None:
    init_db()
    on = today_local()
    LOG.info("daily_picks: starting for %s", on)
    # Light context refresh so the dashboard shows today's games + injuries.
    ingest_today_context(on)
    fetch_odds_all()
    generate(on.isoformat())
    write_dashboard_json(on.isoformat())


def run_odds_refresh() -> None:
    init_db()
    on = today_local()
    LOG.info("odds_refresh: %s", on)
    fetch_odds_all()
    generate(on.isoformat())
    write_dashboard_json(on.isoformat())


def run_nightly() -> None:
    """Ingest yesterday's finals, grade, retrain. Runs ~04:00 ET."""
    init_db()
    yesterday = today_local() - timedelta(days=1)
    LOG.info("nightly: ingesting/grading %s", yesterday)
    ingest_date(yesterday)
    grade(yesterday.isoformat())
    train_all()
    # And generate today's picks fresh after retrain.
    fetch_odds_all()
    generate(today_local().isoformat())
    write_dashboard_json(today_local().isoformat())


def run_bootstrap(days: int | None = None) -> None:
    """One-time backfill + initial train + first picks."""
    init_db()
    days = days or CFG.backfill_days
    LOG.info("bootstrap: backfilling %d days", days)
    backfill(days)
    train_all()
    fetch_odds_all()
    generate(today_local().isoformat())
    write_dashboard_json(today_local().isoformat())


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "daily"
    arg = sys.argv[2] if len(sys.argv) > 2 else None
    if cmd == "daily":      run_daily_picks()
    elif cmd == "odds":     run_odds_refresh()
    elif cmd == "nightly":  run_nightly()
    elif cmd == "bootstrap": run_bootstrap(int(arg) if arg else None)
    else: raise SystemExit(f"unknown command: {cmd}")
