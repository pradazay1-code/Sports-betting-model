"""Tests for the price math. If these break, every recommendation is wrong."""

import math

import pytest

from lib import odds


# --- conversions -----------------------------------------------------------


@pytest.mark.parametrize(
    "american,decimal",
    [(-110, 1.909090909), (100, 2.0), (-100, 2.0), (150, 2.5), (-200, 1.5), (250, 3.5)],
)
def test_american_to_decimal(american, decimal):
    assert odds.american_to_decimal(american) == pytest.approx(decimal, abs=1e-6)


@pytest.mark.parametrize("american", [-110, -250, 100, 137, 900, -1200])
def test_conversion_round_trips(american):
    dec = odds.american_to_decimal(american)
    assert odds.decimal_to_american(dec) == pytest.approx(american, abs=0.01)


def test_even_money_normalizes_to_plus_100():
    """-100 and +100 are the same price; +100 is the canonical way to write it."""
    assert odds.american_to_decimal(-100) == odds.american_to_decimal(100) == 2.0
    assert odds.decimal_to_american(2.0) == 100.0


def test_implied_prob_known_values():
    assert odds.implied_prob(-110) == pytest.approx(0.5238095, abs=1e-6)
    assert odds.implied_prob(100) == pytest.approx(0.5, abs=1e-9)
    assert odds.implied_prob(-200) == pytest.approx(2 / 3, abs=1e-9)


def test_prob_to_american_round_trips():
    for p in (0.1, 0.25, 0.5, 0.5238095, 0.75, 0.9):
        assert odds.implied_prob(odds.prob_to_american(p)) == pytest.approx(p, abs=1e-6)


def test_invalid_odds_rejected():
    for bad in (0, 50, -99, 99.5):
        with pytest.raises(ValueError):
            odds.american_to_decimal(bad)


# --- vig -------------------------------------------------------------------


def test_standard_two_way_hold():
    # -110/-110 is the canonical 4.55% hold.
    assert odds.overround([-110, -110]) == pytest.approx(1.047619, abs=1e-6)
    assert odds.hold([-110, -110]) == pytest.approx(0.04545, abs=1e-4)


def test_fair_market_has_no_hold():
    assert odds.hold([100, 100]) == pytest.approx(0.0, abs=1e-12)


# --- devig -----------------------------------------------------------------


@pytest.mark.parametrize("method", odds.DEVIG_METHODS)
@pytest.mark.parametrize(
    "prices",
    [[-110, -110], [118, -128], [250, -300], [-500, 380], [150, 130, 220], [-200, 500, 900, 1200]],
)
def test_every_method_sums_to_one(method, prices):
    p = odds.devig(prices, method)
    assert sum(p) == pytest.approx(1.0, abs=1e-9)
    assert all(0.0 < x < 1.0 for x in p)


def test_devig_preserves_ordering():
    # The favorite must stay the favorite under every method.
    for method in odds.DEVIG_METHODS:
        p = odds.devig([250, -300], method)
        assert p[0] < p[1]


def test_fair_price_sits_between_posted_prices():
    prices = [118, -128]
    for method in odds.DEVIG_METHODS:
        fair = odds.devig(prices, method)
        for raw, f in zip((odds.implied_prob(x) for x in prices), fair):
            assert f <= raw + 1e-12  # devigging can only remove probability


def test_power_solves_its_own_equation():
    prices = [250, -300]
    q = [odds.implied_prob(x) for x in prices]
    p = odds.devig(prices, "power")
    # Recover k from the first outcome and confirm it reproduces the second.
    k = math.log(p[0]) / math.log(q[0])
    assert sum(x**k for x in q) == pytest.approx(1.0, abs=1e-6)


def test_symmetric_market_devigs_to_even():
    for method in odds.DEVIG_METHODS:
        p = odds.devig([-110, -110], method)
        assert p[0] == pytest.approx(0.5, abs=1e-9)


def test_already_fair_market_is_unchanged():
    p = odds.devig([100, 100], "multiplicative")
    assert p == pytest.approx([0.5, 0.5], abs=1e-12)


def test_method_defaults_by_market_width():
    assert odds.default_method(2) == "power"
    assert odds.default_method(3) == "multiplicative"
    assert odds.default_method(12) == "multiplicative"


def test_devig_spread_flags_disagreement():
    tight = odds.devig_spread([-110, -110])
    assert not tight["meaningful"]
    # A heavy longshot is where the methods actually diverge.
    wide = odds.devig_spread([-2000, 1100])
    assert wide["widest_spread"] > tight["widest_spread"]


def test_additive_clamps_instead_of_going_negative():
    # An extreme longshot can drive naive additive devig below zero.
    p = odds.devig([-5000, 2500], "additive")
    assert all(x > 0 for x in p)
    assert sum(p) == pytest.approx(1.0, abs=1e-9)


def test_unknown_method_rejected():
    with pytest.raises(ValueError):
        odds.devig([-110, -110], "vibes")


# --- EV and Kelly ----------------------------------------------------------


def test_ev_zero_at_fair_price():
    assert odds.ev(0.5, 2.0) == pytest.approx(0.0, abs=1e-12)


def test_ev_positive_when_offered_beats_fair():
    assert odds.ev(0.5, 2.2) == pytest.approx(0.1, abs=1e-12)


def test_kelly_known_value():
    # p=0.55 at +100: f = (0.55*1 - 0.45)/1 = 0.10 full Kelly.
    assert odds.kelly(0.55, 2.0, divisor=1.0) == pytest.approx(0.10, abs=1e-12)
    assert odds.kelly(0.55, 2.0) == pytest.approx(0.025, abs=1e-12)  # quarter


def test_kelly_refuses_negative_edge():
    assert odds.kelly(0.45, 2.0) == 0.0
    assert odds.kelly(0.5, 1.9091) == 0.0


def test_stake_respects_the_two_unit_ceiling():
    # A huge edge would want far more than 2u; the cap is not negotiable.
    assert odds.stake_units(0.95, 100) == odds.MAX_STAKE_UNITS


def test_price_edge_rejects_sub_threshold_ev():
    e = odds.price_edge(0.505, 100)  # +1% EV
    assert not e.is_bet
    assert e.stake_units == 0.0
    assert "threshold" in e.note


def test_price_edge_reports_all_three_forms():
    e = odds.price_edge(0.4482, 132)
    assert e.fair_american == pytest.approx(123.1, abs=0.2)
    assert e.offered_american == 132
    assert e.ev == pytest.approx(0.0399, abs=1e-3)
    assert e.is_bet


# --- parlays ---------------------------------------------------------------


def test_parlay_payout_multiplies_legs():
    assert odds.parlay_decimal([100, 100]) == pytest.approx(4.0)
    assert odds.parlay_decimal([-110, -110]) == pytest.approx(1.9090909**2, abs=1e-6)


def test_four_independent_legs_multiply_the_hold():
    """The headline claim in CLAUDE.md — four -110 legs hand the book ~17%."""
    a = odds.parlay_analysis([-110] * 4)
    assert a["true_prob"] == pytest.approx(0.0625, abs=1e-6)
    assert a["book_hold"] == pytest.approx(0.1697, abs=1e-3)
    assert a["hold_if_bet_straight"] == pytest.approx(0.0455, abs=1e-3)
    assert a["hold_multiple"] > 3.0
    assert not a["is_bet"]


def test_parlay_without_fair_probs_does_not_use_raw_implied():
    """Raw implied would price the vig as truth and show a 0% hold."""
    a = odds.parlay_analysis([-110, -110])
    assert a["leg_fair_probs"][0] == pytest.approx(0.5, abs=1e-3)
    assert a["book_hold"] > 0.05
    assert "approximated" in a["leg_fair_prob_source"]


def test_correlation_uplift_raises_true_probability():
    base = odds.parlay_analysis([-110, -110], [0.5, 0.5])
    corr = odds.parlay_analysis([-110, -110], [0.5, 0.5], correlation_uplift=0.20)
    assert corr["true_prob"] > base["true_prob"]
    assert corr["ev"] > base["ev"]


def test_parlay_cannot_beat_its_likeliest_leg():
    a = odds.parlay_analysis([-110, -110], [0.5, 0.5], correlation_uplift=5.0)
    assert a["true_prob"] <= 0.5 + 1e-12


def test_round_robin_combination_count():
    rr = odds.round_robin([-110] * 4, [0.5] * 4, 2)
    assert rr["n_combos"] == 6  # C(4,2)
    assert rr["total_risk"] == pytest.approx(6.0)


def test_round_robin_does_not_manufacture_ev():
    """Variance reduction, not hold reduction. -EV legs stay -EV."""
    rr = odds.round_robin([-110] * 4, [0.5] * 4, 2)
    assert rr["ev_per_unit_risked"] < 0


# --- anchoring -------------------------------------------------------------


def test_pinnacle_wins_the_anchor():
    a = odds.sharp_anchor({"draftkings": -105, "pinnacle": -110, "fanduel": -108})
    assert a["anchor"] == "pinnacle"
    assert a["tier"] == "sharp"


def test_circa_anchors_when_pinnacle_absent():
    a = odds.sharp_anchor({"draftkings": -105, "circa": -110})
    assert a["anchor"] == "circa"


def test_falls_back_to_median_with_only_soft_books():
    a = odds.sharp_anchor({"draftkings": -105, "fanduel": -115, "betmgm": -110})
    assert a["anchor"] == "market_median"
    assert a["tier"] == "median"
    assert a["price"] == -110
    assert "Lower confidence" in a["note"]


def test_empty_book_list_is_handled():
    a = odds.sharp_anchor({})
    assert a["anchor"] is None


# --- CLV -------------------------------------------------------------------


def test_beating_the_close():
    c = odds.clv(taken_american=-105, closing_american=-125)
    assert c["beat_close"]
    assert c["pct"] > 0
    assert c["ev_at_close"] > 0


def test_losing_to_the_close():
    c = odds.clv(taken_american=-125, closing_american=-105)
    assert not c["beat_close"]
    assert c["pct"] < 0


def test_clv_zero_when_line_does_not_move():
    c = odds.clv(-110, -110)
    assert c["pct"] == pytest.approx(0.0, abs=1e-12)
    assert c["cents"] == 0
