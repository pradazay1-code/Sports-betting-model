"""
Tests for the edge-detection statistics.

These lock down the numbers the desk quotes when someone asks for a guaranteed
pick. If they drift, the agent starts making claims it can't support.
"""

import pytest

from lib import backtest as bt
from lib import db


# --- normal quantiles ------------------------------------------------------


def test_inverse_normal_matches_known_quantiles():
    assert bt._z(0.95) == pytest.approx(1.6449, abs=1e-3)
    assert bt._z(0.975) == pytest.approx(1.9600, abs=1e-3)
    assert bt._z(0.80) == pytest.approx(0.8416, abs=1e-3)
    assert bt._z(0.5) == pytest.approx(0.0, abs=1e-6)


def test_inverse_normal_is_antisymmetric():
    for p in (0.01, 0.1, 0.3):
        assert bt._z(p) == pytest.approx(-bt._z(1 - p), abs=1e-6)


def test_normal_cdf_inverts_z():
    for p in (0.05, 0.25, 0.5, 0.9, 0.99):
        assert bt._normal_cdf(bt._z(p)) == pytest.approx(p, abs=1e-6)


# --- breakeven and per-bet distribution ------------------------------------


def test_breakeven_at_standard_juice():
    assert bt.breakeven_rate(-110) == pytest.approx(0.5238095, abs=1e-6)
    assert bt.breakeven_rate(100) == pytest.approx(0.5, abs=1e-9)


def test_no_edge_at_breakeven():
    mean, _ = bt.profit_per_bet(bt.breakeven_rate(-110), -110)
    assert mean == pytest.approx(0.0, abs=1e-9)


def test_noise_dwarfs_signal():
    """The ratio that explains why betting takes thousands of bets to evaluate."""
    mean, sd = bt.profit_per_bet(0.55, -110)
    assert mean == pytest.approx(0.05, abs=1e-3)
    assert sd == pytest.approx(0.95, abs=0.01)
    assert sd / mean > 15


def test_a_point_of_hit_rate_is_worth_about_two_percent():
    be = bt.breakeven_rate(-110)
    m0, _ = bt.profit_per_bet(be, -110)
    m1, _ = bt.profit_per_bet(be + 0.01, -110)
    assert (m1 - m0) == pytest.approx(0.0191, abs=1e-3)


# --- sample size -----------------------------------------------------------


def test_proving_a_five_percent_roi_takes_thousands_of_bets():
    """The headline number in skills/probability-reality.md."""
    r = bt.required_sample_size(0.55, -110)
    assert 2000 < r["n_required"] < 2500
    assert r["edge_pct_points"] == pytest.approx(2.62, abs=0.05)


def test_smaller_edges_need_more_bets():
    big = bt.required_sample_size(0.58, -110)["n_required"]
    small = bt.required_sample_size(0.54, -110)["n_required"]
    assert small > big * 3


def test_no_edge_has_no_sample_size():
    r = bt.required_sample_size(0.50, -110)
    assert r["n_required"] is None
    assert "No edge" in r["note"]


# --- significance and bootstrap --------------------------------------------


def test_small_sample_is_never_conclusive():
    assert not bt.roi_significance(3.0, 10.0, 10)["significant_at_05"]


def test_large_consistent_edge_is_detected():
    sig = bt.roi_significance(profit_units=150.0, staked_units=3000.0, n_bets=3000)
    assert sig["significant_at_05"]
    assert sig["p_value"] < 0.05


def test_bootstrap_spans_zero_on_a_short_record():
    results = [0.909, -1, 0.909, -1, 0.909, -1, 0.909, -1, 0.909, -1, 0.909, 0.909]
    b = bt.bootstrap_roi_ci(results, iterations=2000)
    assert b["spans_zero"], "a 12-bet record cannot demonstrate an edge"
    assert b["ci_low"] < b["observed_mean"] < b["ci_high"]


def test_bootstrap_is_deterministic_with_a_seed():
    r = [0.909, -1] * 25
    assert bt.bootstrap_roi_ci(r, iterations=500) == bt.bootstrap_roi_ci(r, iterations=500)


def test_bootstrap_needs_a_sample():
    assert "note" in bt.bootstrap_roi_ci([1.0])


# --- what a real edge feels like -------------------------------------------


def test_a_winning_bettor_still_loses_sometimes():
    """The single most useful fact to tell someone on a cold streak."""
    d = bt.drawdown_simulation(0.55, -110, n_bets=500, trials=2000)
    assert 0.05 < d["prob_losing_overall"] < 0.20
    assert d["expected_units"] > 0
    assert d["median_max_drawdown"] > 5


def test_longer_samples_reduce_the_chance_of_losing():
    short = bt.drawdown_simulation(0.55, -110, n_bets=100, trials=1500)
    long = bt.drawdown_simulation(0.55, -110, n_bets=2000, trials=1500)
    assert long["prob_losing_overall"] < short["prob_losing_overall"]


def test_losing_streaks_are_expected_not_anomalous():
    p7 = bt.losing_streak_probability(0.55, 7, 500)
    assert 0.5 < p7 < 0.8, "a 7-bet skid should be more likely than not"
    assert bt.losing_streak_probability(0.55, 3, 500) > 0.99


def test_streak_probability_is_monotonic():
    probs = [bt.losing_streak_probability(0.55, s, 500) for s in (4, 6, 8, 10, 12)]
    assert probs == sorted(probs, reverse=True)


def test_streak_probability_bounds():
    assert bt.losing_streak_probability(0.55, 5, 0) == 0.0
    assert bt.losing_streak_probability(1.0, 2, 100) == pytest.approx(0.0)
    assert bt.losing_streak_probability(0.0, 2, 100) == pytest.approx(1.0)


# --- reality check ---------------------------------------------------------


def test_hot_record_has_a_uselessly_wide_interval():
    r = bt.reality_check(12, 3, -110)
    lo, hi = r["ci95"]
    assert hi - lo > 0.30, "15 bets cannot pin down a hit rate"
    assert lo < 0.60


def test_short_winning_record_proves_nothing():
    r = bt.reality_check(7, 3, -110)
    assert not r["proves_an_edge"]
    assert r["ci_includes_breakeven"]


def test_wilson_interval_contains_the_estimate():
    for wins, n in ((5, 10), (50, 100), (1, 3), (0, 5)):
        lo, hi = bt.hit_rate_ci(wins, n)
        assert lo <= wins / n <= hi
        assert 0.0 <= lo <= hi <= 1.0


def test_wilson_narrows_with_sample_size():
    small = bt.hit_rate_ci(6, 10)
    large = bt.hit_rate_ci(600, 1000)
    assert (large[1] - large[0]) < (small[1] - small[0])


def test_empty_record_is_handled():
    assert "note" in bt.reality_check(0, 0)


# --- backtesting the log ---------------------------------------------------


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "bt.db")
    yield c
    c.close()


def test_backtest_of_an_empty_log(conn):
    r = bt.backtest_log(conn)
    assert r.settled == 0


def test_backtest_calls_a_small_sample_too_small(conn):
    for i in range(10):
        b = db.log_bet(conn, sport="NFL", event=f"g{i}", market="h2h", side="s",
                       price_taken=-110, book="dk", stake_units=1.0, fair_prob=0.55)
        db.grade_bet(conn, b, "win" if i % 2 else "loss")
    r = bt.backtest_log(conn)
    assert r.settled == 10
    assert "too small" in r.verdict


def test_backtest_surfaces_negative_clv_over_a_winning_record(conn):
    """A winning record with negative CLV is luck, and the verdict must say so."""
    for i in range(40):
        b = db.log_bet(conn, sport="NFL", event=f"g{i}", market="h2h", side="s",
                       price_taken=-110, book="dk", stake_units=1.0, fair_prob=0.55)
        db.set_closing_line(conn, b, 100)   # took -110, closed +100 = lost to the close
        db.grade_bet(conn, b, "win" if i % 3 else "loss")
    r = bt.backtest_log(conn)
    assert r.avg_clv < 0
    assert "market is beating these numbers" in r.verdict


def test_backtest_flags_missing_closing_lines(conn):
    for i in range(40):
        b = db.log_bet(conn, sport="NFL", event=f"g{i}", market="h2h", side="s",
                       price_taken=-110, book="dk", stake_units=1.0, fair_prob=0.55)
        db.grade_bet(conn, b, "win" if i % 2 else "loss")
    assert "closing line" in bt.backtest_log(conn).verdict


def test_backtest_excludes_pending_and_void(conn):
    a = db.log_bet(conn, sport="NFL", event="a", market="h2h", side="s",
                   price_taken=-110, book="dk", stake_units=1.0)
    db.grade_bet(conn, a, "win")
    db.log_bet(conn, sport="NFL", event="b", market="h2h", side="s",
               price_taken=-110, book="dk", stake_units=1.0)  # stays pending
    c = db.log_bet(conn, sport="NFL", event="c", market="h2h", side="s",
                   price_taken=-110, book="dk", stake_units=1.0)
    db.grade_bet(conn, c, "void")
    assert bt.backtest_log(conn).settled == 1
