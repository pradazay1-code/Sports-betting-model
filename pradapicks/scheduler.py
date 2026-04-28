"""APScheduler jobs — runs in-process when RUN_SCHEDULER=true."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import get_settings
from .db import SessionLocal
from .ingest import ingest_box_scores, ingest_odds
from .models.trainer import train_all
from .picks import generate_daily_picks
from .tracker import grade_picks

log = logging.getLogger(__name__)


def _job_morning_picks() -> None:
    with SessionLocal() as db:
        ingest_odds(db, on=date.today())
        picks = generate_daily_picks(db, on=date.today())
        log.info("generated %d picks for %s", len(picks), date.today())


def _job_grade_yesterday() -> None:
    with SessionLocal() as db:
        ingest_box_scores(db, date.today() - timedelta(days=1))
        result = grade_picks(db, on=date.today() - timedelta(days=1))
        log.info("graded: %s", result)


def _job_nightly_retrain() -> None:
    with SessionLocal() as db:
        results = train_all(db)
        log.info("retrained %d (sport,market) pairs", len(results))


def _job_refresh_odds() -> None:
    with SessionLocal() as db:
        n = ingest_odds(db, on=date.today())
        log.info("refreshed %d offers", n)


def start_scheduler() -> BackgroundScheduler | None:
    settings = get_settings()
    if not settings.run_scheduler:
        return None
    sched = BackgroundScheduler(timezone=settings.tz)
    # Morning: ingest odds + publish daily top-25
    sched.add_job(_job_morning_picks, CronTrigger(hour=9, minute=0), id="morning_picks", replace_existing=True)
    # Mid-day refresh of odds (lines move)
    sched.add_job(_job_refresh_odds, CronTrigger(hour="11,14,17", minute=15), id="refresh_odds", replace_existing=True)
    # Nightly: ingest yesterday's box scores + grade yesterday's picks
    sched.add_job(_job_grade_yesterday, CronTrigger(hour=4, minute=0), id="grade_yesterday", replace_existing=True)
    # Nightly retrain after grading completes
    sched.add_job(_job_nightly_retrain, CronTrigger(hour=5, minute=0), id="retrain", replace_existing=True)
    sched.start()
    log.info("scheduler started in tz=%s", settings.tz)
    return sched
