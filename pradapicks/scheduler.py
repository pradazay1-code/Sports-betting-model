"""APScheduler jobs + self-keepalive.

Aggressive refresh policy: odds + picks every 30 min, today's box scores
ingested every hour, retraining nightly, grading after 4am.

Self-keepalive: if RENDER_EXTERNAL_URL (Render's auto-injected env var) or
SELF_URL is set, a background thread pings /health every 10 minutes to
prevent the free-tier instance from sleeping after 15 min of idle.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import date, timedelta

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .config import get_settings
from .db import SessionLocal
from .ingest import ingest_box_scores, ingest_odds
from .models.trainer import train_all
from .picks import generate_daily_picks
from .tracker import grade_picks

log = logging.getLogger(__name__)


# --- jobs ---------------------------------------------------------------

def _job_refresh_odds_and_picks() -> None:
    """Every 30 min: pull fresh odds and regenerate today's top-25."""
    with SessionLocal() as db:
        try:
            n = ingest_odds(db, on=date.today())
            log.info("scheduler.refresh: %d offers", n)
        except Exception:
            log.exception("scheduler.refresh: odds failed")
        try:
            picks = generate_daily_picks(db, on=date.today())
            log.info("scheduler.refresh: regenerated %d picks", len(picks))
        except Exception:
            log.exception("scheduler.refresh: picks failed")


def _job_ingest_today_box_scores() -> None:
    """Every hour: pull today's box scores so in-progress / final games update."""
    with SessionLocal() as db:
        try:
            ingest_box_scores(db, date.today())
        except Exception:
            log.exception("scheduler.box-scores-today: failed")


def _job_grade_yesterday_and_retrain() -> None:
    """Every night at 4am: ingest yesterday's results, grade picks, retrain."""
    with SessionLocal() as db:
        try:
            ingest_box_scores(db, date.today() - timedelta(days=1))
        except Exception:
            log.exception("scheduler.grade-night: ingest failed")
        try:
            result = grade_picks(db, on=date.today() - timedelta(days=1))
            log.info("scheduler.grade-night: %s", result)
        except Exception:
            log.exception("scheduler.grade-night: grade failed")
        try:
            train_all(db)
        except Exception:
            log.exception("scheduler.grade-night: retrain failed")


# --- self-keepalive ------------------------------------------------------

def _self_url() -> str | None:
    # Render auto-injects RENDER_EXTERNAL_URL on web services.
    return os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("SELF_URL")


def _keepalive_loop() -> None:
    url = _self_url()
    if not url:
        return
    target = url.rstrip("/") + "/health"
    log.info("keepalive: pinging %s every 10 min", target)
    while True:
        time.sleep(600)
        try:
            httpx.get(target, timeout=10)
        except Exception as e:
            log.debug("keepalive ping failed: %s", e)


def _start_keepalive() -> None:
    if _self_url():
        threading.Thread(target=_keepalive_loop, name="keepalive", daemon=True).start()


# --- entrypoint ---------------------------------------------------------

def start_scheduler() -> BackgroundScheduler | None:
    settings = get_settings()
    if not settings.run_scheduler:
        return None
    sched = BackgroundScheduler(timezone=settings.tz)
    # High-cadence refresh: every 30 min.
    sched.add_job(
        _job_refresh_odds_and_picks,
        IntervalTrigger(minutes=30),
        id="refresh_30m",
        replace_existing=True,
    )
    # Hourly ingest of today's in-progress games.
    sched.add_job(
        _job_ingest_today_box_scores,
        IntervalTrigger(hours=1),
        id="ingest_today_1h",
        replace_existing=True,
    )
    # Nightly grade + retrain at 4am.
    sched.add_job(
        _job_grade_yesterday_and_retrain,
        CronTrigger(hour=4, minute=0),
        id="grade_retrain_nightly",
        replace_existing=True,
    )
    sched.start()
    _start_keepalive()
    log.info("scheduler started (tz=%s)", settings.tz)
    return sched
