"""AI breakdown: a per-asset, per-scan deep dive the dashboard can render.

For every read the scanner produces, this assembles:
- the fair-value chain: GBM fair value -> raw model prob -> market-shrunk
  decision prob -> Kalshi implied -> fee/buffer hurdle;
- the top weighted factors behind the model's lean (LightGBM per-prediction
  contributions, translated into signed probability points);
- historical analogs: how windows in the same time-of-day / vol regime
  resolved over the training period (from the model bundle's context stats);
- self-tracking: the system's own recent graded record for the asset.

Everything is honest math from the live inputs — no generated fluff.
"""
from __future__ import annotations

import logging
import math

import numpy as np

import config
from engine import edge as edge_mod

log = logging.getLogger("pulse.explain")

# feature -> (human label, formatter)
_FMT_PCT = lambda v: f"{v * 100:+.2f}%"
_FMT_NUM = lambda v: f"{v:+.2f}"
_FMT_RAW = lambda v: f"{v:.2f}"
FRIENDLY: dict[str, tuple[str, object]] = {
    "win_open_to_now": ("move since window open", _FMT_PCT),
    "gbm_prob": ("Brownian fair value", lambda v: f"{v * 100:.1f}%"),
    "elapsed_frac": ("time elapsed in window", lambda v: f"{v * 100:.0f}%"),
    "ret_1m": ("1-min return", _FMT_PCT), "ret_3m": ("3-min return", _FMT_PCT),
    "ret_5m": ("5-min return", _FMT_PCT), "ret_15m": ("15-min return", _FMT_PCT),
    "ret_30m": ("30-min return", _FMT_PCT), "ret_60m": ("60-min return", _FMT_PCT),
    "ema_spread": ("EMA5 vs EMA20 spread", _FMT_PCT),
    "rsi_14": ("RSI(14)", _FMT_RAW), "macd_hist": ("MACD histogram", _FMT_NUM),
    "rvol_30m": ("30-min realized vol", lambda v: f"{v * 100:.3f}%/min"),
    "vol_regime": ("volatility vs 4h norm", _FMT_NUM),
    "vwap_dist": ("distance from VWAP", _FMT_PCT),
    "dist_4h_high": ("distance from 4h high", _FMT_PCT),
    "dist_4h_low": ("distance from 4h low", _FMT_PCT),
    "body_1": ("last candle body", _FMT_NUM), "body_2": ("2nd-last candle body", _FMT_NUM),
    "body_3": ("3rd-last candle body", _FMT_NUM),
    "consec_updown": ("consecutive candles same direction", _FMT_NUM),
    "vol_zscore": ("volume vs 30-day norm (z)", _FMT_NUM),
    "btc_ret_5m": ("BTC 5-min move (leads alts)", _FMT_PCT),
    "btc_corr_1h": ("1h correlation to BTC", _FMT_RAW),
    "hour_sin": ("time of day", _FMT_NUM), "hour_cos": ("time of day", _FMT_NUM),
    "dow": ("day of week", _FMT_RAW),
    "us_open_prox": ("US market open proximity", _FMT_RAW),
    "us_close_prox": ("US market close proximity", _FMT_RAW),
    "fng_level": ("Fear & Greed index", _FMT_RAW),
    "fng_change": ("Fear & Greed 1-day change", _FMT_NUM),
    "news_count_60m": ("headlines last 60m", _FMT_RAW),
    "news_hi_count_60m": ("high-importance headlines 60m", _FMT_RAW),
    "news_sent_60m": ("news sentiment 60m", _FMT_NUM),
    "news_breaking": ("breaking-news flag", _FMT_RAW),
    "kalshi_implied": ("Kalshi implied prob", lambda v: f"{v * 100:.1f}%"),
    "kalshi_drift_2m": ("Kalshi implied drift (2m)", lambda v: f"{v * 100:+.1f}pts"),
    "kalshi_spread": ("Kalshi bid-ask spread", lambda v: f"{v * 100:.0f}c"),
}


def top_factors(bundle: dict, feats: dict, k: int = 6) -> list[dict]:
    """Top signed feature contributions for this prediction, in prob points."""
    try:
        cols = bundle["feature_columns"]
        x = np.array([[feats.get(c, 0.0) for c in cols]], dtype=float)
        contrib = bundle["model"].booster_.predict(x, pred_contrib=True)[0]
    except Exception as e:  # noqa: BLE001 — explanation must never break a scan
        log.debug("pred_contrib failed: %s", e)
        return []
    per_feature, base = contrib[:-1], contrib[-1]
    p = 1.0 / (1.0 + math.exp(-(float(per_feature.sum()) + float(base))))
    scale = p * (1.0 - p)  # logistic slope: log-odds -> prob points
    order = np.argsort(-np.abs(per_feature))
    out = []
    for i in order[:k]:
        pts = float(per_feature[i]) * scale * 100.0
        if abs(pts) < 0.05:
            continue
        name = cols[i]
        label, fmt = FRIENDLY.get(name, (name, _FMT_NUM))
        try:
            shown = fmt(feats.get(name, 0.0))
        except Exception:  # noqa: BLE001
            shown = str(feats.get(name))
        out.append({"label": label, "value": shown, "points": round(pts, 1)})
    return out


def _analogs(bundle: dict | None, window_start: int, feats: dict) -> list[str]:
    if not bundle or not bundle.get("context_stats"):
        return []
    from engine import window as win
    cs = bundle["context_stats"]
    lines = []
    hour = win.et_datetime(window_start).hour
    bucket = ("overnight(12-6am)" if hour < 6 else "morning(6am-12)" if hour < 12
              else "afternoon(12-6pm)" if hour < 18 else "evening(6pm-12)")
    hb = cs.get("by_hour_bucket", {}).get(bucket)
    if hb:
        lines.append(f"In the {bucket} ET stretch, this asset closed UP "
                     f"{hb['up_rate']:.1%} of {hb['n']:,} past windows.")
    regime = "high-vol" if feats.get("vol_regime", 0) > 0.5 else "normal-vol"
    vb = cs.get("by_vol", {}).get(regime)
    if vb:
        lines.append(f"In {regime} conditions like now: UP {vb['up_rate']:.1%} "
                     f"of {vb['n']:,} windows.")
    if cs.get("windows"):
        lines.append(f"Base rate over the whole training period: UP "
                     f"{cs['up_rate']:.1%} of {cs['windows']:,} windows — "
                     "these markets live near 50/50.")
    return lines


def build_breakdown(asset: str, summary: dict, feats: dict | None,
                    bundle: dict | None, self_stats: dict | None) -> dict:
    """Assemble the full breakdown dict for one asset scan."""
    feats = feats or {}
    prob = summary.get("prob_up")
    raw = summary.get("raw_prob_up", prob)
    implied = summary.get("implied_up")
    edge_v = summary.get("edge")
    pick = summary.get("pick", edge_mod.NO_PLAY)

    fair_chain = []
    if feats.get("gbm_prob") is not None:
        fair_chain.append(f"Brownian fair value (move vs time left): "
                          f"{feats['gbm_prob'] * 100:.1f}% UP")
    if raw is not None:
        fair_chain.append(f"ML model (all factors): {raw * 100:.1f}% UP")
    if implied is not None and prob is not None and raw is not None and \
            abs(prob - raw) > 1e-6:
        fair_chain.append(
            f"After shrinking {config.MODEL_MARKET_SHRINK:.0%} toward the "
            f"market's {implied * 100:.1f}%: decision prob {prob * 100:.1f}%")
    if implied is not None:
        entry = summary.get("entry_price")
        fee = config.kalshi_fee_per_contract(entry if entry else 0.5)
        hurdle = (fee + summary.get("buffer", config.MIN_EDGE_BUFFER)) * 100
        fair_chain.append(
            f"Kalshi prices it {implied * 100:.1f}% — edge "
            f"{'%+.1f' % (edge_v * 100) if edge_v is not None else 'n/a'}pts vs "
            f"a ~{hurdle:.1f}pt fee+buffer hurdle")
        spread = feats.get("kalshi_spread")
        if spread:
            fair_chain.append(
                f"Spread cost: {spread * 100:.0f}c wide book — crossing it is "
                f"~{spread * 50:.1f}pts of the edge")
    else:
        fair_chain.append("No live Kalshi quotes this window — read is "
                          "informational, no playable market")

    verdict = {"pick": pick}
    if pick in (edge_mod.UP, edge_mod.DOWN):
        verdict["line"] = (f"{pick}: the decision probability beats the price "
                           f"paid by more than fees + buffer, confirmed on "
                           f"{config.SCAN_CONFIRMATIONS} consecutive scans.")
        entry = summary.get("entry_price")
        if entry and prob is not None:
            p_side = prob if pick == edge_mod.UP else 1 - prob
            fee = config.kalshi_fee_per_contract(entry)
            ev = p_side * 1.0 - entry - fee
            breakeven = entry + fee
            verdict["value_line"] = (
                f"Value per contract at {entry * 100:.0f}c: EV "
                f"{ev * 100:+.1f}c (win prob {p_side:.1%} vs breakeven "
                f"{breakeven:.1%} incl. fee).")
    else:
        verdict["line"] = ("NO PLAY: after fees there is no exploitable gap "
                           "between the model and the market on this window.")
    if summary.get("slip", {}).get("flagged"):
        s = summary["slip"]
        verdict["slip_line"] = (
            f"SLIP detected: quote is {s['quote_age_s']}s old while spot moved "
            f"{s['spot_move_pct']:+.3f}% — fair value has shifted "
            f"{s['expected_repricing_pts']:+.1f}pts vs the posted quote.")

    self_lines = []
    if self_stats:
        acc = self_stats.get("pick_accuracy")
        n = self_stats.get("picks", 0)
        if acc is not None and n:
            self_lines.append(f"Last 7 days on {asset}: {n} picks, "
                              f"{acc:.0%} correct, Brier {self_stats.get('brier')}, "
                              f"paper P&L ${self_stats.get('paper_pnl')}.")
        elif self_stats.get("windows"):
            self_lines.append(f"Last 7 days on {asset}: "
                              f"{self_stats['windows']} windows graded, no picks "
                              "flagged yet (NO PLAY discipline).")
    self_lines.append("Every window is graded 30s after close; models retrain "
                      "weekly (or on Brier degradation / 200 new outcomes) and "
                      "are only promoted if validation improves.")

    return {
        "verdict": verdict,
        "fair_value_chain": fair_chain,
        "factors": top_factors(bundle, feats) if bundle and feats else [],
        "analogs": _analogs(bundle, summary.get("window_start", 0), feats),
        "self_tracking": self_lines,
    }
