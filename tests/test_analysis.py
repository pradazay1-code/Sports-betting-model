"""Tests for the deep bet-analysis grading engine.

Models are stubbed so the grading math + letter mapping are exercised without
training data or HTTP.
"""

from __future__ import annotations

import pytest

from app import analysis
from app.analysis import GRADES, _letter_from, grade, grade_single, grade_slip
from app.betslip import Leg


class _Stub:
    n_train = 1500
    feature_cols: list[str] = []
    residual_std = 1.0
    market = ""
    sport = ""

    def __init__(self, p, mean=20.0):
        self.p = p
        self.mean = mean

    def prob_over(self, _features, _line):
        return self.p

    def predict_mean(self, _features):
        return self.mean


@pytest.fixture
def stub_strong(monkeypatch):
    monkeypatch.setattr(analysis.prop_model, "load", lambda *_a, **_k: _Stub(0.66, mean=28.0))
    monkeypatch.setattr(
        analysis, "build_inference_features",
        lambda *_a, **_k: {"r5_mean": 27.0, "r10_mean": 26.0, "r25_mean": 24.0,
                           "r10_std": 4.0, "season_avg": 25.0, "n_games": 60})


def test_letter_ordering_is_well_formed():
    assert GRADES[0] == "F" and GRADES[-1] == "A+"
    # Strong rating + edge -> top of scale; weak/negative -> bottom.
    assert _letter_from(95, 8.0) == "A+"
    assert _letter_from(95, -8.0) in ("D-", "F", "D")  # capped by negative edge


def test_negative_edge_cannot_grade_above_ceiling():
    g = _letter_from(99, -2.0)
    assert GRADES.index(g) <= GRADES.index("C-")


def test_single_bet_positive_edge_grades_well(stub_strong):
    out = grade_single({
        "sport": "NBA", "player_name": "Test Star", "market": "player_points",
        "side": "over", "line": 24.5, "price_american": -110,
    }, on_date="2026-05-14")
    assert out.modeled is True
    assert out.edge_pct > 0
    assert out.projection == 28.0
    assert out.margin == pytest.approx(3.5, abs=1e-6)
    assert out.grade[0] in ("A", "B")
    assert out.strengths  # non-empty narrative
    assert "Grade" in out.summary


def test_unmodeled_bet_is_flagged(monkeypatch):
    monkeypatch.setattr(analysis.prop_model, "load", lambda *_a, **_k: None)
    monkeypatch.setattr(analysis, "build_inference_features", lambda *_a, **_k: None)
    out = grade_single({
        "sport": "EPL", "player_name": "Unknown Player", "market": "player_shots",
        "side": "over", "line": 1.5, "price_american": -120,
    }, on_date="2026-05-14")
    assert out.modeled is False
    assert any("un-vetted" in c or "history" in c for c in out.concerns)


def test_slip_grade_includes_per_leg_and_parlay(stub_strong):
    legs = [
        {"sport": "NBA", "player_name": "A B", "market": "player_points",
         "side": "over", "line": 24.5, "price_american": -110},
        {"sport": "NBA", "player_name": "A B", "market": "player_assists",
         "side": "over", "line": 5.5, "price_american": -110},
    ]
    out = grade_slip(legs, on_date="2026-05-14")
    assert out["n_legs"] == 2
    assert len(out["legs"]) == 2
    assert out["parlay"]["grade"] in GRADES
    assert "summary" in out["parlay"]


def test_top_level_grade_dispatches_on_type(stub_strong):
    single = grade({"sport": "NBA", "player_name": "A B", "market": "player_points",
                    "side": "over", "line": 24.5, "price_american": -110})
    assert "grade" in single and "legs" not in single
    parlay = grade([
        {"sport": "NBA", "player_name": "A B", "market": "player_points",
         "side": "over", "line": 24.5, "price_american": -110},
        {"sport": "NBA", "player_name": "C D", "market": "player_points",
         "side": "over", "line": 18.5, "price_american": -110},
    ])
    assert "parlay" in parlay and "legs" in parlay
