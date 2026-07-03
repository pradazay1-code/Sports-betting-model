"""End-to-end: Odds API payload -> normalized snapshots -> movement + shopping."""

import json
from pathlib import Path

import pytest

from src import db
from src.ingest import odds

FIXTURE = Path(__file__).parent / "fixtures" / "odds_api_sample.json"


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text())


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.sqlite")
    yield c
    c.close()


def test_normalize_event_counts(payload):
    event_row, rows = odds.normalize_event(payload[0], "2026-07-03T14:00:00Z")
    assert event_row["event_id"] == payload[0]["id"]
    assert event_row["home_team"] == "New York Yankees"
    # DK: 2 h2h + 2 totals; FD: 2 h2h + 2 props; Pinnacle: 2 h2h
    assert len(rows) == 10


def test_prop_rows_carry_player(payload):
    _, rows = odds.normalize_event(payload[0], "2026-07-03T14:00:00Z")
    props = [r for r in rows if r["market"] == "pitcher_strikeouts"]
    assert len(props) == 2
    assert all(r["player"] == "Gerrit Cole" for r in props)
    assert {r["side"] for r in props} == {"over", "under"}
    assert all(r["line"] == 6.5 for r in props)


def test_three_way_market_sides(payload):
    _, rows = odds.normalize_event(payload[1], "2026-07-03T14:00:00Z")
    assert {r["side"] for r in rows} == {"home", "away", "draw"}


def test_ingest_payload_lands_in_db(conn, payload):
    n = odds.ingest_payload(conn, payload, pulled_at="2026-07-03T14:00:00Z")
    assert n == 13  # 10 (MLB event) + 3 (WC event)
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 2
    row = conn.execute(
        "SELECT * FROM line_snapshots WHERE market='pitcher_strikeouts' AND side='over'"
    ).fetchone()
    assert row["odds_american"] == -115
    assert row["implied_prob"] == pytest.approx(0.5349, abs=1e-3)


def test_line_movement_detected(conn, payload):
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    t0 = (now - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t1 = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    odds.ingest_payload(conn, payload, pulled_at=t0)
    # simulate the line steaming up half an hour later
    moved = json.loads(FIXTURE.read_text())
    moved[0]["bookmakers"][1]["markets"][1]["outcomes"][0].update(point=7.5, price=-120)
    moved[0]["bookmakers"][1]["markets"][1]["outcomes"][1].update(point=7.5, price=100)
    odds.ingest_payload(conn, moved, pulled_at=t1)

    moves = odds.line_movement(conn, hours=1)
    k_move = [m for m in moves if m["market"] == "pitcher_strikeouts" and m["side"] == "over"]
    assert len(k_move) == 1
    assert k_move[0]["open_line"] == 6.5
    assert k_move[0]["last_line"] == 7.5
    assert k_move[0]["player"] == "Gerrit Cole"
    # unmoved markets (e.g. draftkings h2h) are not reported
    assert not any(m["book"] == "draftkings" and m["market"] == "h2h" for m in moves)


def test_best_prices_line_shopping(conn, payload):
    odds.ingest_payload(conn, payload, pulled_at="2026-07-03T14:00:00Z")
    prices = odds.best_prices(conn, payload[0]["id"], "h2h", side="away")
    assert [p["book"] for p in prices] == ["pinnacle", "draftkings", "fanduel"]
    assert prices[0]["odds_american"] == 138  # best price first


def test_ingest_skips_malformed_entries(conn):
    assert odds.ingest_payload(conn, [{"not": "an event"}, "junk"]) == 0
