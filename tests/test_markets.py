from app.sources.markets import map_market


def test_nba_basic():
    assert map_market("NBA", "Player Points") == "player_points"
    assert map_market("NBA", "Total Rebounds") == "player_rebounds"
    assert map_market("NBA", "Pts+Rebs+Asts") == "player_pra"


def test_mlb_basic():
    assert map_market("MLB", "Total Bases") == "batter_total_bases"
    assert map_market("MLB", "Pitcher Strikeouts") == "pitcher_strikeouts"


def test_nhl_basic():
    assert map_market("NHL", "Shots On Goal") == "player_shots_on_goal"
    assert map_market("NHL", "Saves") == "goalie_saves"


def test_unknown_returns_none():
    assert map_market("NBA", "Weird Wacky Market") is None
    assert map_market("MLB", "") is None
    assert map_market("XYZ", "Anything") is None
