"""Walk-forward backtest.

For each (sport, market) we hold out the latest 20% of historical games and
report MAE on the predicted stat plus Brier score on a half-line proxy. This
is the same thing the trainer computes — exposed here as a CLI for sanity.
"""

from __future__ import annotations

import json
import math

import numpy as np
from scipy.stats import norm, poisson

from app.config import MARKETS
from app.features import FEATURE_COLS, build_training_frame
from app.models.prop_model import COUNT_MARKETS
import lightgbm as lgb
from sklearn.metrics import brier_score_loss, log_loss, mean_absolute_error


def _prob_over(market: str, mu: np.ndarray, sigma: float, line: float) -> np.ndarray:
    if market in COUNT_MARKETS:
        threshold = math.floor(line) if (line % 1) > 0 else int(line)
        lam = np.clip(mu, 0.05, None)
        p = 1.0 - poisson.cdf(threshold, lam)
    else:
        z = (line - mu) / max(sigma, 0.5)
        p = 1.0 - norm.cdf(z)
    return np.clip(p, 1e-4, 1 - 1e-4)


def backtest(sport: str, market: str, *, holdout_frac: float = 0.2) -> dict:
    df = build_training_frame(sport, market)
    if df.empty or len(df) < 200:
        return {"sport": sport, "market": market, "rows": len(df), "skip": True}
    df = df.sort_values("game_date").reset_index(drop=True)
    X = df[FEATURE_COLS].fillna(df[FEATURE_COLS].median(numeric_only=True)).fillna(0.0).to_numpy()
    y = df["target"].to_numpy(dtype=float)
    split = int(len(df) * (1 - holdout_frac))
    model = lgb.LGBMRegressor(
        n_estimators=400, learning_rate=0.05, num_leaves=31,
        min_child_samples=20, subsample=0.85, colsample_bytree=0.85,
        random_state=42, verbose=-1,
    )
    model.fit(X[:split], y[:split])
    pred = model.predict(X[split:])
    sigma = float(np.std(y[split:] - pred))
    mae = float(mean_absolute_error(y[split:], pred))
    line = float(np.median(y[:split]))
    if (line % 1) == 0:
        line += 0.5
    probs = _prob_over(market, pred, sigma, line)
    did_over = (y[split:] > line).astype(int)
    try:
        brier = float(brier_score_loss(did_over, probs))
        ll = float(log_loss(did_over, probs))
    except ValueError:
        brier = ll = None
    return {
        "sport": sport, "market": market, "rows": len(df),
        "holdout": int(len(df) - split), "mae": round(mae, 3),
        "brier": brier and round(brier, 4), "log_loss": ll and round(ll, 4),
        "proxy_line": line,
    }


def run_all() -> list[dict]:
    out = []
    for sport, markets in MARKETS.items():
        for market in markets:
            try:
                out.append(backtest(sport, market))
            except Exception as e:  # noqa: BLE001
                out.append({"sport": sport, "market": market, "error": str(e)})
    return out


if __name__ == "__main__":
    print(json.dumps(run_all(), indent=2))
