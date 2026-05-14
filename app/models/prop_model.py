"""Player-prop model.

Pipeline per (sport, market):
  1. LightGBM regressor over the feature columns -> predicted stat value
  2. Residual std on a hold-out tail -> noise estimate
  3. P(over line) = 1 - F(line | mu_hat, sigma_hat) where F is either:
       - Poisson CDF for count markets (strikeouts, threes, hits, shots, saves, ...)
       - Normal CDF otherwise
  4. Optional isotonic calibration on (predicted_p, did_over) from out-of-fold
     predictions so probabilities are honest.

The whole bundle (model, feature_cols, residual_std, calibrator, metadata) is
joblib-dumped to models/<sport>__<market>.joblib so the daily pipeline can
load it without retraining.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from scipy.stats import norm, poisson
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, log_loss, mean_absolute_error
from sklearn.model_selection import KFold

import lightgbm as lgb

from app.config import CFG
from app.features import FEATURE_COLS, build_training_frame
from app.store import record_model_run
from app.utils import get_logger

LOG = get_logger("prop_model")

COUNT_MARKETS = {
    "player_threes", "player_steals", "player_blocks", "player_goals",
    "player_assists",  # often integer
    "batter_hits", "batter_home_runs", "batter_rbis", "batter_runs",
    "batter_strikeouts", "pitcher_strikeouts", "pitcher_earned_runs",
    "player_shots_on_goal", "goalie_saves",
}


@dataclass
class TrainedModel:
    sport: str
    market: str
    model: Any
    feature_cols: list[str]
    residual_std: float
    n_train: int
    mae: float
    brier: float | None
    log_loss: float | None
    calibrator: IsotonicRegression | None = None
    extra: dict = field(default_factory=dict)

    def prob_over(self, features: dict, line: float) -> float:
        x = np.array([[features.get(c, 0.0) for c in self.feature_cols]], dtype=float)
        mu = float(self.model.predict(x)[0])
        sigma = max(self.residual_std, 0.5)
        if self.market in COUNT_MARKETS:
            # Poisson over: P(X > line) using floor(line). For half-line, line.5,
            # P(X >= ceil(line)).
            lam = max(mu, 0.05)
            threshold = math.floor(line) if (line % 1) > 0 else int(line)
            # If line is half (e.g. 2.5) we want P(X >= 3) = 1 - P(X <= 2) = 1 - cdf(2)
            # If line is whole (push possible) treat over as P(X > line) = 1 - cdf(line).
            p = 1.0 - float(poisson.cdf(threshold, lam))
        else:
            z = (line - mu) / sigma
            p = 1.0 - float(norm.cdf(z))
        p = min(max(p, 1e-4), 1 - 1e-4)
        if self.calibrator is not None:
            try:
                p = float(self.calibrator.predict([p])[0])
                p = min(max(p, 1e-4), 1 - 1e-4)
            except Exception:
                pass
        return p

    def predict_mean(self, features: dict) -> float:
        x = np.array([[features.get(c, 0.0) for c in self.feature_cols]], dtype=float)
        return float(self.model.predict(x)[0])


def model_path(sport: str, market: str) -> Path:
    return CFG.models_dir / f"{sport}__{market}.joblib"


def load(sport: str, market: str) -> TrainedModel | None:
    p = model_path(sport, market)
    if not p.exists():
        return None
    try:
        return joblib.load(p)
    except Exception as e:  # noqa: BLE001
        LOG.warning("failed to load %s: %s", p, e)
        return None


def train(sport: str, market: str, *, min_rows: int = 200) -> TrainedModel | None:
    df = build_training_frame(sport, market)
    if df.empty or len(df) < min_rows:
        LOG.info("train %s/%s: skipped (rows=%d)", sport, market, len(df))
        return None

    # Sort by date so the hold-out is the most-recent slice — closer to real use.
    df = df.sort_values("game_date").reset_index(drop=True)
    X = df[FEATURE_COLS].fillna(df[FEATURE_COLS].median(numeric_only=True)).fillna(0.0).to_numpy()
    y = df["target"].to_numpy(dtype=float)

    split = int(len(df) * 0.85)
    X_tr, X_te = X[:split], X[split:]
    y_tr, y_te = y[:split], y[split:]

    booster = lgb.LGBMRegressor(
        n_estimators=400,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=20,
        subsample=0.85,
        colsample_bytree=0.85,
        reg_alpha=0.0,
        reg_lambda=0.0,
        objective="regression",
        random_state=42,
        verbose=-1,
    )
    booster.fit(X_tr, y_tr)
    pred_te = booster.predict(X_te)
    residual_std = float(np.std(y_te - pred_te))
    mae = float(mean_absolute_error(y_te, pred_te))

    # Calibration: out-of-fold probabilities -> did_over for the median market line.
    calibrator = None
    brier = ll = None
    try:
        oof_pred = np.zeros_like(y, dtype=float)
        for tr_idx, va_idx in KFold(n_splits=5, shuffle=True, random_state=0).split(X):
            fold = lgb.LGBMRegressor(**booster.get_params())
            fold.fit(X[tr_idx], y[tr_idx])
            oof_pred[va_idx] = fold.predict(X[va_idx])
        sigma = max(float(np.std(y - oof_pred)), 0.5)
        # Use the half-of-prior-game median as the proxy line.
        med = float(np.median(y))
        line_proxy = med if (med % 1) else med + 0.5
        if market in COUNT_MARKETS:
            lam = np.clip(oof_pred, 0.05, None)
            raw_p = 1.0 - poisson.cdf(int(math.floor(line_proxy)), lam)
        else:
            z = (line_proxy - oof_pred) / sigma
            raw_p = 1.0 - norm.cdf(z)
        raw_p = np.clip(raw_p, 1e-4, 1 - 1e-4)
        did_over = (y > line_proxy).astype(int)
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.001, y_max=0.999)
        iso.fit(raw_p, did_over)
        cal_p = np.clip(iso.predict(raw_p), 1e-4, 1 - 1e-4)
        brier = float(brier_score_loss(did_over, cal_p))
        ll = float(log_loss(did_over, cal_p))
        calibrator = iso
    except Exception as e:  # noqa: BLE001
        LOG.warning("calibration skipped for %s/%s: %s", sport, market, e)

    tm = TrainedModel(
        sport=sport, market=market, model=booster,
        feature_cols=FEATURE_COLS, residual_std=residual_std,
        n_train=int(len(df)), mae=mae, brier=brier, log_loss=ll,
        calibrator=calibrator,
        extra={"median_target": float(np.median(y))},
    )
    CFG.models_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(tm, model_path(sport, market))
    record_model_run(sport, market, int(len(df)), mae, brier, ll,
                     notes=json.dumps({"residual_std": residual_std}))
    LOG.info("trained %s/%s rows=%d mae=%.3f brier=%s", sport, market, len(df), mae, brier)
    return tm
