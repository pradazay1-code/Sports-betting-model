"""Prediction loop: fires ~75s into each 15-minute window.

Builds features -> calibrated prob_up -> Kalshi implied prob -> fee-aware
edge -> UP / DOWN / NO PLAY. Every prediction (including NO PLAY) is logged
with the Kalshi price at signal time as the paper entry. If the price feed
is stale or a model is missing, the window is skipped for that asset rather
than guessed at.
"""
from __future__ import annotations

import logging
import time

import config
import storage
from collectors.news_collector import news_features
from engine import edge as edge_mod
from engine import window as win
from engine.features import build_features
from engine.model import ModelStore

log = logging.getLogger("pulse.predictor")


class Predictor:
    def __init__(self, price_cache=None, kalshi_cache=None, news_cache=None) -> None:
        self.models = ModelStore()
        self.price_cache = price_cache
        self.kalshi_cache = kalshi_cache
        self.news_cache = news_cache
        self.last_run: dict[str, dict] = {}   # asset -> latest decision summary

    def _kalshi_inputs(self, asset: str, at_ts: float):
        """(yes_bid, yes_ask, implied, implied_2m_ago, spread) or Nones."""
        if self.kalshi_cache is None:
            return None, None, None, None, None
        q = self.kalshi_cache.quotes.get(asset)
        _, close_ts = win.window_bounds(at_ts)
        if q is None or q.window_close != close_ts or \
                at_ts - q.fetched_at > 3 * config.KALSHI_POLL_SECONDS + 30:
            return None, None, None, None, None
        implied = q.implied_up
        drift_ref = self.kalshi_cache.implied_at(asset, at_ts - 120)
        spread = None
        if q.yes_bid is not None and q.yes_ask is not None:
            spread = (q.yes_ask - q.yes_bid) / 100.0
        return q.yes_bid, q.yes_ask, implied, drift_ref, spread

    def run_window(self, now_ts: float | None = None) -> list[dict]:
        """Predict for every asset in the current window. Returns summaries."""
        now_ts = now_ts or time.time()
        wstart, wclose = win.window_bounds(now_ts)
        at_ts = int(now_ts)
        results = []
        lookback_start = at_ts - 35 * 86400  # 30d vol-z lookback + margin
        btc_candles = storage.get_candles("BTC", lookback_start, at_ts)
        buffer = storage.current_edge_buffer()

        for asset in config.ASSETS:
            summary = {"asset": asset, "window_start": wstart, "window_close": wclose,
                       "pick": edge_mod.NO_PLAY, "prob_up": None, "implied_up": None,
                       "edge": None, "status": "ok", "reasons": []}
            try:
                candles = btc_candles if asset == "BTC" else \
                    storage.get_candles(asset, lookback_start, at_ts)
                tick = self.price_cache.get(asset) if self.price_cache else None
                live_price = tick.price if tick and now_ts - tick.ts < 120 else None

                yes_bid, yes_ask, implied, implied_2m, spread = \
                    self._kalshi_inputs(asset, now_ts)
                nf = news_features(asset, at_ts)
                fng = (self.news_cache.fng if self.news_cache else None) or None

                feats = build_features(
                    asset, at_ts, candles, btc_candles, live_price=live_price,
                    kalshi_implied=implied, kalshi_implied_2m_ago=implied_2m,
                    kalshi_spread=spread, news=nf, fng=fng)
                if feats is None:
                    summary["status"] = "stale-data"
                    summary["reasons"].append("price data stale/insufficient — suppressing pick")
                    results.append(summary)
                    self.last_run[asset] = summary
                    continue

                pred = self.models.predict_prob_up(asset, feats)
                if pred is None:
                    summary["status"] = "no-model"
                    summary["reasons"].append("no trained model — run engine/model.py --train")
                    results.append(summary)
                    self.last_run[asset] = summary
                    continue
                prob_up, version = pred

                decision = edge_mod.decide(prob_up, yes_bid, yes_ask, buffer=buffer)
                summary.update({
                    "pick": decision.pick, "prob_up": prob_up,
                    "implied_up": decision.implied_up, "edge": decision.edge,
                    "reasons": decision.reasons, "model_version": version,
                    "no_kalshi_market": decision.implied_up is None,
                })

                storage.save_features(asset, wstart, feats)
                storage.insert_prediction({
                    "asset": asset, "window_start": wstart, "window_close": wclose,
                    "prob_up": prob_up, "pick": decision.pick,
                    "kalshi_yes_price_at_signal": decision.entry_price
                        if decision.pick != edge_mod.NO_PLAY else (
                            decision.implied_up if decision.implied_up is not None else None),
                    "edge": decision.edge, "model_version": version,
                    "created_at": at_ts,
                })
                log.info("%s %s->%s: prob_up=%.3f implied=%s edge=%s pick=%s",
                         asset, win.et_label(wstart), win.et_label(wclose),
                         prob_up, decision.implied_up, decision.edge, decision.pick)
            except Exception as e:  # noqa: BLE001 — one asset must not kill the loop
                log.exception("%s prediction failed: %s", asset, e)
                summary["status"] = "error"
                summary["reasons"].append(str(e))
            results.append(summary)
            self.last_run[asset] = summary
        return results
