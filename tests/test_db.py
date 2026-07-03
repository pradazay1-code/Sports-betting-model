"""Ledger schema: creation, idempotency, bankroll seed, snapshot dedup."""

import sqlite3

import pytest

from src import db


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.sqlite")
    yield c
    c.close()


def _snapshot_row(**over):
    row = {
        "pulled_at": "2026-07-03T14:00:00Z", "sport": "baseball_mlb",
        "event_id": "ev1", "book": "draftkings", "market": "totals",
        "player": None, "outcome": "Over", "side": "over", "line": 8.5,
        "odds_american": -110, "odds_decimal": 1.909091,
        "implied_prob": 0.52381, "raw_file": None,
    }
    row.update(over)
    return row


def test_schema_tables_exist(conn):
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"events", "line_snapshots", "picks", "clv_log",
            "bankroll_history", "api_usage"} <= tables


def test_connect_is_idempotent(tmp_path):
    path = tmp_path / "test.sqlite"
    db.connect(path).close()
    db.connect(path).close()  # re-running schema must not fail


def test_bankroll_seeded_once(tmp_path):
    path = tmp_path / "test.sqlite"
    c1 = db.connect(path)
    c1.close()
    c2 = db.connect(path)
    rows = c2.execute("SELECT bankroll, reason FROM bankroll_history").fetchall()
    c2.close()
    assert len(rows) == 1
    assert rows[0]["reason"] == "seed"
    assert rows[0]["bankroll"] > 0


def test_duplicate_snapshot_ignored(conn):
    assert db.insert_snapshots(conn, [_snapshot_row()]) == 1
    assert db.insert_snapshots(conn, [_snapshot_row()]) == 0  # same pull, same row
    # a later pull of the same market is a NEW time-series point
    assert db.insert_snapshots(
        conn, [_snapshot_row(pulled_at="2026-07-03T15:00:00Z")]) == 1


def test_upsert_event_updates_last_seen(conn):
    ev = {"event_id": "ev1", "sport": "baseball_mlb",
          "commence_time": "2026-07-03T23:05:00Z",
          "home_team": "H", "away_team": "A"}
    db.upsert_event(conn, ev, "2026-07-03T14:00:00Z")
    db.upsert_event(conn, ev, "2026-07-03T15:00:00Z")
    row = conn.execute("SELECT first_seen_at, last_seen_at FROM events").fetchone()
    assert row["first_seen_at"] == "2026-07-03T14:00:00Z"
    assert row["last_seen_at"] == "2026-07-03T15:00:00Z"
