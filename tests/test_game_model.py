import json

import pytest

from app.models.game_model import predict_for_games
from app.sources.parks import factor_for


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    import importlib
    import app.config as cfg; importlib.reload(cfg)
    import app.store as store; importlib.reload(store)
    store.init_db()
    yield store


def _seed_team(store, sport, team, opp, dates_scores):
    rows = []
    for i, (d, pf, pa, is_home) in enumerate(dates_scores):
        rows.append({
            "sport": sport, "game_id": f"{sport}-{team}-{i}", "team": team,
            "opp_team": opp, "game_date": d, "home": int(is_home),
            "points_for": pf, "points_against": pa,
            "stats_json": json.dumps({}),
        })
    store.upsert_team_game_stats(rows)


def test_predict_runs_when_both_teams_have_history(isolated_db):
    store = isolated_db
    # Five games each for two teams (over the rolling window minimum 3).
    home_games = [
        ("2026-04-01", 110, 100, True),
        ("2026-04-02", 105, 98, False),
        ("2026-04-03", 112, 95, True),
        ("2026-04-04", 100, 105, False),
        ("2026-04-05", 115, 102, True),
    ]
    away_games = [
        ("2026-04-01", 99, 105, False),
        ("2026-04-02", 108, 102, True),
        ("2026-04-03", 100, 110, False),
        ("2026-04-04", 102, 100, True),
        ("2026-04-05", 99, 108, False),
    ]
    _seed_team(store, "NBA", "Lakers", "Celtics", home_games)
    _seed_team(store, "NBA", "Celtics", "Lakers", away_games)

    games = [{"game_id": "NBA-X1", "home_team": "Lakers", "away_team": "Celtics"}]
    preds = predict_for_games("NBA", games)
    assert len(preds) == 1
    p = preds[0]
    assert 50 < p.pred_home_score < 200
    assert 50 < p.pred_away_score < 200
    assert 0.0 < p.home_win_prob < 1.0


def test_predict_skipped_when_no_history():
    games = [{"game_id": "NBA-X1", "home_team": "X", "away_team": "Y"}]
    preds = predict_for_games("NBA", games)
    assert preds == []


def test_park_factor_default_neutral():
    assert factor_for(None) == 1.0
    assert factor_for("Unknown Park") == 1.0
    assert factor_for("Coors Field") > 1.0
