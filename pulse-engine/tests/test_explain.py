"""AI-breakdown builder: factor attribution and narrative assembly."""
import numpy as np
import pandas as pd

from engine import explain
from engine.features import FEATURE_COLUMNS


def _tiny_bundle(seed: int = 5):
    import lightgbm as lgb
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(rng.normal(size=(500, len(FEATURE_COLUMNS))),
                     columns=FEATURE_COLUMNS)
    y = ((X["ret_5m"] + 0.5 * X["gbm_prob"]) > 0).astype(int)
    m = lgb.LGBMClassifier(n_estimators=30, verbose=-1)
    m.fit(X, y)
    return {"model": m, "feature_columns": FEATURE_COLUMNS}, X


def test_top_factors_rank_real_drivers():
    bundle, X = _tiny_bundle()
    feats = {c: float(X.iloc[0][c]) for c in FEATURE_COLUMNS}
    factors = explain.top_factors(bundle, feats)
    assert factors, "expected non-empty factor list"
    assert all({"label", "value", "points"} <= set(f) for f in factors)
    labels = " ".join(f["label"] for f in factors)
    assert "5-min return" in labels or "Brownian fair value" in labels


def test_build_breakdown_without_model():
    summary = {"pick": "NO PLAY", "prob_up": 0.53, "raw_prob_up": 0.56,
               "implied_up": 0.50, "edge": 0.01, "window_start": 1_783_356_300,
               "buffer": 0.03}
    feats = {"gbm_prob": 0.52, "vol_regime": 0.1}
    bd = explain.build_breakdown("BTC", summary, feats, None, None)
    assert bd["verdict"]["pick"] == "NO PLAY"
    assert any("fee" in l for l in bd["fair_value_chain"])
    assert bd["factors"] == []
    assert bd["self_tracking"]


def test_breakdown_pick_verdict_and_analogs():
    bundle, X = _tiny_bundle()
    bundle["context_stats"] = {
        "windows": 4000, "up_rate": 0.501,
        "by_hour_bucket": {"afternoon(12-6pm)": {"up_rate": 0.53, "n": 900}},
        "by_vol": {"normal-vol": {"up_rate": 0.49, "n": 2500}},
    }
    # 1783357200 = 12:00pm ET (16:00 UTC, July) -> afternoon bucket
    summary = {"pick": "UP", "prob_up": 0.61, "raw_prob_up": 0.68,
               "implied_up": 0.52, "edge": 0.07, "entry_price": 0.54,
               "window_start": 1_783_368_000, "buffer": 0.03}
    feats = {c: float(X.iloc[1][c]) for c in FEATURE_COLUMNS}
    feats["vol_regime"] = 0.1
    bd = explain.build_breakdown("BTC", summary, feats, bundle,
                                 {"picks": 12, "pick_accuracy": 0.58,
                                  "brier": 0.24, "paper_pnl": 55.0})
    assert bd["verdict"]["pick"] == "UP"
    assert bd["analogs"], "expected historical analog lines"
    assert any("58%" in l for l in bd["self_tracking"])
    assert any("shrink" in l.lower() for l in bd["fair_value_chain"])
