"""MLB ingest parsers + K-prop model probability outputs (spec §10)."""

import json
from pathlib import Path

import pytest

from src import db
from src.ingest import mlb
from src.models import mlb_model

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.sqlite")
    yield c
    c.close()


def _load(name):
    return json.loads((FIX / name).read_text())


# ------------------------------------------------------------------ parsers

def test_ip_to_outs():
    assert mlb.ip_to_outs("6.2") == 20
    assert mlb.ip_to_outs("7.0") == 21
    assert mlb.ip_to_outs(None) is None


def test_parse_schedule():
    games = mlb.parse_schedule(_load("mlb_schedule.json"))
    assert len(games) == 1
    g = games[0]
    assert g["game_pk"] == 776543
    assert g["home_probable"] == "Gerrit Cole"
    assert g["away_team_id"] == 111
    assert g["venue"] == "Yankee Stadium"


def test_parse_gamelog_chronological():
    rows = mlb.parse_pitcher_gamelog(_load("mlb_gamelog_cole.json"), 543037)
    assert len(rows) == 6
    assert rows[0]["game_date"] == "2026-05-29"
    assert rows[-1]["game_date"] == "2026-06-27"
    assert rows[-1]["strikeouts"] == 8
    assert rows[-1]["innings_outs"] == 21
    assert rows[0]["hand"] == "R"


def test_parse_team_splits():
    rows = mlb.parse_team_splits(_load("mlb_team_splits_bos.json"), 111, 2026)
    by_hand = {r["vs_hand"]: r for r in rows}
    assert by_hand["R"]["k_rate"] == pytest.approx(592 / 2210, abs=1e-4)
    assert by_hand["L"]["k_rate"] == pytest.approx(240 / 980, abs=1e-4)


def test_store_and_query_roundtrip(conn):
    mlb.store_games(conn, mlb.parse_schedule(_load("mlb_schedule.json")))
    mlb.store_pitcher_logs(conn, mlb.parse_pitcher_gamelog(_load("mlb_gamelog_cole.json"), 543037))
    mlb.store_team_batting(conn, mlb.parse_team_splits(_load("mlb_team_splits_bos.json"), 111, 2026))

    games = mlb.todays_games(conn, "2026-07-03")
    assert len(games) == 1
    recent = mlb.pitcher_recent_games(conn, 543037)
    assert recent[0]["game_date"] == "2026-06-27"  # most recent first
    assert mlb.team_k_rate(conn, 111, "R", 2026) == pytest.approx(0.2679, abs=1e-3)


def test_store_pitcher_logs_upserts(conn):
    rows = mlb.parse_pitcher_gamelog(_load("mlb_gamelog_cole.json"), 543037)
    mlb.store_pitcher_logs(conn, rows)
    mlb.store_pitcher_logs(conn, rows)  # re-ingest must not duplicate
    n = conn.execute("SELECT COUNT(*) FROM mlb_pitcher_logs").fetchone()[0]
    assert n == 6


# -------------------------------------------------------------------- model

def _cole_recent(conn):
    mlb.store_pitcher_logs(conn, mlb.parse_pitcher_gamelog(_load("mlb_gamelog_cole.json"), 543037))
    return mlb.pitcher_recent_games(conn, 543037)


def test_k_projection_reasonable(conn):
    proj = mlb_model.project_strikeouts(_cole_recent(conn), opp_k_rate=0.268)
    assert proj is not None
    assert proj.sample_games == 6
    # 6 starts, ~28.7% raw K rate, hot opponent: lambda lands ~6.5-7.5
    assert 6.3 < proj.lam < 7.6
    assert proj.inputs["expected_batters_faced"] == pytest.approx(25.1, abs=0.5)
    p_over = proj.prob_over(6.5)
    assert 0.45 < p_over < 0.65
    assert proj.prob_under(6.5) == pytest.approx(1 - p_over)


def test_k_projection_opponent_matters(conn):
    recent = _cole_recent(conn)
    hot = mlb_model.project_strikeouts(recent, opp_k_rate=0.28)
    cold = mlb_model.project_strikeouts(recent, opp_k_rate=0.18)
    assert hot.lam > cold.lam


def test_k_projection_refuses_tiny_sample():
    tiny = [{"player_id": 1, "player_name": "X", "batters_faced": 25,
             "strikeouts": 9, "game_date": "2026-06-01", "hand": "R"}] * 2
    assert mlb_model.project_strikeouts(tiny, opp_k_rate=0.25) is None


def test_game_projection_skips_missing_data(conn):
    mlb.store_games(conn, mlb.parse_schedule(_load("mlb_schedule.json")))
    mlb.store_team_batting(conn, mlb.parse_team_splits(_load("mlb_team_splits_bos.json"), 111, 2026))
    _cole_recent(conn)
    game = mlb.todays_games(conn, "2026-07-03")[0]
    projections = mlb_model.project_game_strikeouts(conn, game, 2026)
    # Bello has no logs ingested -> only Cole projected
    assert [p.player_name for p in projections] == ["Gerrit Cole"]


# --------------------------------------------------------------------- NRFI

def test_clean_first_probability_regression():
    assert mlb_model.clean_first_probability([]) == pytest.approx(0.73)
    # 10 clean firsts out of 10 -> regressed below 1.0
    p = mlb_model.clean_first_probability([0] * 10)
    assert 0.85 < p < 0.93


def test_nrfi_park_adjustment():
    base = mlb_model.nrfi_probability(0.75, 0.75)
    coors = mlb_model.nrfi_probability(0.75, 0.75, venue="Coors Field")
    pitcher_park = mlb_model.nrfi_probability(0.75, 0.75, venue="T-Mobile Park")
    assert coors < base < pitcher_park
