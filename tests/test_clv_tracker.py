"""CLV capture, boxscore parsing, grading, bankroll settlement (spec §10)."""

import json
from pathlib import Path

import pytest

from src import db
from src.engine import clv_tracker as clv
from src.ingest import odds

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.sqlite")
    yield c
    c.close()


def _insert_pick(conn, **over):
    row = {"created_at": "2026-07-03T15:00:00Z", "sport": "baseball_mlb",
           "event_id": "e912f18a2c3b4d5e6f708192a3b4c5d6",
           "market": "pitcher_strikeouts", "player": "Gerrit Cole",
           "side": "over", "line": 6.5, "book": "fanduel",
           "odds_american": -115, "odds_decimal": 1.869565,
           "model_prob": 0.57, "market_fair_prob": 0.511, "ev_pct": 0.066,
           "tier": "B", "stake_units": 1.0, "status": "pending"}
    row.update(over)
    cols = ", ".join(row)
    conn.execute(f"INSERT INTO picks ({cols}) VALUES ({', '.join(':' + c for c in row)})", row)
    conn.commit()
    return conn.execute("SELECT MAX(pick_id) FROM picks").fetchone()[0]


def test_clv_pct():
    # took -115 (1.8696), closed -130 (1.7692): you beat the close
    assert clv.clv_pct(1.8696, 1.7692) == pytest.approx(0.0567, abs=1e-3)
    # closed better than you took -> negative
    assert clv.clv_pct(1.8696, 1.9524) < 0


def test_capture_closes_uses_last_pre_commence_snapshot(conn):
    payload = json.loads((FIX / "odds_api_sample.json").read_text())
    odds.ingest_payload(conn, payload, pulled_at="2026-07-03T14:00:00Z")
    # line juice steams to -130 just before first pitch
    moved = json.loads((FIX / "odds_api_sample.json").read_text())
    moved[0]["bookmakers"][1]["markets"][1]["outcomes"][0]["price"] = -130
    odds.ingest_payload(conn, moved, pulled_at="2026-07-03T15:59:00Z")
    # game already underway relative to the capture run
    conn.execute("UPDATE events SET commence_time = '2026-07-03T16:00:00Z'")
    conn.commit()
    _insert_pick(conn)

    assert clv.capture_closes(conn) == 1
    log = conn.execute("SELECT * FROM clv_log").fetchone()
    assert log["close_odds_american"] == -130
    assert log["clv_pct"] == pytest.approx(0.0567, abs=1e-3)


def test_parse_boxscore_pitching():
    box = clv.parse_boxscore_pitching(json.loads((FIX / "mlb_boxscore.json").read_text()))
    assert box["Gerrit Cole"]["strikeouts"] == 8
    assert box["Brayan Bello"]["strikeouts"] == 4
    assert "Some Batter" not in box  # batters filtered out


def test_grade_over_win_updates_bankroll(conn):
    pick_id = _insert_pick(conn)
    box = clv.parse_boxscore_pitching(json.loads((FIX / "mlb_boxscore.json").read_text()))
    assert clv.grade_mlb_strikeouts(conn, box) == 1
    p = conn.execute("SELECT * FROM picks WHERE pick_id = ?", (pick_id,)).fetchone()
    assert p["status"] == "won"          # 8 Ks > 6.5
    assert p["result_value"] == 8.0
    bankroll = conn.execute(
        "SELECT bankroll FROM bankroll_history ORDER BY id DESC LIMIT 1").fetchone()[0]
    # 1 unit at 1.8696: profit = 0.8696u = 0.87% of 1000
    assert bankroll == pytest.approx(1008.70, abs=0.05)


def test_grade_under_loss(conn):
    pick_id = _insert_pick(conn, side="under", line=5.5)
    clv.grade_mlb_strikeouts(conn, {"Gerrit Cole": {"strikeouts": 8}})
    p = conn.execute("SELECT status FROM picks WHERE pick_id = ?", (pick_id,)).fetchone()
    assert p["status"] == "lost"
    bankroll = conn.execute(
        "SELECT bankroll FROM bankroll_history ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert bankroll == pytest.approx(990.0, abs=0.01)


def test_grade_push_on_whole_line(conn):
    pick_id = _insert_pick(conn, line=8.0)
    clv.settle_pick(conn, pick_id, 8.0)
    p = conn.execute("SELECT status FROM picks WHERE pick_id = ?", (pick_id,)).fetchone()
    assert p["status"] == "push"


def test_summary_groups_by_segment(conn):
    pick_id = _insert_pick(conn)
    conn.execute("INSERT INTO clv_log (pick_id, open_odds_american, clv_pct, captured_at) "
                 "VALUES (?, -115, 0.03, '2026-07-04')", (pick_id,))
    conn.commit()
    rows = clv.summary(conn)
    assert rows[0]["market"] == "pitcher_strikeouts"
    assert rows[0]["avg_clv"] == pytest.approx(0.03)
