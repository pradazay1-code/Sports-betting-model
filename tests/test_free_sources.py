"""Tests for keyless public feeds. Fixtures only — no network."""

import pytest

from lib import free_sources as F

SCOREBOARD = {
    "events": [{
        "id": "401", "shortName": "KC @ BUF", "date": "2026-09-07T20:25Z",
        "status": {"type": {"state": "pre", "shortDetail": "Sun 4:25 PM"}},
        "competitions": [{
            "neutralSite": False,
            "venue": {"fullName": "Highmark Stadium"},
            "broadcasts": [{"names": ["CBS"]}],
            "odds": [{"details": "BUF -2.5", "overUnder": 48.5,
                      "provider": {"name": "ESPN BET"}}],
            "competitors": [
                {"homeAway": "home", "score": "0",
                 "team": {"displayName": "Buffalo Bills", "abbreviation": "BUF"},
                 "records": [{"summary": "1-0"}], "curatedRank": {"current": 3}},
                {"homeAway": "away", "score": "0",
                 "team": {"displayName": "Kansas City Chiefs", "abbreviation": "KC"},
                 "records": [{"summary": "1-0"}]},
            ],
        }],
    }]
}


def test_fcs_is_reachable_without_a_key():
    """Group 81 is the keyless answer to college football's hardest data problem."""
    assert F.CFB_FCS_GROUP == 81
    assert F.CFB_FBS_GROUP == 80
    assert "cfb" in F.LEAGUES


def test_unknown_league_lists_the_known_ones():
    with pytest.raises(F.FreeSourceError) as e:
        F.scoreboard("quidditch")
    assert "nfl" in str(e.value)


def test_parse_pulls_teams_odds_and_venue():
    row = F.parse_scoreboard(SCOREBOARD)[0]
    assert row["home"]["name"] == "Buffalo Bills"
    assert row["away"]["abbr"] == "KC"
    assert row["spread"] == "BUF -2.5"
    assert row["total"] == 48.5
    assert row["venue"] == "Highmark Stadium"
    assert row["home"]["rank"] == 3
    assert row["broadcast"] == "CBS"


def test_parse_survives_a_game_with_no_odds():
    bare = {"events": [{"id": "1", "shortName": "A @ B",
                        "competitions": [{"competitors": []}]}]}
    row = F.parse_scoreboard(bare)[0]
    assert row["spread"] is None and row["total"] is None


def test_board_stub_warns_that_consensus_is_not_sharp():
    stub = F.to_board_stub(F.parse_scoreboard(SCOREBOARD), "KC @ BUF")
    assert "CONSENSUS IS NOT A SHARP PRICE" in stub["note"]
    assert "BUF -2.5" in stub["note"]
    assert stub["markets"][0]["name"] == "moneyline"


def test_board_stub_names_the_missing_event():
    with pytest.raises(F.FreeSourceError) as e:
        F.to_board_stub(F.parse_scoreboard(SCOREBOARD), "SF @ LAR")
    assert "SF @ LAR" in str(e.value)
