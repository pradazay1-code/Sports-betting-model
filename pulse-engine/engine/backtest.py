"""Backtest: replay historical 15-min windows through the live feature and
decision code.

Historical Kalshi quotes don't exist locally, so the implied probability is
simulated as 50% +/- small noise — backtest P&L is therefore APPROXIMATE and
labeled as such. This is as much a plumbing test (no-lookahead, decision
wiring) as an alpha test.

Run:  python engine/backtest.py [--days 30] [--asset BTC]
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
import storage
from engine import edge as edge_mod
from engine.features import build_features

log = logging.getLogger("pulse.backtest")


def _train_out_of_sample(asset: str, cutoff_ts: int):
    """Model + calibrator fit ONLY on windows before `cutoff_ts`, so the
    backtest period is genuinely out-of-sample (the promoted live model has
    usually seen it)."""
    from sklearn.isotonic import IsotonicRegression

    from engine.model import _make_lgbm, build_training_frame

    df = build_training_frame(asset)
    df = df[df["_window_start"] < cutoff_ts]
    if len(df) < 1500:
        return None
    cal_cut = int(df["_window_start"].quantile(0.85))
    tr, ca = df[df["_window_start"] < cal_cut], df[df["_window_start"] >= cal_cut]
    from engine.features import FEATURE_COLUMNS
    m = _make_lgbm()
    m.fit(tr[FEATURE_COLUMNS].astype(float), tr["_label"].to_numpy(int))
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.02, y_max=0.98)
    iso.fit(m.predict_proba(ca[FEATURE_COLUMNS].astype(float))[:, 1],
            ca["_label"].to_numpy(int))
    return m, iso


def backtest_asset(asset: str, days: int = 30, seed: int = 7) -> dict | None:
    from collectors.history_backfill import resample_15m
    from engine.features import FEATURE_COLUMNS

    rng = np.random.default_rng(seed)
    start = int(time.time()) - days * 86400

    trained = _train_out_of_sample(asset, start)
    if trained is None:
        log.warning("%s: not enough pre-period data to backtest", asset)
        return None
    model, calibrator = trained
    candles = storage.get_candles(asset, start - 40 * 86400)
    btc = candles if asset == "BTC" else storage.get_candles("BTC", start - 40 * 86400)
    wins = resample_15m(asset, start)
    if wins.empty:
        return None
    wins = wins.dropna(subset=["direction"])

    # Scanner replay: evaluate every 60s through each window; the first
    # offset where edge clears fee + buffer becomes the (single) pick, same
    # as live. Simulated quotes track the Brownian fair value +/- noise —
    # an efficient market — so picks here come only from ML disagreement
    # with GBM. The real-world latency edge (Kalshi repricing seconds
    # behind spot) cannot be simulated from candles and is NOT included.
    offsets = range(60, config.WINDOW_SECONDS - 45, 60)
    n = picks = correct_picks = 0
    briers: list[float] = []
    pnl = 0.0
    for wstart, w in wins.iterrows():
        y = int(w["direction"])
        window_counted = decided = False
        streak_side, streak_n = "", 0
        for off in offsets:
            feats = build_features(asset, int(wstart) + off, candles, btc)
            if feats is None:
                continue
            x = pd.DataFrame([[feats[c] for c in FEATURE_COLUMNS]],
                             columns=FEATURE_COLUMNS, dtype=float)
            raw = float(model.predict_proba(x)[0, 1])
            prob_up = float(np.clip(calibrator.predict([raw])[0], 0.02, 0.98))
            briers.append((prob_up - y) ** 2)
            if not window_counted:
                n += 1
                window_counted = True
            if decided:
                continue
            mid = float(np.clip(feats["gbm_prob"] * 100 + rng.normal(0, 2.0),
                                3.0, 97.0))
            yes_bid, yes_ask = mid - 1.0, mid + 1.0
            d = edge_mod.decide(prob_up, yes_bid, yes_ask)
            if d.pick in (edge_mod.UP, edge_mod.DOWN):
                streak_n = streak_n + 1 if d.pick == streak_side else 1
                streak_side = d.pick
                if streak_n >= config.SCAN_CONFIRMATIONS:  # same debounce as live
                    decided = True
                    picks += 1
                    won = (d.pick == "UP") == (y == 1)
                    correct_picks += int(won)
                    pnl += edge_mod.paper_pnl(d.pick, d.entry_price, won)
            else:
                streak_side, streak_n = "", 0

    if n == 0:
        return None
    return {
        "asset": asset, "windows": n,
        "brier": round(float(np.mean(briers)), 4),
        "accuracy": round(float(np.mean([(b <= 0.25) for b in briers])), 4),
        "picks": picks, "pick_rate": round(picks / n, 3),
        "pick_accuracy": round(correct_picks / picks, 4) if picks else None,
        "approx_pnl": round(pnl, 2),
    }


def run(days: int = 30, asset: str | None = None) -> None:
    assets = [asset.upper()] if asset else config.ASSETS
    print(f"Backtest — last {days} days, scanner replay @60s steps.\n"
          "Quotes SIMULATED as GBM fair value ±2c (efficient market): picks "
          "come only from\nML-vs-GBM disagreement; the live latency edge is "
          "not simulated. P&L is approximate.\n")
    print(f"{'asset':<6} {'windows':>8} {'brier':>7} {'acc':>7} {'picks':>6} "
          f"{'pick%':>6} {'pick_acc':>9} {'~P&L($)':>9}")
    for a in assets:
        r = backtest_asset(a, days)
        if r is None:
            print(f"{a:<6}  no data / no model")
            continue
        print(f"{r['asset']:<6} {r['windows']:>8} {r['brier']:>7.4f} "
              f"{r['accuracy']:>7.4f} {r['picks']:>6} {r['pick_rate']:>6.1%} "
              f"{str(r['pick_accuracy']):>9} {r['approx_pnl']:>9.2f}")
    print("\nNO PLAY should dominate: pick% above ~25% with simulated 50% "
          "quotes suggests miscalibration.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--asset", default=None)
    args = p.parse_args()
    logging.basicConfig(level=config.LOG_LEVEL,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    storage.init_db()
    run(args.days, args.asset)
