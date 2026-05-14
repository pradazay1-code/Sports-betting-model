import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    # Recreate the frozen Config so it picks up the env override.
    import importlib

    import app.config as cfg
    importlib.reload(cfg)
    import app.store as store
    importlib.reload(store)
    store.init_db()
    yield store


def test_upsert_and_read_game(isolated_db):
    store = isolated_db
    store.upsert_games([{
        "game_id": "NBA-1", "sport": "NBA", "game_date": "2026-01-01",
        "home_team": "Lakers", "away_team": "Celtics", "status": "Scheduled",
    }])
    rows = store.fetch_games_on("NBA", "2026-01-01")
    assert len(rows) == 1
    assert rows[0]["home_team"] == "Lakers"


def test_insert_pick_and_grade_flow(isolated_db):
    store = isolated_db
    pid = store.insert_pick({
        "generated_at": "2026-05-14T12:00:00",
        "on_date": "2026-05-14",
        "sport": "NBA", "player_name": "Test Guy", "market": "player_points",
        "side": "over", "line": 24.5, "price_american": -110, "book": "dk",
        "model_prob": 0.58, "fair_prob": 0.52, "edge_pct": 5.0,
        "kelly_stake": 0.02, "rating": 72.0, "rationale": "{}",
    })
    assert pid > 0
    assert len(store.fetch_picks_on("2026-05-14")) == 1


def test_offers_unique(isolated_db):
    store = isolated_db
    row = dict(
        fetched_at="2026-05-14T12:00:00", sport="NBA", game_id=None, player_id=None,
        player_name="Test Guy", team=None, market="player_points",
        line=24.5, over_price=-110, under_price=-110, book="dk",
    )
    store.insert_prop_offers([row])
    # Same key -> ignored.
    store.insert_prop_offers([row])
    out = store.fetch_recent_offers("NBA", "2026-05-14T00:00:00")
    assert len(out) == 1
