"""NFL volume/efficiency models + game-script logic (spec §10)."""

import pytest

from src.ingest import nfl
from src.models import nfl_model

CSV = """player_id,player_display_name,position,recent_team,season,week,targets,receptions,receiving_yards,receiving_tds,carries,rushing_yards,rushing_tds,attempts,passing_yards,passing_tds
00-001,Ace Receiver,WR,KC,2025,1,11,8,102,1,0,0,0,0,0,0
00-001,Ace Receiver,WR,KC,2025,2,9,6,74,0,1,6,0,0,0,0
00-001,Ace Receiver,WR,KC,2025,3,12,9,118,1,0,0,0,0,0,0
00-001,Ace Receiver,WR,KC,2025,4,8,5,61,0,0,0,0,0,0,0
00-001,Ace Receiver,WR,KC,2025,5,10,7,88,1,0,0,0,0,0,0
00-002,Work Horse,RB,SF,2025,1,3,3,22,0,22,105,1,0,0,0
00-002,Work Horse,RB,SF,2025,2,4,3,18,0,18,84,0,0,0,0
00-002,Work Horse,RB,SF,2025,3,2,2,11,0,25,131,2,0,0,0
00-002,Work Horse,RB,SF,2025,4,5,4,31,0,20,92,1,0,0,0
00-003,Gun Slinger,QB,KC,2025,1,0,0,0,0,3,12,0,35,285,2
00-003,Gun Slinger,QB,KC,2025,2,0,0,0,0,2,8,0,41,310,3
00-003,Gun Slinger,QB,KC,2025,3,0,0,0,0,4,18,1,38,264,1
00-003,Gun Slinger,QB,KC,2025,4,0,0,0,0,1,3,0,44,329,2
"""


@pytest.fixture
def weeks_wr():
    rows = nfl.parse_weekly_csv(CSV)
    wr = [r for r in rows if r["player_id"] == "00-001"]
    wr.sort(key=lambda r: r["week"], reverse=True)
    return wr


@pytest.fixture
def weeks_rb():
    rows = nfl.parse_weekly_csv(CSV)
    rb = [r for r in rows if r["player_id"] == "00-002"]
    rb.sort(key=lambda r: r["week"], reverse=True)
    return rb


def test_parse_weekly_csv():
    rows = nfl.parse_weekly_csv(CSV)
    assert len(rows) == 13
    assert rows[0]["player_name"] == "Ace Receiver"
    assert rows[0]["team"] == "KC"
    assert rows[0]["receiving_yards"] == 102.0


def test_game_script_factor():
    # underdog (+7) passes more, runs less
    assert nfl_model.game_script_factor(7.0, is_pass_stat=True) > 1.0
    assert nfl_model.game_script_factor(7.0, is_pass_stat=False) < 1.0
    # favorite (-7) the reverse
    assert nfl_model.game_script_factor(-7.0, is_pass_stat=True) < 1.0
    assert nfl_model.game_script_factor(None, True) == 1.0


def test_receiving_yards_projection(weeks_wr):
    proj = nfl_model.project_receiving_yards(weeks_wr)
    # ~10 targets, 70% catch, ~12.6 ypc -> mid-80s
    assert 75 < proj.mean < 100
    assert proj.inputs["catch_rate"] == pytest.approx(0.69, abs=0.03)
    assert 0.3 < proj.prob_over(79.5) < 0.7


def test_wind_kills_passing(weeks_wr):
    calm = nfl_model.project_receiving_yards(weeks_wr, windy=False)
    windy = nfl_model.project_receiving_yards(weeks_wr, windy=True)
    assert windy.mean == pytest.approx(calm.mean * 0.93, abs=0.5)


def test_rushing_yards_projection(weeks_rb):
    proj = nfl_model.project_rushing_yards(weeks_rb)
    assert 85 < proj.mean < 110
    # favorite runs more
    fav = nfl_model.project_rushing_yards(weeks_rb, spread=-7.0)
    assert fav.mean > proj.mean


def test_receptions_negbin(weeks_wr):
    proj = nfl_model.project_receptions(weeks_wr)
    assert 5.5 < proj.mean < 8.5
    assert proj.prob_over(4.5) > 0.6


def test_anytime_td(weeks_wr):
    p = nfl_model.prob_anytime_td(weeks_wr)
    # scored in 3 of 5 -> healthy but regressed probability
    assert 0.35 < p < 0.60


def test_small_samples_refused():
    assert nfl_model.project_receiving_yards([]) is None
    assert nfl_model.prob_anytime_td([{"week": 1, "receiving_tds": 1, "rushing_tds": 0}]) is None
