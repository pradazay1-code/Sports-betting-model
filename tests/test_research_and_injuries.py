"""Deep-research gate + injuries/lineup gate (spec §4, §2.3, §10)."""

import json

import pytest

from src import db
from src.ingest import injuries, news
from src.research import deep_dive


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.sqlite")
    yield c
    c.close()


def _pick(conn, **over):
    row = {"created_at": db.utcnow(), "sport": "baseball_mlb", "event_id": "ev1",
           "market": "pitcher_strikeouts", "player": "Gerrit Cole", "side": "over",
           "line": 6.5, "book": "fanduel", "odds_american": -115,
           "odds_decimal": 1.869565, "model_prob": 0.58, "market_fair_prob": 0.51,
           "ev_pct": 0.084, "tier": "B", "stake_units": 0.3, "needs_research": 1,
           "status": "pending"}
    row.update(over)
    cols = ", ".join(row)
    conn.execute(f"INSERT INTO picks ({cols}) VALUES ({', '.join(':' + c for c in row)})", row)
    conn.commit()
    return conn.execute("SELECT MAX(pick_id) FROM picks").fetchone()[0]


def test_generate_briefs_only_for_flagged(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(deep_dive.config, "REPO_ROOT", tmp_path)
    _pick(conn)
    _pick(conn, needs_research=0, player="Other Guy")
    day = db.utcnow()[:10]
    paths = deep_dive.generate_briefs(conn, day)
    assert len(paths) == 1
    brief = json.loads(open(paths[0]).read())
    assert "Gerrit Cole" in brief["pick"]
    assert len(brief["kill_switch_questions"]) == 5
    assert "market is usually right" in brief["key_assumption"]


def test_kill_switch_demotes_to_no_play(conn):
    pick_id = _pick(conn)
    status = deep_dive.attach_memo(conn, pick_id, "Pitch count capped at 75 (beat writer, 9am).",
                                   validated=False, kill_switch_hit=True)
    assert status == "no_play"
    p = conn.execute("SELECT * FROM picks WHERE pick_id = ?", (pick_id,)).fetchone()
    assert p["status"] == "no_play"
    assert p["stake_units"] == 0
    assert "[KILL-SWITCH]" in p["research_memo"]


def test_validation_restores_tier_sizing(conn):
    pick_id = _pick(conn, stake_units=0.3)   # research-capped C sizing
    status = deep_dive.attach_memo(conn, pick_id, "Confirmed starter, no restrictions.",
                                   validated=True)
    assert status == "validated"
    p = conn.execute("SELECT * FROM picks WHERE pick_id = ?", (pick_id,)).fetchone()
    assert p["stake_units"] > 0.3            # B-tier sizing restored
    assert p["research_memo"].startswith("Confirmed")


# ------------------------------------------------------------------ injuries

ESPN_PAYLOAD = {"injuries": [{
    "displayName": "Los Angeles Lakers",
    "injuries": [{"athlete": {"displayName": "Star Guard"},
                  "status": "Questionable", "details": {"type": "Ankle"}}]}]}


def test_parse_and_store_espn_injuries(conn):
    rows = injuries.parse_espn_injuries(ESPN_PAYLOAD, "basketball_nba")
    assert rows[0]["player"] == "Star Guard"
    assert rows[0]["status"] == "Questionable"
    injuries.store_injuries(conn, rows)
    assert injuries.player_injury_status(conn, "basketball_nba", "Star Guard") == "Questionable"


def test_lineup_gate_holds_then_upgrades(conn):
    _pick(conn, sport="basketball_nba", player="Star Guard",
          market="player_points", needs_research=0)
    _pick(conn, sport="baseball_mlb", player="Gerrit Cole", needs_research=0)

    held = injuries.hold_ungated_picks(conn)
    assert held == 1        # only the NBA pick is gated; MLB stays pending
    statuses = {r["player"]: r["status"] for r in
                conn.execute("SELECT player, status FROM picks").fetchall()}
    assert statuses["Star Guard"] == "hold_lineup"
    assert statuses["Gerrit Cole"] == "pending"

    upgraded = injuries.apply_lineup_gate(conn, "basketball_nba", ["Star Guard"])
    assert upgraded == 1
    assert conn.execute("SELECT status FROM picks WHERE player='Star Guard'"
                        ).fetchone()["status"] == "pending"


def test_news_queries():
    qs = news.build_queries("Gerrit Cole", "Yankees", "pitcher_strikeouts")
    assert any("beat writer" in q for q in qs)
    qs_yds = news.build_queries("Ace", "KC", "player_reception_yds")
    assert any("weather" in q for q in qs_yds)
