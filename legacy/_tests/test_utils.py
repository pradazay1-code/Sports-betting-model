from pradapicks.utils import (
    american_to_decimal,
    american_to_implied,
    decimal_to_american,
    edge_pct,
    kelly_fraction,
    two_way_no_vig,
)


def test_american_to_decimal_positive():
    assert abs(american_to_decimal(150) - 2.5) < 1e-9


def test_american_to_decimal_negative():
    assert abs(american_to_decimal(-200) - 1.5) < 1e-9


def test_decimal_to_american_roundtrip():
    for a in (-300, -200, -150, -110, 100, 120, 150, 250, 400):
        assert decimal_to_american(american_to_decimal(a)) == a


def test_implied():
    assert abs(american_to_implied(-110) - (110 / 210)) < 1e-9


def test_two_way_no_vig_sums_to_one():
    p_o, p_u = two_way_no_vig(-110, -110)
    assert abs(p_o + p_u - 1.0) < 1e-9
    assert abs(p_o - 0.5) < 1e-9


def test_edge_zero_at_fair():
    p = american_to_implied(-110)
    assert abs(edge_pct(p, -110)) < 1e-6


def test_edge_positive_when_model_better():
    assert edge_pct(0.6, -110) > 0


def test_kelly_zero_when_no_edge():
    p = american_to_implied(-110)
    assert kelly_fraction(p, -110) < 1e-6
