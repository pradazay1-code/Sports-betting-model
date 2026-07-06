"""Pulse Engine entry point — starts collectors, scheduler and dashboard.

    python run.py            # everything
    python run.py --no-web   # collectors + engine only

Then open http://localhost:8777. Automated trading is NOT part of this
system (Phases 0–8 are research/paper-trade only).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import logging.handlers
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import storage


def setup_logging() -> None:
    root = logging.getLogger()
    root.setLevel(config.LOG_LEVEL)
    fmt = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    fh = logging.handlers.RotatingFileHandler(
        config.LOGS_DIR / "pulse.log", maxBytes=10 * 2 ** 20, backupCount=5)
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(fh)
    root.addHandler(sh)
    logging.getLogger("apscheduler").setLevel("WARNING")
    logging.getLogger("uvicorn.access").setLevel("WARNING")


async def main(serve_web: bool = True) -> None:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    from collectors.kalshi_client import KalshiPoller
    from collectors.news_collector import NewsCollector
    from collectors.price_collector import PriceCollector
    from dashboard.server import Runtime, create_app
    from engine.learner import adapt_threshold, error_analysis, grade_pending, maybe_retrain
    from engine.predictor import Predictor

    log = logging.getLogger("pulse")
    storage.init_db()

    prices = PriceCollector()
    kalshi = KalshiPoller()
    news = NewsCollector()
    predictor = Predictor(price_cache=prices.cache, kalshi_cache=kalshi.cache,
                          news_cache=news.cache)

    tasks = [
        asyncio.create_task(prices.run(), name="prices"),
        asyncio.create_task(kalshi.run(), name="kalshi"),
        asyncio.create_task(news.run(), name="news"),
    ]

    # Scheduler: all times UTC; window boundaries align to quarter hours in
    # UTC and ET alike, so minute marks are exact year-round. Jobs are plain
    # sync callables — AsyncIOScheduler runs them in its thread executor, so
    # the event loop (collectors, dashboard) is never blocked.
    sched = AsyncIOScheduler(timezone="UTC")
    pred_min = ",".join(str((m + config.PREDICTION_DELAY_SECONDS // 60) % 60)
                        for m in (0, 15, 30, 45))
    pred_sec = config.PREDICTION_DELAY_SECONDS % 60
    sched.add_job(predictor.run_window,
                  CronTrigger(minute=pred_min, second=pred_sec),
                  name="predict", misfire_grace_time=120)
    sched.add_job(grade_pending,
                  CronTrigger(minute="0,15,30,45", second=config.GRADE_DELAY_SECONDS),
                  name="grade", misfire_grace_time=300)
    sched.add_job(adapt_threshold,
                  CronTrigger(minute="7,22,37,52"), name="adapt-threshold",
                  misfire_grace_time=300)
    sched.add_job(error_analysis,
                  CronTrigger(hour=10, minute=5), name="error-analysis",  # ~6am ET
                  misfire_grace_time=3600)
    sched.add_job(maybe_retrain,
                  CronTrigger(minute=11), name="retrain-check",
                  misfire_grace_time=600)
    sched.start()
    log.info("scheduler started: predict @ :%s+%02ds, grade @ +%02ds",
             pred_min, pred_sec, config.GRADE_DELAY_SECONDS)

    server = None
    if serve_web:
        import uvicorn
        app = create_app(Runtime(price_cache=prices.cache, kalshi_cache=kalshi.cache,
                                 news_cache=news.cache, predictor=predictor))
        server = uvicorn.Server(uvicorn.Config(
            app, host=config.DASHBOARD_HOST, port=config.DASHBOARD_PORT,
            log_level="warning"))
        tasks.append(asyncio.create_task(server.serve(), name="dashboard"))
        log.info("dashboard: http://%s:%d", config.DASHBOARD_HOST, config.DASHBOARD_PORT)

    try:
        await asyncio.gather(*tasks)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        log.info("shutting down")
        sched.shutdown(wait=False)
        prices.stop()
        kalshi.stop()
        news.stop()
        if server:
            server.should_exit = True
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--no-web", action="store_true")
    args = p.parse_args()
    setup_logging()
    try:
        asyncio.run(main(serve_web=not args.no_web))
    except KeyboardInterrupt:
        pass
