"""First-boot bootstrap — split into two concurrent passes.

Pass A (fast, ~1-3 min): pull a small recent window of box scores, train
whatever markets have enough rows, fetch live odds, publish today's picks.
This makes the dashboard usable within minutes of deploy.

Pass B (slow, ~10-30 min): 30-day historical backfill running in parallel,
then a final retrain when it finishes for higher-quality models.

Both run in daemon threads so the HTTP server is never blocked.
"""
from __future__ import annotations

import logging
import threading
from datetime import date, timedelta

from sqlalchemy import select

from .db import PlayerGameStat, SessionLocal
from .ingest import ingest_box_scores, ingest_odds
from .models.trainer import train_all
from .picks import generate_daily_picks

log = logging.getLogger(__name__)

_state = {"fast_done": False, "slow_done": False, "started": False}


def status() -> dict:
    return dict(_state)


def needs_bootstrap() -> bool:
    with SessionLocal() as db:
        any_row = db.execute(select(PlayerGameStat).limit(1)).first()
        return any_row is None


def _fast_pass() -> None:
    """Pull last 7 days of box scores, train, fetch odds, publish picks."""
    log.info("bootstrap.fast: starting")
    try:
        with SessionLocal() as db:
            today = date.today()
            for i in range(1, 8):
                d = today - timedelta(days=i)
                try:
                    ingest_box_scores(db, d)
                except Exception:
                    log.exception("bootstrap.fast: ingest %s failed", d)
            try:
                train_all(db)
            except Exception:
                log.exception("bootstrap.fast: training failed")
            try:
                ingest_odds(db, on=today)
                generate_daily_picks(db, on=today)
            except Exception:
                log.exception("bootstrap.fast: odds/picks failed")
    finally:
        _state["fast_done"] = True
        log.info("bootstrap.fast: done")


def _slow_pass(days: int) -> None:
    """Continue the 30-day backfill, retraining at the end."""
    log.info("bootstrap.slow: backfilling %d days", days)
    try:
        with SessionLocal() as db:
            today = date.today()
            for i in range(8, days + 1):
                d = today - timedelta(days=i)
                try:
                    ingest_box_scores(db, d)
                except Exception:
                    log.exception("bootstrap.slow: ingest %s failed", d)
            try:
                train_all(db)
            except Exception:
                log.exception("bootstrap.slow: retrain failed")
            try:
                ingest_odds(db, on=today)
                generate_daily_picks(db, on=today)
            except Exception:
                log.exception("bootstrap.slow: odds/picks refresh failed")
    finally:
        _state["slow_done"] = True
        log.info("bootstrap.slow: done")


def kick_off_bootstrap_if_needed(days: int = 30) -> None:
    if _state["started"]:
        log.info("bootstrap: already started")
        return
    _state["started"] = True
    threading.Thread(target=_fast_pass, name="pradapicks-fast", daemon=True).start()
    threading.Thread(target=_slow_pass, args=(days,), name="pradapicks-slow", daemon=True).start()
    log.info("bootstrap: kicked off fast + slow passes")


# Back-compat shim
def run_bootstrap(days: int = 30) -> None:
    _fast_pass()
    _slow_pass(days)
