"""SQLite ledger: picks ledger, CLV log, bankroll history, line snapshots.

Every recommendation and every odds pull lands here. The line_snapshots
time series powers line-movement analysis and CLV grading (spec §0.2, §2.1).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id      TEXT PRIMARY KEY,          -- book/API event id
    sport         TEXT NOT NULL,             -- odds api sport key (baseball_mlb...)
    commence_time TEXT,                      -- ISO-8601 UTC
    home_team     TEXT,
    away_team     TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL
);

-- Every line ever pulled, timestamped. Never updated, only appended.
CREATE TABLE IF NOT EXISTS line_snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    pulled_at     TEXT NOT NULL,             -- ISO-8601 UTC of the API pull
    sport         TEXT NOT NULL,
    event_id      TEXT NOT NULL,
    book          TEXT NOT NULL,             -- bookmaker key (draftkings, pinnacle...)
    market        TEXT NOT NULL,             -- h2h, totals, pitcher_strikeouts...
    player        TEXT,                      -- NULL for game markets
    outcome       TEXT NOT NULL,             -- raw outcome name (team name, Over, Under)
    side          TEXT NOT NULL,             -- canonical: over/under/home/away/draw/other
    line          REAL,                      -- the point/handicap; NULL for moneylines
    odds_american INTEGER NOT NULL,
    odds_decimal  REAL NOT NULL,
    implied_prob  REAL NOT NULL,             -- 1/decimal, WITH vig (de-vig is Phase 2)
    raw_file      TEXT                       -- cached JSON this row was parsed from
);
-- NULL-safe dedup (SQLite treats NULLs as distinct in plain UNIQUE constraints)
CREATE UNIQUE INDEX IF NOT EXISTS uq_snap ON line_snapshots
    (pulled_at, event_id, book, market, ifnull(player, ''), outcome, ifnull(line, -1e9));
CREATE INDEX IF NOT EXISTS idx_snap_lookup
    ON line_snapshots (event_id, market, player, side, book, pulled_at);
CREATE INDEX IF NOT EXISTS idx_snap_time ON line_snapshots (pulled_at);

-- Picks ledger (spec §0.1: every pick carries model prob, implied prob, EV gap).
CREATE TABLE IF NOT EXISTS picks (
    pick_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at       TEXT NOT NULL,
    sport            TEXT NOT NULL,
    event_id         TEXT NOT NULL,
    market           TEXT NOT NULL,
    player           TEXT,
    side             TEXT NOT NULL,
    line             REAL,
    book             TEXT NOT NULL,          -- book whose price we recommend
    odds_american    INTEGER NOT NULL,
    odds_decimal     REAL NOT NULL,
    model_prob       REAL NOT NULL,
    market_fair_prob REAL NOT NULL,          -- de-vigged implied prob
    ev_pct           REAL NOT NULL,          -- model_prob * decimal - 1
    tier             TEXT NOT NULL,          -- A / B / C
    stake_units      REAL NOT NULL,
    is_paper         INTEGER NOT NULL DEFAULT 1,  -- paper until 200-pick +CLV gate (spec §9)
    status           TEXT NOT NULL DEFAULT 'pending',
                     -- pending / hold_lineup / won / lost / push / void / no_play
    result_value     REAL,                   -- actual stat value once graded
    settled_at       TEXT,
    research_memo    TEXT,                   -- deep-dive memo (Phase 5)
    notes            TEXT
);

-- Closing Line Value log — the true scoreboard (spec §0.2).
CREATE TABLE IF NOT EXISTS clv_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    pick_id             INTEGER NOT NULL REFERENCES picks (pick_id),
    open_odds_american  INTEGER NOT NULL,
    open_line           REAL,
    close_odds_american INTEGER,
    close_line          REAL,
    close_book          TEXT,
    clv_pct             REAL,               -- open decimal vs close decimal edge
    captured_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bankroll_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    bankroll    REAL NOT NULL,
    change      REAL NOT NULL DEFAULT 0,
    reason      TEXT NOT NULL                -- seed / settle / adjustment
);

-- The Odds API usage headers, logged per request (500/mo free-tier budget).
CREATE TABLE IF NOT EXISTS api_usage (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    pulled_at          TEXT NOT NULL,
    endpoint           TEXT NOT NULL,
    requests_used      INTEGER,
    requests_remaining INTEGER
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open (and initialize) the ledger DB."""
    db_file = path or config.db_path()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    _seed_bankroll(conn)
    return conn


def _seed_bankroll(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT COUNT(*) FROM bankroll_history").fetchone()
    if row[0] == 0:
        starting = config.settings()["bankroll"]["starting"]
        conn.execute(
            "INSERT INTO bankroll_history (recorded_at, bankroll, change, reason) VALUES (?, ?, 0, 'seed')",
            (utcnow(), starting),
        )
        conn.commit()


def upsert_event(conn: sqlite3.Connection, event: dict, seen_at: str) -> None:
    conn.execute(
        """
        INSERT INTO events (event_id, sport, commence_time, home_team, away_team, first_seen_at, last_seen_at)
        VALUES (:event_id, :sport, :commence_time, :home_team, :away_team, :seen, :seen)
        ON CONFLICT (event_id) DO UPDATE SET
            commence_time = excluded.commence_time,
            last_seen_at  = excluded.last_seen_at
        """,
        {**event, "seen": seen_at},
    )


def insert_snapshots(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """Append snapshot rows; duplicate rows within a pull are ignored.

    Returns the number of rows actually inserted (rowcount lies for
    INSERT OR IGNORE under executemany, so we diff total_changes).
    """
    before = conn.total_changes
    conn.executemany(
        """
        INSERT OR IGNORE INTO line_snapshots
            (pulled_at, sport, event_id, book, market, player, outcome, side,
             line, odds_american, odds_decimal, implied_prob, raw_file)
        VALUES (:pulled_at, :sport, :event_id, :book, :market, :player, :outcome, :side,
                :line, :odds_american, :odds_decimal, :implied_prob, :raw_file)
        """,
        rows,
    )
    conn.commit()
    return conn.total_changes - before


def log_api_usage(conn: sqlite3.Connection, endpoint: str, used: int | None, remaining: int | None) -> None:
    conn.execute(
        "INSERT INTO api_usage (pulled_at, endpoint, requests_used, requests_remaining) VALUES (?, ?, ?, ?)",
        (utcnow(), endpoint, used, remaining),
    )
    conn.commit()
