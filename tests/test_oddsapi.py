"""Tests for the The Odds API integration (no network)."""

from __future__ import annotations

from app.sources import oddsapi


def test_no_key_is_noop(monkeypatch):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    assert oddsapi.fetch_offers() == []


def test_parse_event_groups_over_under():
    event = {
        "id": "evt1", "home_team": "Lakers", "away_team": "Nuggets",
        "bookmakers": [{
            "key": "draftkings", "title": "DraftKings",
            "markets": [{
                "key": "player_points",
                "outcomes": [
                    {"name": "Over",  "description": "Nikola Jokic", "price": -115, "point": 24.5},
                    {"name": "Under", "description": "Nikola Jokic", "price": -105, "point": 24.5},
                ],
            }, {
                "key": "player_points_rebounds_assists",
                "outcomes": [
                    {"name": "Over",  "description": "Nikola Jokic", "price": -120, "point": 44.5},
                    {"name": "Under", "description": "Nikola Jokic", "price": +100, "point": 44.5},
                ],
            }],
        }],
    }
    rows = oddsapi._parse_event("NBA", event, "2026-06-25T00:00:00Z")
    by_market = {r["market"]: r for r in rows}
    assert by_market["player_points"]["over_price"] == -115
    assert by_market["player_points"]["under_price"] == -105
    assert by_market["player_points"]["line"] == 24.5
    assert by_market["player_points"]["book"] == "draftkings"
    # The combined market maps to our canonical player_pra.
    assert "player_pra" in by_market
    assert by_market["player_pra"]["line"] == 44.5


def test_parse_event_skips_unknown_markets():
    event = {"bookmakers": [{"key": "fanduel", "markets": [
        {"key": "h2h", "outcomes": [{"name": "Lakers", "price": -200}]},
    ]}]}
    assert oddsapi._parse_event("NBA", event, "t") == []


def test_fetch_offers_with_key(monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY", "TESTKEY")
    monkeypatch.setenv("ODDS_API_MAX_EVENTS", "2")
    calls = {"events": 0, "odds": 0}

    def fake_get(url, params):
        if url.endswith("/events"):
            calls["events"] += 1
            # Only return events for one sport key to keep it small.
            return [{"id": "e1"}] if "basketball_nba" in url else []
        calls["odds"] += 1
        return {"bookmakers": [{"key": "dk", "markets": [{
            "key": "player_points",
            "outcomes": [
                {"name": "Over", "description": "A B", "price": -110, "point": 20.5},
                {"name": "Under", "description": "A B", "price": -110, "point": 20.5},
            ]}]}]}

    monkeypatch.setattr(oddsapi, "_get", fake_get)
    rows = oddsapi.fetch_offers()
    assert calls["odds"] >= 1
    assert any(r["player_name"] == "A B" and r["market"] == "player_points" for r in rows)
