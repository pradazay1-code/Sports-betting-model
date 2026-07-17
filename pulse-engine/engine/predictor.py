"""In-window scanner: evaluates every asset continuously through each
15-minute window and commits a pick the moment fee-adjusted edge appears.

This mirrors how the practitioner ecosystem trades these markets: Kalshi
quotes reprice seconds behind spot, so edge shows up mid-window when the
underlying moves and the market lags. The scanner:

- starts SCAN_START_SECONDS after the window opens, stops taking entries
  SCAN_STOP_SECONDS before close;
- each pass builds features (including the Brownian fair value) from the
  live tick, predicts calibrated P(up) — falling back to the pure GBM prob
  if no ML model is trained — and compares against live Kalshi quotes;
- writes at most ONE pick per (asset, window): the first time edge clears
  fee + buffer outside the confidence band (DB uniqueness enforces this);
- if the window ends with no trigger, records NO PLAY on the final pass so
  grading and Brier stats stay complete;
- flags dual-side arbitrage (YES ask + NO ask < $1) when quotes show it;
- attaches a fractional-Kelly stake *suggestion* to picks (display only).

If the price feed is stale, the pass is skipped rather than guessed at.
"""
from __future__ import annotations

import logging
import time

import config
import storage
from collectors.news_collector import news_features
from engine import edge as edge_mod
from engine import explain
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
        self.last_run: dict[str, dict] = {}   # asset -> latest scan summary
        self._decided: dict[str, int] = {}    # asset -> window_start already decided
        self._streak: dict[str, tuple[int, str, int]] = {}  # asset -> (wstart, side, count)
        self._self_stats: tuple[float, dict] = (0.0, {})    # (fetched_at, by_asset)

    def _asset_self_stats(self, asset: str) -> dict | None:
        """7-day graded record per asset, cached for 5 minutes."""
        ts, stats = self._self_stats
        if time.time() - ts > 300:
            try:
                from engine.learner import rolling_metrics
                stats = rolling_metrics(7)["by_asset"]
                self._self_stats = (time.time(), stats)
            except Exception as e:  # noqa: BLE001
                log.debug("self-stats refresh failed: %s", e)
        return stats.get(asset)

    def _next_window_preview(self, asset: str, wclose: int, candles,
                             btc_candles) -> dict | None:
        """Early read on the upcoming window, from at-the-open features."""
        feats = build_features(asset, wclose, candles, btc_candles)
        if feats is None:
            return None
        pred = self.models.predict_prob_up(asset, feats)
        prob, version = pred if pred else (feats["gbm_prob"], "gbm-fallback")
        return {"window_start": wclose, "window_close": wclose + config.WINDOW_SECONDS,
                "label": f"{win.et_label(wclose)}–{win.et_label(wclose + config.WINDOW_SECONDS)}",
                "prob_up": prob, "model_version": version}

    # ------------------------------------------------------------- inputs --

    def _kalshi_inputs(self, asset: str, at_ts: float):
        """(quote, implied, implied_2m_ago, spread) — Nones when unavailable."""
        if self.kalshi_cache is None:
            return None, None, None, None
        q = self.kalshi_cache.quotes.get(asset)
        _, close_ts = win.window_bounds(at_ts)
        if q is None or q.window_close != close_ts or \
                at_ts - q.fetched_at > 3 * config.KALSHI_POLL_SECONDS + 30:
            return None, None, None, None
        implied = q.implied_up
        drift_ref = self.kalshi_cache.implied_at(asset, at_ts - 120)
        spread = None
        if q.yes_bid is not None and q.yes_ask is not None:
            spread = (q.yes_ask - q.yes_bid) / 100.0
        return q, implied, drift_ref, spread

    def _already_decided(self, asset: str, wstart: int) -> bool:
        if self._decided.get(asset) == wstart:
            return True
        if storage.prediction_for(asset, wstart) is not None:
            self._decided[asset] = wstart
            return True
        return False

    # --------------------------------------------------------------- scan --

    def scan(self, now_ts: float | None = None) -> list[dict]:
        """One scanner pass over all assets. Returns per-asset summaries."""
        now_ts = now_ts or time.time()
        wstart, wclose = win.window_bounds(now_ts)
        elapsed = now_ts - wstart
        remaining = wclose - now_ts
        if elapsed < config.SCAN_START_SECONDS:
            return []
        entries_open = remaining > config.SCAN_STOP_SECONDS
        # Last pass of the window: close out undecided assets as NO PLAY.
        finalize = remaining <= config.SCAN_STOP_SECONDS + config.SCAN_INTERVAL_SECONDS
        if not entries_open and not finalize:
            return []

        at_ts = int(now_ts)
        results = []
        lookback_start = at_ts - 35 * 86400  # 30d vol-z lookback + margin
        btc_candles = storage.get_candles("BTC", lookback_start, at_ts)
        buffer = storage.current_edge_buffer()

        for asset in config.ASSETS:
            summary = {"asset": asset, "window_start": wstart, "window_close": wclose,
                       "pick": edge_mod.NO_PLAY, "prob_up": None, "implied_up": None,
                       "edge": None, "status": "ok", "reasons": [], "kelly": None,
                       "arb_cents": None, "decided": False, "scanned_at": at_ts}
            try:
                candles = btc_candles if asset == "BTC" else \
                    storage.get_candles(asset, lookback_start, at_ts)

                if self._already_decided(asset, wstart):
                    prev = self.last_run.get(asset)
                    if not (prev and prev.get("window_start") == wstart):
                        row = storage.prediction_for(asset, wstart) or {}
                        summary.update({"pick": row.get("pick", edge_mod.NO_PLAY),
                                        "prob_up": row.get("prob_up"),
                                        "edge": row.get("edge"), "decided": True})
                        prev = summary
                    if remaining <= config.NEXT_WINDOW_PREVIEW_SECONDS:
                        prev["next_window"] = self._next_window_preview(
                            asset, wclose, candles, btc_candles)
                    results.append(prev)
                    self.last_run[asset] = prev
                    continue
                tick = self.price_cache.get(asset) if self.price_cache else None
                live_price = tick.price if tick and now_ts - tick.ts < 120 else None

                quote, implied, implied_2m, spread = self._kalshi_inputs(asset, now_ts)
                nf = news_features(asset, at_ts)
                fng = (self.news_cache.fng if self.news_cache else None) or None

                feats = build_features(
                    asset, at_ts, candles, btc_candles, live_price=live_price,
                    kalshi_implied=implied, kalshi_implied_2m_ago=implied_2m,
                    kalshi_spread=spread, news=nf, fng=fng)
                if feats is None:
                    summary["status"] = "stale-data"
                    summary["reasons"].append("price data stale/insufficient — suppressing")
                    results.append(summary)
                    self.last_run[asset] = summary
                    continue

                pred = self.models.predict_prob_up(asset, feats)
                if pred is not None:
                    prob_up, version = pred
                else:
                    # Pure Brownian fair value until a model is trained.
                    prob_up, version = feats["gbm_prob"], "gbm-fallback"
                    summary["reasons"].append("no ML model — using GBM fair value")

                yes_bid = quote.yes_bid if quote else None
                yes_ask = quote.yes_ask if quote else None
                decision = edge_mod.decide(prob_up, yes_bid, yes_ask, buffer=buffer)

                arb = edge_mod.dual_side_arb(yes_ask, quote.no_ask if quote else None)
                if arb is not None:
                    summary["arb_cents"] = arb
                    summary["reasons"].append(
                        f"ARB: YES+NO asks leave {arb:.0f}c/pair gross (check fees)")
                    log.warning("%s %s: dual-side arb %sc gross", asset,
                                quote.ticker if quote else "?", arb)

                # decision.prob_up is the market-shrunk probability actually
                # acted on (and graded); the raw model prob rides along.
                prob_up = decision.prob_up
                summary.update({
                    "pick": decision.pick, "prob_up": prob_up,
                    "raw_prob_up": decision.raw_prob_up,
                    "implied_up": decision.implied_up, "edge": decision.edge,
                    "entry_price": decision.entry_price, "buffer": buffer,
                    "reasons": decision.reasons + summary["reasons"],
                    "model_version": version,
                    "no_kalshi_market": decision.implied_up is None,
                })

                # Confirmation streak: the same side must clear the threshold
                # on SCAN_CONFIRMATIONS consecutive scans before we commit.
                if decision.pick != edge_mod.NO_PLAY:
                    w0, side, count = self._streak.get(asset, (0, "", 0))
                    count = count + 1 if (w0 == wstart and side == decision.pick) else 1
                    self._streak[asset] = (wstart, decision.pick, count)
                else:
                    self._streak.pop(asset, None)
                confirmed = self._streak.get(asset, (0, "", 0))[2] >= config.SCAN_CONFIRMATIONS

                take_pick = (decision.pick != edge_mod.NO_PLAY and entries_open
                             and confirmed)
                if decision.pick != edge_mod.NO_PLAY and not confirmed:
                    summary["reasons"].append(
                        f"awaiting confirmation "
                        f"({self._streak[asset][2]}/{config.SCAN_CONFIRMATIONS} scans)")
                if take_pick:
                    p_side = prob_up if decision.pick == edge_mod.UP else 1 - prob_up
                    summary["kelly"] = edge_mod.kelly_suggestion(
                        p_side, decision.entry_price)
                if take_pick or finalize:
                    # Only a taken entry is a pick; an unconfirmed edge at the
                    # finalize pass records as NO PLAY (no position exists).
                    pick_to_store = decision.pick if take_pick else edge_mod.NO_PLAY
                    summary["pick"] = pick_to_store
                    storage.save_features(asset, wstart, feats)
                    storage.insert_prediction({
                        "asset": asset, "window_start": wstart, "window_close": wclose,
                        "prob_up": prob_up, "pick": pick_to_store,
                        "kalshi_yes_price_at_signal": decision.entry_price
                            if take_pick else (decision.implied_up
                                               if decision.implied_up is not None else None),
                        "edge": decision.edge, "model_version": version,
                        "created_at": at_ts,
                    })
                    self._decided[asset] = wstart
                    summary["decided"] = True
                    log.info("%s %s: %s @ %ds in — prob_up=%.3f implied=%s edge=%s%s",
                             asset, win.et_label(wstart), pick_to_store, int(elapsed),
                             prob_up, decision.implied_up, decision.edge,
                             f" kelly={summary['kelly']}" if summary["kelly"] else "")
                # Deep-dive breakdown + early read on the NEXT window.
                summary["breakdown"] = explain.build_breakdown(
                    asset, summary, feats, self.models.get(asset),
                    self._asset_self_stats(asset))
                if remaining <= config.NEXT_WINDOW_PREVIEW_SECONDS:
                    summary["next_window"] = self._next_window_preview(
                        asset, wclose, candles, btc_candles)
            except Exception as e:  # noqa: BLE001 — one asset must not kill the pass
                log.exception("%s scan failed: %s", asset, e)
                summary["status"] = "error"
                summary["reasons"].append(str(e))
            results.append(summary)
            self.last_run[asset] = summary
        return results

    # Back-compat alias (older callers/tests used one-shot semantics).
    def run_window(self, now_ts: float | None = None) -> list[dict]:
        return self.scan(now_ts)
