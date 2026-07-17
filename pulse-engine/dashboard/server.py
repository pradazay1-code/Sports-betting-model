"""FastAPI dashboard backend.

Runs inside the run.py process and reads the live in-memory caches; it also
works standalone (`uvicorn dashboard.server:app`) in a degraded, DB-only
mode. Endpoints: /api/state, /api/history, /api/performance, /api/news,
/health — plus the static single-page UI at /.
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
import storage
from engine import edge as edge_mod
from engine import learner
from engine import window as win

log = logging.getLogger("pulse.dashboard")

STATIC_DIR = Path(__file__).resolve().parent / "static"


class Runtime:
    """Live objects wired in by run.py; None fields mean standalone mode."""

    def __init__(self, price_cache=None, kalshi_cache=None, news_cache=None,
                 predictor=None):
        self.price_cache = price_cache
        self.kalshi_cache = kalshi_cache
        self.news_cache = news_cache
        self.predictor = predictor
        self.started_at = time.time()


def create_app(runtime: Runtime | None = None) -> FastAPI:
    rt = runtime or Runtime()
    app = FastAPI(title="Pulse Engine", docs_url=None, redoc_url=None)

    @app.get("/health")
    def health():
        return {
            "ok": True, "uptime_s": int(time.time() - rt.started_at),
            "price_feed": bool(rt.price_cache and rt.price_cache.healthy()),
            "kalshi_feed": rt.kalshi_cache.status if rt.kalshi_cache else "standalone",
            "news_feed": rt.news_cache.status if rt.news_cache else "standalone",
        }

    @app.get("/api/state")
    def state():
        now = time.time()
        wstart, wclose = win.window_bounds(now)
        assets = {}
        for asset in config.ASSETS:
            tick = rt.price_cache.get(asset) if rt.price_cache else None
            spark_df = storage.get_candles(asset, int(now) - 3660, int(now))
            spark = [round(float(v), 6) for v in spark_df["close"].tolist()] \
                if not spark_df.empty else []
            # Current window open price (first candle at/after boundary).
            wopen = None
            if not spark_df.empty:
                pos = spark_df.index.searchsorted(wstart, side="left")
                if pos < len(spark_df):
                    wopen = float(spark_df.iloc[pos]["open"])
            price = tick.price if tick else (spark[-1] if spark else None)
            q = rt.kalshi_cache.quotes.get(asset) if rt.kalshi_cache else None
            q_current = q if q and q.window_close == wclose else None
            pred = (rt.predictor.last_run.get(asset) if rt.predictor else None) or {}
            if pred.get("window_start") != wstart:
                pred = {}
            if not pred:  # e.g. dashboard restarted mid-window — recover from DB
                row = storage.prediction_for(asset, wstart)
                if row:
                    pred = {"pick": row["pick"], "prob_up": row["prob_up"],
                            "implied_up": None, "edge": row["edge"],
                            "status": "ok", "reasons": []}
            assets[asset] = {
                "price": price,
                "tick_age_s": round(now - tick.ts, 1) if tick else None,
                "stale": (now - tick.ts > config.MAX_DATA_STALENESS_SECONDS)
                    if tick else True,
                "sparkline": spark[-60:],
                "window_open": wopen,
                "open_to_now": round(price / wopen - 1.0, 6)
                    if price and wopen else None,
                "kalshi": {
                    "ticker": q_current.ticker if q_current else None,
                    "yes_bid": q_current.yes_bid if q_current else None,
                    "yes_ask": q_current.yes_ask if q_current else None,
                    "implied_up": q_current.implied_up if q_current else None,
                    "url": f"https://kalshi.com/markets/{q_current.ticker.split('-')[0].lower()}"
                        if q_current and q_current.ticker else None,
                    "no_market": asset in rt.kalshi_cache.no_market
                        if rt.kalshi_cache else True,
                },
                "prediction": {
                    "pick": pred.get("pick"), "prob_up": pred.get("prob_up"),
                    "implied_up": pred.get("implied_up"), "edge": pred.get("edge"),
                    "status": pred.get("status"),
                    "reasons": pred.get("reasons", []),
                    "decided": pred.get("decided", True),
                    "kelly": pred.get("kelly"),
                    "arb_cents": pred.get("arb_cents"),
                    "scanned_at": pred.get("scanned_at"),
                    "raw_prob_up": pred.get("raw_prob_up"),
                    "breakdown": pred.get("breakdown"),
                    "next_window": pred.get("next_window"),
                    "slip": pred.get("slip"),
                } if pred else None,
            }
        # v2: live plays feed — every asset ranked by net margin right now.
        plays = []
        if rt.predictor:
            base_hurdle = config.kalshi_fee_per_contract(0.5) + storage.current_edge_buffer()
            for asset, r in rt.predictor.last_run.items():
                if r.get("window_start") != wstart:
                    continue
                pick = r.get("pick")
                edge_v = r.get("edge")
                slip = r.get("slip") or {}
                is_play = pick in ("UP", "DOWN") and r.get("decided")
                if is_play:
                    status, rank = f"PLAY {pick} — edge {edge_v * 100:+.1f} pts", 0
                elif slip.get("flagged"):
                    status = (f"SLIP {slip['expected_repricing_pts']:+.1f} pts — "
                              f"quote {slip['quote_age_s']}s stale")
                    rank = 1
                elif edge_v is not None:
                    short = (edge_v - base_hurdle) * 100
                    status, rank = f"{abs(short):.1f} pts short of a play", 2
                elif r.get("status") and r["status"] != "ok":
                    status, rank = r["status"], 4
                else:
                    status, rank = "no Kalshi quotes", 3
                plays.append({
                    "asset": asset, "pick": pick, "prob_up": r.get("prob_up"),
                    "edge": edge_v, "status": status, "is_play": is_play,
                    "slip_flagged": bool(slip.get("flagged")),
                    "kelly": r.get("kelly"),
                    "_rank": (rank, -(edge_v or -1))})
            plays.sort(key=lambda x: x.pop("_rank"))

        versions = {r["asset"]: r["version"] for r in reversed(storage.registry_rows())}
        last_retrain = max((r["trained_at"] for r in storage.registry_rows()), default=None)
        return {
            "now": now,
            "assets": assets,
            "plays": plays,
            "et_time": win.et_datetime(int(now)).strftime("%a %b %-d, %-I:%M:%S %p ET"),
            "window": {"start": wstart, "close": wclose,
                       "label": f"{win.et_label(wstart)}–{win.et_label(wclose)}",
                       "seconds_to_close": round(wclose - now, 1)},
            "feeds": {
                "prices": {
                    "status": "ok" if rt.price_cache and rt.price_cache.healthy()
                        else "down",
                    "source": rt.price_cache.source if rt.price_cache else None,
                    "stale_s": round(rt.price_cache.stale_seconds(), 1)
                        if rt.price_cache and rt.price_cache.ticks else None},
                "kalshi": {"status": rt.kalshi_cache.status if rt.kalshi_cache else "off",
                           "no_market": sorted(rt.kalshi_cache.no_market)
                               if rt.kalshi_cache else []},
                "news": {"status": rt.news_cache.status if rt.news_cache else "off",
                         "fng": rt.news_cache.fng if rt.news_cache else {}},
            },
            "learning": {
                "model_versions": versions,
                "last_retrain": last_retrain,
                "edge_buffer": storage.current_edge_buffer(),
                "findings": learner.latest_findings()[:5],
            },
            "trading_enabled": False,  # Phase 9 not built; always off
            "reality_note": (
                "15-minute crypto direction is close to a coin flip and Kalshi "
                "prices it efficiently. Probabilities shown are calibrated "
                "estimates, not locks; NO PLAY is the expected output for most "
                "windows. Paper results include Kalshi fees."),
        }

    @app.get("/api/history")
    def history(asset: str | None = Query(None), limit: int = Query(50, le=500)):
        rows = storage.resolved_history(limit=limit, asset=asset)
        return [{
            "asset": r["asset"], "window": win.et_label(r["window_start"]) +
                "–" + win.et_label(r["window_close"]),
            "window_close": r["window_close"],
            "date": win.et_datetime(r["window_start"]).strftime("%m/%d"),
            "pick": r["pick"], "prob_up": r["prob_up"],
            "entry": r["kalshi_yes_price_at_signal"], "edge": r["edge"],
            "actual": r["actual_direction"], "correct": r["correct"],
            "paper_pnl": r["paper_pnl"],
        } for r in rows]

    @app.get("/api/performance")
    def performance():
        rows = storage.resolved_history(limit=100_000)
        pnl_curve, cum = [], 0.0
        for r in sorted(rows, key=lambda x: x["resolved_at"]):
            if r["pick"] in (edge_mod.UP, edge_mod.DOWN):
                cum += r["paper_pnl"] or 0.0
                pnl_curve.append({"ts": r["resolved_at"], "pnl": round(cum, 2)})
        seven = learner.rolling_metrics(7)
        fourteen = learner.rolling_metrics(14)
        return {
            "seven_day": seven,
            "all_time": learner.rolling_metrics(None),
            "calibration": learner.calibration_buckets(30),
            "pnl_curve": pnl_curve[-500:],
            "paper_contracts": config.PAPER_CONTRACTS,
            # Self-improvement trend: this week vs the two-week average.
            "trend": {"acc_7d": seven["overall"].get("pick_accuracy"),
                      "acc_14d": fourteen["overall"].get("pick_accuracy"),
                      "brier_7d": seven["overall"].get("brier"),
                      "brier_14d": fourteen["overall"].get("brier"),
                      "graded_total": storage.resolved_count()},
        }

    @app.get("/api/news")
    def news(limit: int = Query(10, le=50)):
        return [{
            "ts": r["ts"], "source": r["source"], "title": r["title"],
            "url": r["url"], "assets": r["assets_mentioned"],
            "sentiment": r["sentiment_score"], "importance": r["importance"],
        } for r in storage.recent_news(limit=limit)]

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


# Standalone (DB-only) app for `uvicorn dashboard.server:app`.
storage.init_db()
app = create_app()
