"""First-boot bootstrap: backfill historical box scores + train models.

Called from FastAPI startup. Runs in a daemon thread so it never blocks the
HTTP server. Safe to call repeatedly — it no-ops once data exists.
"""
from __future__ import annotations

import logging
import threading
from datetime import date

from sqlalchemy import select

from .db import PlayerGameStat, SessionLocal
from .ingest import backfill_box_scores, ingest_odds
from .models.trainer import train_all
from .picks import generate_daily_picks

log = logging.getLogger(__name__)


def needs_bootstrap() -> bool:
    with SessionLocal() as db:
        any_row = db.execute(select(PlayerGameStat).limit(1)).first()
        return any_row is None


def run_bootstrap(days: int = 30) -> None:
    log.info("bootstrap: backfilling %d days of box scores", days)
    with SessionLocal() as db:
        try:
            backfill_box_scores(db, days=days)
        except Exception:
            log.exception("bootstrap backfill failed")
        try:
            log.info("bootstrap: training models")
            train_all(db)
        except Exception:
            log.exception("bootstrap training failed")
        try:
            log.info("bootstrap: pulling odds + generating today's picks")
            ingest_odds(db, on=date.today())
            generate_daily_picks(db, on=date.today())
        except Exception:
            log.exception("bootstrap odds/picks failed")
    log.info("bootstrap: done")


def kick_off_bootstrap_if_needed(days: int = 30) -> None:
    if not needs_bootstrap():
        log.info("bootstrap: skipping (data already present)")
        return
    t = threading.Thread(target=run_bootstrap, args=(days,), name="pradapicks-bootstrap", daemon=True)
    t.start()
    log.info("bootstrap: kicked off in background thread")
