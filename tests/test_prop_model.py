"""Lightweight tests on prop_model.TrainedModel without training."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.models.prop_model import TrainedModel


class _ConstModel:
    def predict(self, X):
        return np.array([float(X[0][0])])


class _NaNModel:
    def predict(self, X):
        return np.array([float("nan")])


def _make(model, market="player_points", residual_std=2.0):
    return TrainedModel(
        sport="NBA", market=market, model=model,
        feature_cols=["r5_mean"], residual_std=residual_std,
        n_train=100, mae=1.0, brier=None, log_loss=None,
        extra={"median_target": 20.0},
    )


def test_prob_over_continuous():
    tm = _make(_ConstModel())
    p = tm.prob_over({"r5_mean": 24.0}, 22.5)
    assert 0.0 < p < 1.0
    assert p > 0.5  # mu > line -> over is favored


def test_prob_over_count_market():
    tm = _make(_ConstModel(), market="player_threes")
    p = tm.prob_over({"r5_mean": 3.0}, 2.5)
    assert 0.0 < p < 1.0


def test_prob_over_nan_falls_back_to_50():
    tm = _make(_NaNModel())
    p = tm.prob_over({"r5_mean": float("nan")}, 22.5)
    assert math.isclose(p, 0.5)


def test_predict_mean_uses_median_on_nan_features():
    tm = _make(_ConstModel())
    mean = tm.predict_mean({"r5_mean": float("inf")})
    assert math.isclose(mean, 20.0)  # median_target fallback
