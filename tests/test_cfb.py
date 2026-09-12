"""Tests for the college football data client. Offline — no key, no network."""

import pytest

from lib import fetch_cfb as C


def test_missing_key_refuses_rather_than_guessing(monkeypatch):
    monkeypatch.delenv("CFBD_API_KEY", raising=False)
    with pytest.raises(C.CFBDError) as e:
        C.api_key()
    assert "collegefootballdata.com/key" in str(e.value)
    assert "will not invent" in str(e.value)


def test_season_rolls_over_in_spring(monkeypatch):
    import datetime as dt

    class FakeJan(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2027, 1, 15, tzinfo=tz)

    class FakeSep(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 12, tzinfo=tz)

    monkeypatch.setattr(C, "datetime", FakeJan)
    assert C.current_season() == 2026  # January still belongs to the 2026 season
    monkeypatch.setattr(C, "datetime", FakeSep)
    assert C.current_season() == 2026


def test_sp_spread_combines_rating_gap_with_venue_hfa(monkeypatch):
    """Home favored by the SP+ gap PLUS the venue edge, signed as a spread."""
    fake = [
        {"team": "Wyoming", "rating": 5.0},
        {"team": "Hawaii", "rating": 0.0},
    ]
    monkeypatch.setattr(C, "sp_ratings", lambda **kw: (fake, {"source": "test", "age": "0s"}))
    r = C.sp_spread("Wyoming", "Hawaii")
    assert r["sp_differential"] == 5.0
    assert r["home_field_points"] == 4.5          # 3.0 crowd + 1.5 altitude
    assert r["projected_spread"] == -9.5          # negative = home favored
    assert r["reading"] == "Wyoming -9.5"


def test_sp_spread_names_the_team_it_cannot_find(monkeypatch):
    monkeypatch.setattr(
        C, "sp_ratings", lambda **kw: ([{"team": "Oregon", "rating": 20.0}], {"source": "t", "age": "0s"})
    )
    with pytest.raises(C.CFBDError) as e:
        C.sp_spread("Oregon", "Nowhere State")
    assert "Nowhere State" in str(e.value)


def test_sp_spread_carries_a_caveat(monkeypatch):
    monkeypatch.setattr(
        C, "sp_ratings",
        lambda **kw: ([{"team": "A", "rating": 1.0}, {"team": "B", "rating": 0.0}],
                      {"source": "t", "age": "0s"}),
    )
    r = C.sp_spread("A", "B")
    assert "injuries" in r["caveat"] and "market" in r["caveat"]


def test_underdog_spread_is_signed_correctly(monkeypatch):
    """A weak home team against a strong road team must come out a home DOG."""
    fake = [{"team": "UCLA", "rating": 0.0}, {"team": "Oregon", "rating": 20.0}]
    monkeypatch.setattr(C, "sp_ratings", lambda **kw: (fake, {"source": "t", "age": "0s"}))
    r = C.sp_spread("UCLA", "Oregon")
    assert r["projected_spread"] > 0, "home underdog should be a positive spread"
    assert r["reading"].startswith("UCLA +")
