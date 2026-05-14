"""Per-(sport, market) regression model with Poisson-style P(over) inference.

Strategy:
  - Predict the *expected count* (or expected value) for the stat.
  - Estimate residual std from training residuals.
  - At inference, P(stat > line) is computed from a Poisson CDF for count
    markets, or a Normal CDF as a fallback for continuous markets.
  - A small isotonic calibrator can be fit on top to map raw model probabilities
    to better-calibrated probabilities.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:  # pragma: no cover
    HAS_LGB = False
    from sklearn.ensemble import GradientBoostingRegressor

from ..features import COUNT_MARKETS


@dataclass
class TrainMetrics:
    n: int = 0
    mae: float = 0.0
    rmse: float = 0.0
    residual_std: float = 1.0
    calibration_brier: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class PropModel:
    def __init__(self, sport: str, market: str):
        self.sport = sport
        self.market = market
        self.feature_names: list[str] = []
        self.regressor = None
        self.residual_std: float = 1.0
        self.calibrator: Optional[IsotonicRegression] = None
        self.metrics: TrainMetrics = TrainMetrics()
        self.is_count_market: bool = market in COUNT_MARKETS

    def fit(self, X: pd.DataFrame, y: pd.Series) -> TrainMetrics:
        self.feature_names = list(X.columns)
        if HAS_LGB:
            self.regressor = lgb.LGBMRegressor(
                n_estimators=400,
                learning_rate=0.05,
                num_leaves=31,
                min_child_samples=20,
                subsample=0.9,
                colsample_bytree=0.9,
                random_state=42,
                verbose=-1,
            )
        else:
            self.regressor = GradientBoostingRegressor(random_state=42)

        # Time-series-respecting split: last 20% for validation.
        split = max(1, int(len(X) * 0.8))
        X_train, X_val = X.iloc[:split], X.iloc[split:]
        y_train, y_val = y.iloc[:split], y.iloc[split:]
        self.regressor.fit(X_train, y_train)
        preds = self.regressor.predict(X_val) if len(X_val) else self.regressor.predict(X_train)
        truth = y_val.values if len(y_val) else y_train.values
        residuals = truth - preds
        self.residual_std = float(max(0.5, np.nanstd(residuals)))

        m = TrainMetrics(
            n=len(X),
            mae=float(np.mean(np.abs(residuals))) if len(residuals) else 0.0,
            rmse=float(np.sqrt(np.mean(residuals ** 2))) if len(residuals) else 0.0,
            residual_std=self.residual_std,
        )

        # Fit a calibrator using "predicted P(over) at a synthesized line" vs. truth.
        if len(X_val) >= 50:
            lines = np.maximum(0, np.round(preds - 0.5))  # synthetic line near the mean
            raw_probs = np.array([self._raw_prob_over(p, l) for p, l in zip(preds, lines)])
            actuals = (truth > lines).astype(int)
            try:
                cal = IsotonicRegression(out_of_bounds="clip")
                cal.fit(raw_probs, actuals)
                self.calibrator = cal
                m.calibration_brier = float(np.mean((cal.predict(raw_probs) - actuals) ** 2))
            except Exception:
                self.calibrator = None

        self.metrics = m
        return m

    def _raw_prob_over(self, mu: float, line: float) -> float:
        """P(stat > line) given predicted mean."""
        mu = max(0.0, float(mu))
        if self.is_count_market and mu < 60:
            # Poisson: P(X > line) = 1 - F(floor(line))
            k = int(math.floor(line))
            if k < 0:
                return 1.0
            cdf = 0.0
            term = math.exp(-mu)
            cdf += term
            for i in range(1, k + 1):
                term *= mu / i
                cdf += term
            p = 1.0 - cdf
            # half-integer lines (e.g. 1.5) — exact; integer lines would be a push,
            # the sportsbook uses .5 lines almost always.
            return max(1e-6, min(1 - 1e-6, p))
        # Normal fallback.
        sd = max(0.5, self.residual_std)
        z = (line + 1e-9 - mu) / sd
        from math import erf, sqrt
        cdf = 0.5 * (1.0 + erf(z / sqrt(2)))
        return max(1e-6, min(1 - 1e-6, 1.0 - cdf))

    def predict_mean(self, feats: dict[str, float]) -> float:
        if self.regressor is None:
            return 0.0
        x = pd.DataFrame([feats]).reindex(columns=self.feature_names, fill_value=0.0)
        return float(max(0.0, self.regressor.predict(x)[0]))

    def predict_over_prob(self, feats: dict[str, float], line: float) -> tuple[float, float]:
        mu = self.predict_mean(feats)
        raw = self._raw_prob_over(mu, line)
        if self.calibrator is not None:
            try:
                cal = float(self.calibrator.predict([raw])[0])
                return cal, mu
            except Exception:
                pass
        return raw, mu

    # --- persistence ---
    def save(self, dir_path: Path) -> Path:
        dir_path.mkdir(parents=True, exist_ok=True)
        model_path = dir_path / f"{self.sport}__{self.market}.joblib"
        joblib.dump(
            {
                "sport": self.sport,
                "market": self.market,
                "feature_names": self.feature_names,
                "regressor": self.regressor,
                "residual_std": self.residual_std,
                "calibrator": self.calibrator,
                "metrics": self.metrics.to_dict(),
                "is_count_market": self.is_count_market,
            },
            model_path,
        )
        return model_path

    @classmethod
    def load(cls, path: Path) -> "PropModel":
        bundle = joblib.load(path)
        m = cls(bundle["sport"], bundle["market"])
        m.feature_names = bundle["feature_names"]
        m.regressor = bundle["regressor"]
        m.residual_std = bundle["residual_std"]
        m.calibrator = bundle.get("calibrator")
        m.is_count_market = bundle.get("is_count_market", True)
        d = bundle.get("metrics") or {}
        m.metrics = TrainMetrics(**d) if d else TrainMetrics()
        return m
