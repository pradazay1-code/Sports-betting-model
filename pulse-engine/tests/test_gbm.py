"""Brownian fair-value model and Kelly/arb helpers."""
import math

import numpy as np

import config
from engine import edge, gbm


def test_no_move_is_coinflip():
    assert gbm.prob_up(100.0, 100.0, 0.0001, 600) == 0.5


def test_up_move_raises_prob_and_time_decay_sharpens_it():
    sigma = 0.0001
    early = gbm.prob_up(100.0, 100.2, sigma, 800)   # +20bp, lots of time left
    late = gbm.prob_up(100.0, 100.2, sigma, 30)     # same move, almost settled
    assert 0.5 < early < late <= gbm.PROB_CAP


def test_down_move_symmetry():
    sigma = 0.0001
    up = gbm.prob_up(100.0, 100.3, sigma, 300)
    dn = gbm.prob_up(100.0, 100.0 * (100.0 / 100.3), sigma, 300)
    assert abs((1 - up) - dn) < 1e-6


def test_settled_window_pins_to_bounds():
    assert gbm.prob_up(100.0, 101.0, 0.0001, 0) == gbm.PROB_CAP
    assert gbm.prob_up(100.0, 99.0, 0.0001, 0.5) == gbm.PROB_FLOOR


def test_sigma_estimation_and_fallback():
    rng = np.random.default_rng(3)
    closes = 100 * np.cumprod(1 + rng.normal(0, 0.001, 120))
    s = gbm.sigma_per_sqrt_second(closes)
    assert abs(s - 0.001 / math.sqrt(60)) < 0.0003
    assert gbm.sigma_per_sqrt_second(np.array([100.0, 100.1])) == \
        gbm.DEFAULT_SIGMA_PER_SQRT_S


def test_kelly_suggestion():
    k = edge.kelly_suggestion(0.62, 0.54)
    # full Kelly = (b*p - q)/b with b = 0.46/0.54
    b = 0.46 / 0.54
    full = (b * 0.62 - 0.38) / b
    assert abs(k["fraction"] - full * config.KELLY_FRACTION) < 1e-3
    assert k["contracts"] > 0
    assert edge.kelly_suggestion(0.50, 0.54)["contracts"] == 0  # no edge, no stake


def test_dual_side_arb():
    assert edge.dual_side_arb(52, 44) == 4.0    # 52 + 44 = 96c -> 4c gross
    assert edge.dual_side_arb(52, 49) is None   # 101c -> no arb
    assert edge.dual_side_arb(None, 44) is None
