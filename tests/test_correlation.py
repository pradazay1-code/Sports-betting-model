"""Correlation rules + Gaussian-copula slip math (spec §5, §10)."""

import pytest

from src.engine import correlation as corr
from src.engine.correlation import Leg


def _leg(**kw):
    base = dict(event_id="game1", market="player_reception_yds", player="Ace",
                side="over", line=79.5, model_prob=0.58)
    base.update(kw)
    return Leg(**base)


def test_qb_wr_stack_positive():
    qb = _leg(market="player_pass_yds", player="Gun Slinger")
    wr = _leg(market="player_reception_yds", player="Ace")
    assert corr.leg_correlation(qb, wr) == pytest.approx(0.35)


def test_qb_rb_negative_and_blocked():
    qb = _leg(market="player_pass_yds", player="QB")
    rb = _leg(market="player_rush_yds", player="RB")
    assert corr.leg_correlation(qb, rb) == pytest.approx(-0.20)
    ok, notes = corr.validate_slip([qb, rb])
    assert not ok
    assert "negatively correlated" in notes[0]


def test_opposite_sides_flip_sign():
    qb = _leg(market="player_pass_yds", player="QB", side="over")
    wr = _leg(market="player_reception_yds", player="WR", side="under")
    assert corr.leg_correlation(qb, wr) == pytest.approx(-0.35)


def test_different_games_independent():
    a = _leg(event_id="game1")
    b = _leg(event_id="game2", player="Other")
    assert corr.leg_correlation(a, b) == 0.0


def test_max_two_legs_per_game():
    legs = [_leg(player=f"P{i}", market="player_receptions") for i in range(3)]
    ok, notes = corr.validate_slip(legs)
    assert not ok
    assert "3 legs" in notes[0]


def test_positive_stack_flagged_not_blocked():
    qb = _leg(market="player_pass_yds", player="QB")
    wr = _leg(market="player_reception_yds", player="WR")
    ok, notes = corr.validate_slip([qb, wr])
    assert ok
    assert any("size DOWN" in n for n in notes)


def test_combined_probability_independent_case():
    a = _leg(event_id="g1", model_prob=0.6)
    b = _leg(event_id="g2", player="B", model_prob=0.6)
    p = corr.combined_probability([a, b])
    assert p == pytest.approx(0.36, abs=0.02)   # independent product


def test_combined_probability_positive_corr_raises_joint():
    qb = _leg(market="player_pass_yds", player="QB", model_prob=0.6)
    wr = _leg(market="player_reception_yds", player="WR", model_prob=0.6)
    p_corr = corr.combined_probability([qb, wr])
    assert p_corr > 0.37   # above the independent 0.36


class FakeEdge:
    def __init__(self, event_id, market, player, prob):
        self.event_id, self.market, self.player = event_id, market, player
        self.side, self.line, self.model_prob = "over", 10.5, prob
        self.surface = True


def test_build_slips_returns_plus_ev_only():
    edges = [
        FakeEdge("g1", "player_pass_yds", "QB", 0.62),
        FakeEdge("g1", "player_reception_yds", "WR", 0.61),
        FakeEdge("g2", "player_points", "C", 0.42),   # weak leg
    ]
    slips = corr.build_slips(edges)
    assert slips, "expected at least the QB+WR stack"
    top = slips[0]
    assert top["combined_prob"] * 3.0 - 1.0 == pytest.approx(top["ev"], abs=1e-6)
    assert top["ev"] > 0.04
    assert top["sized_down"]   # QB+WR stack carries the size-down flag
    # the weak leg never forms a +EV slip
    assert all(l.player != "C" for s in slips for l in s["legs"])
