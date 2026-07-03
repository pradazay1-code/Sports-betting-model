"""Odds conversion math produces known values for known inputs (spec §10)."""

import pytest

from src.ingest.odds import american_to_decimal, canonical_side, implied_prob


def test_positive_american():
    assert american_to_decimal(130) == pytest.approx(2.30)
    assert american_to_decimal(100) == pytest.approx(2.00)


def test_negative_american():
    assert american_to_decimal(-150) == pytest.approx(1.6667, abs=1e-4)
    assert american_to_decimal(-110) == pytest.approx(1.9091, abs=1e-4)


def test_invalid_american_rejected():
    with pytest.raises(ValueError):
        american_to_decimal(50)


def test_implied_prob():
    assert implied_prob(2.0) == pytest.approx(0.5)
    assert implied_prob(american_to_decimal(-110)) == pytest.approx(0.5238, abs=1e-4)


def test_canonical_side():
    assert canonical_side("Over", "A", "B") == "over"
    assert canonical_side("Under", "A", "B") == "under"
    assert canonical_side("Draw", "France", "Brazil") == "draw"
    assert canonical_side("France", "France", "Brazil") == "home"
    assert canonical_side("Brazil", "France", "Brazil") == "away"
    assert canonical_side("Somebody Else", "France", "Brazil") == "other"
