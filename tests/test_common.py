"""Probability utilities produce known values for known inputs (spec §10)."""

import pytest

from src.models import common as c


def test_poisson_pmf_known_values():
    # P(X=0 | lam=1) = e^-1
    assert c.poisson_pmf(0, 1.0) == pytest.approx(0.367879, abs=1e-5)
    assert c.poisson_pmf(2, 3.0) == pytest.approx(0.224042, abs=1e-5)


def test_poisson_cdf_sums_to_one():
    assert sum(c.poisson_pmf(k, 5.0) for k in range(60)) == pytest.approx(1.0, abs=1e-9)


def test_prob_over_half_lines():
    # lam=6.0, over 6.5 -> 1 - CDF(6) — known value ~0.393697
    assert c.prob_over_poisson(6.5, 6.0) == pytest.approx(0.39370, abs=1e-4)
    # over 0.5 with tiny lam is near lam
    assert c.prob_over_poisson(0.5, 0.05) == pytest.approx(0.04877, abs=1e-4)


def test_negbin_matches_poisson_at_high_dispersion():
    for k in range(8):
        assert c.negbin_pmf(k, 4.0, 1e7) == pytest.approx(c.poisson_pmf(k, 4.0), abs=1e-5)


def test_negbin_fatter_tails_than_poisson():
    assert c.prob_over_negbin(9.5, 5.0, 2.0) > c.prob_over_poisson(9.5, 5.0)


def test_prob_over_normal():
    assert c.prob_over_normal(0.0, 0.0, 1.0) == pytest.approx(0.5)
    assert c.prob_over_normal(249.5, 265.0, 40.0) == pytest.approx(0.6512, abs=1e-3)


def test_monte_carlo_agrees_with_normal():
    mc = c.monte_carlo_over(249.5, lambda rng: rng.gauss(265.0, 40.0), n=20000)
    assert mc == pytest.approx(0.6512, abs=0.02)


def test_decay_weights():
    w = c.decay_weights(3, 0.85)
    assert w == pytest.approx([1.0, 0.85, 0.7225])


def test_weighted_recent_rate_favors_recent():
    rising = c.weighted_recent_rate([9, 8, 7, 2, 2, 2])
    assert rising > 5.0  # recent 9,8,7 dominate the older 2s


def test_regress_to_mean():
    # tiny sample -> pulled hard toward league
    assert c.regress_to_mean(0.40, 2, 0.22, 60) == pytest.approx(0.2258, abs=1e-3)
    # big sample -> stays near player
    assert c.regress_to_mean(0.30, 500, 0.22, 60) == pytest.approx(0.2914, abs=1e-3)


def test_opponent_adjustment():
    assert c.opponent_adjustment(0.25, 0.22) == pytest.approx(1.1364, abs=1e-3)
    assert c.opponent_adjustment(0.25, 0.22, power=0.5) < 1.1364


def test_shrink_probability():
    assert c.shrink_probability(0.60, 1.0) == pytest.approx(0.60)
    assert c.shrink_probability(0.60, 0.5) == pytest.approx(0.55)
    assert c.shrink_probability(0.60, 0.0) == pytest.approx(0.50)
