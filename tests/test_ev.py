import math

import pytest

from app.ev import devig_two_way, kelly_fraction, price, rating
from app.utils import american_to_decimal, american_to_prob, decimal_to_american


def test_american_decimal_roundtrip():
    for am in (-200, -150, -110, +100, +110, +250, +500):
        assert decimal_to_american(american_to_decimal(am)) == am


def test_american_to_prob():
    assert math.isclose(american_to_prob(+100), 0.5, abs_tol=1e-9)
    # -200 -> implied 200/(200+100) = 0.6667
    assert math.isclose(american_to_prob(-200), 200 / 300, abs_tol=1e-9)


def test_devig_two_way_balanced():
    fo, fu = devig_two_way(-110, -110)
    assert math.isclose(fo, 0.5, abs_tol=1e-6)
    assert math.isclose(fu, 0.5, abs_tol=1e-6)


def test_devig_two_way_skewed():
    # over -300 / under +250 has heavy lean to over
    fo, fu = devig_two_way(-300, +250)
    assert fo > fu
    assert math.isclose(fo + fu, 1.0, abs_tol=1e-9)


def test_kelly_fraction_positive_edge():
    # 60% prob at +100 -> kelly = (1*0.6 - 0.4)/1 = 0.2
    assert math.isclose(kelly_fraction(0.6, +100), 0.2, abs_tol=1e-9)


def test_kelly_fraction_no_edge_clipped():
    # 40% at +100 would yield negative kelly -> 0
    assert kelly_fraction(0.4, +100) == 0.0


def test_price_edge_positive():
    p = price("over", 0.6, 0.5, +100)
    assert p.edge_pct > 0
    assert p.kelly_stake > 0


def test_rating_bounds():
    r, parts = rating(edge_pct=10.0, model_prob=0.65, fair_prob=0.5,
                      n_train_rows=1500, n_books=3)
    assert 0.0 <= r <= 100.0
    for k, v in parts.items():
        assert 0.0 <= v <= 1.0
