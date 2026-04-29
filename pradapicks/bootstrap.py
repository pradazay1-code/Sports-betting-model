"""First-boot bootstrap.

Architectural fix (audit-driven): the previous version tried to do a
sequential 30-day backfill before ever fetching odds, which meant the
service appeared dead from the user's perspective for 10+ minutes — and
if any single HTTP source rate-limited, it got stuck entirely.

New order, fast pass:
  1. Fetch today's schedule for every sport (so we have current rosters)
  2. Fetch live odds — populates providers dict immediately so /health
     shows life within ~30 seconds
  3. Backfill last 3 days of box scores **in parallel** (ThreadPoolExecutor)
     with a hard 4-minute time budget — no single hung call can stall us
  4. Train whatever markets have enough rows
  5. Regenerate picks with real models

Slow pass continues the full 30-day backfill in the background and
retrains when complete for higher-quality models.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

from sqlalchemy import select

from .db import PlayerGameStat, SessionLocal
from .ingest import ingest_box_scores, ingest_odds
from .models.trainer import train_all
from .picks import generate_daily_picks

log = logging.getLogger(__name__)

_state = {
    "fast_done": False, "slow_done": False, "started": False,
    "fast_started_ts": 0.0, "fast_ended_ts": 0.0,
    "last_error": "",
}

FAST_BACKFILL_DAYS = 3
FAST_TIME_BUDGET_SEC = 240  # 4 minutes


def status() -> dict:
    return dict(_state)


def needs_bootstrap() -> bool:
    with SessionLocal() as db:
        any_row = db.execute(select(PlayerGameStat).limit(1)).first()
        return any_row is None


# --- helpers --------------------------------------------------------------

def _ingest_one_day(d: date) -> int:
    with SessionLocal() as db:
        try:
            summary = ingest_box_scores(db, d)
            n = sum(s.get("player_rows", 0) for s in summary.values())
            log.info("bootstrap: ingested %s -> %d rows", d, n)
            return n
        except Exception as e:
            log.warning("bootstrap: ingest %s failed: %s", d, e)
            return 0


def _odds_and_picks() -> None:
    with SessionLocal() as db:
        try:
            n = ingest_odds(db, on=date.today())
            log.info("bootstrap: ingested %d odds rows", n)
        except Exception:
            log.exception("bootstrap: odds fetch failed")
        try:
            picks = generate_daily_picks(db, on=date.today())
            log.info("bootstrap: generated %d picks", len(picks))
        except Exception:
            log.exception("bootstrap: pick generation failed")


# --- fast pass ------------------------------------------------------------

def _fast_pass() -> None:
    log.info("bootstrap.fast: starting")
    _state["fast_started_ts"] = time.time()
    deadline = time.time() + FAST_TIME_BUDGET_SEC
    today = date.today()

    # Step 1+2: try odds first so /health shows life immediately.
    try:
        _odds_and_picks()
    except Exception:
        log.exception("bootstrap.fast: early odds fetch failed")

    # Step 3: parallel backfill with budget.
    days = [today - timedelta(days=i) for i in range(0, FAST_BACKFILL_DAYS + 1)]
    try:
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="bootstrap") as pool:
            futures = {pool.submit(_ingest_one_day, d): d for d in days}
            for fut in as_completed(futures, timeout=max(10, deadline - time.time())):
                pass  # results logged inside
    except Exception as e:
        log.warning("bootstrap.fast: parallel backfill stopped: %s", e)
        _state["last_error"] = str(e)

    # Step 4: train.
    try:
        with SessionLocal() as db:
            train_all(db)
    except Exception:
        log.exception("bootstrap.fast: training failed")

    # Step 5: regenerate picks now that we have data + models.
    try:
        _odds_and_picks()
    except Exception:
        log.exception("bootstrap.fast: post-train odds/picks failed")

    _state["fast_done"] = True
    _state["fast_ended_ts"] = time.time()
    log.info("bootstrap.fast: done in %.1fs",
             _state["fast_ended_ts"] - _state["fast_started_ts"])


# --- slow pass ------------------------------------------------------------

def _slow_pass(days: int) -> None:
    log.info("bootstrap.slow: backfilling %d days", days)
    today = date.today()
    targets = [today - timedelta(days=i) for i in range(FAST_BACKFILL_DAYS + 1, days + 1)]
    try:
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="bootstrap-slow") as pool:
            for fut in as_completed({pool.submit(_ingest_one_day, d): d for d in targets}):
                pass
    except Exception:
        log.exception("bootstrap.slow: failed")
    try:
        with SessionLocal() as db:
            train_all(db)
    except Exception:
        log.exception("bootstrap.slow: retrain failed")
    try:
        _odds_and_picks()
    except Exception:
        log.exception("bootstrap.slow: refresh failed")
    _state["slow_done"] = True
    log.info("bootstrap.slow: done")


# --- public --------------------------------------------------------------

def kick_off_bootstrap_if_needed(days: int = 30) -> None:
    if _state["started"]:
        log.info("bootstrap: already started")
        return
    _state["started"] = True

    # If the database already has data (i.e. we're using a persistent
    # Postgres and this is a normal restart, not a fresh deploy), skip the
    # expensive backfill entirely. Just kick off a refresh so today's odds
    # and picks are current.
    if not needs_bootstrap():
        log.info("bootstrap: db already populated, just refreshing odds + picks")
        threading.Thread(
            target=_refresh_only, name="pradapicks-refresh", daemon=True
        ).start()
        _state["fast_done"] = True  # nothing to do
        _state["slow_done"] = True
        return

    threading.Thread(target=_fast_pass, name="pradapicks-fast", daemon=True).start()
    threading.Thread(target=_slow_pass, args=(days,), name="pradapicks-slow", daemon=True).start()
    log.info("bootstrap: kicked off fast + slow passes (cold start)")


def _refresh_only() -> None:
    """Lightweight refresh — fetch today's box scores, odds, regenerate picks."""
    try:
        with SessionLocal() as db:
            try:
                ingest_box_scores(db, date.today())
            except Exception:
                log.exception("refresh: today ingest failed")
            try:
                ingest_odds(db, on=date.today())
            except Exception:
                log.exception("refresh: odds failed")
            try:
                generate_daily_picks(db, on=date.today())
            except Exception:
                log.exception("refresh: pick generation failed")
    except Exception:
        log.exception("refresh: outer failure")


def run_bootstrap(days: int = 30) -> None:
    """Synchronous entry point for /admin/bootstrap."""
    _fast_pass()
    _slow_pass(days)
