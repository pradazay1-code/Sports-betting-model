"""Tests for the bet slip analyzer that don't need a real model.

We monkey-patch app.models.prop_model.load to a stub so the analyzer's pricing
math is exercised without any training data or HTTP."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.betslip import Leg, analyze


class _Stub:
    n_train = 1000
    feature_cols: list[str] = []
    residual_std = 1.0
    market = ""
    sport = ""

    def __init__(self, p):
        self.p = p

    def prob_over(self, _features, _line):
        return self.p

    def predict_mean(self, _features):
        return 0.0


@pytest.fixture
def stub_models(monkeypatch):
    from app import betslip as bs
    monkeypatch.setattr(bs.prop_model, "load", lambda *_a, **_k: _Stub(0.6))
    # Skip the heavy feature builder.
    monkeypatch.setattr(bs, "build_inference_features", lambda *_a, **_k: {"r5_mean": 1.0})


def test_single_leg_positive_edge(stub_models):
    leg = Leg(sport="NBA", player_name="Test", market="player_points",
              line=24.5, side="over", price_american=+100)
    result = analyze([leg], on_date="2026-05-14")
    assert len(result.legs) == 1
    assert result.legs[0].model_prob == pytest.approx(0.6, abs=1e-6)
    assert result.parlay_edge_pct > 0


def test_two_leg_correlation_lifts_parlay(stub_models):
    legs = [
        Leg(sport="NBA", player_name="Foo Bar", market="player_points",
            line=24.5, side="over", price_american=-110),
        Leg(sport="NBA", player_name="Foo Bar", market="player_assists",
            line=6.5, side="over", price_american=-110),
    ]
    result = analyze(legs, on_date="2026-05-14")
    assert result.correlated_model_prob >= result.naive_model_prob - 1e-6
