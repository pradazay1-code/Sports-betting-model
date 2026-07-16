"""SQLite storage layer.

The whole point of using SQLite is that the DB file lives in the repo and a
GitHub Actions workflow can commit updates back. This keeps everything free
and self-hosted. If the DB ever outgrows the repo we swap the connection in
this file (Turso libsql is wire-compatible).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Iterator

from app.config import CFG, ensure_dirs


SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS games (
    game_id     TEXT PRIMARY KEY,
    sport       TEXT NOT NULL,
    game_date   TEXT NOT NULL,
    start_utc   TEXT,
    home_team   TEXT,
    away_team   TEXT,
    venue       TEXT,
    status      TEXT,
    home_score  INTEGER,
    away_score  INTEGER,
    extra       TEXT
);
CREATE INDEX IF NOT EXISTS idx_games_date ON games(sport, game_date);

CREATE TABLE IF NOT EXISTS players (
    player_id   TEXT PRIMARY KEY,
    sport       TEXT NOT NULL,
    full_name   TEXT NOT NULL,
    team        TEXT,
    position    TEXT
);
CREATE INDEX IF NOT EXISTS idx_players_name ON players(sport, full_name);

CREATE TABLE IF NOT EXISTS player_game_stats (
    sport       TEXT NOT NULL,
    game_id     TEXT NOT NULL,
    player_id   TEXT NOT NULL,
    game_date   TEXT NOT NULL,
    team        TEXT,
    opp_team    TEXT,
    home        INTEGER,
    minutes     REAL,
    stats_json  TEXT NOT NULL,
    PRIMARY KEY (game_id, player_id)
);
CREATE INDEX IF NOT EXISTS idx_pgs_player_date ON player_game_stats(player_id, game_date);
CREATE INDEX IF NOT EXISTS idx_pgs_sport_date ON player_game_stats(sport, game_date);

CREATE TABLE IF NOT EXISTS prop_offers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_at      TEXT NOT NULL,
    sport           TEXT NOT NULL,
    game_id         TEXT,
    player_id       TEXT,
    player_name     TEXT NOT NULL,
    team            TEXT,
    market          TEXT NOT NULL,
    line            REAL NOT NULL,
    over_price      INTEGER,
    under_price     INTEGER,
    book            TEXT NOT NULL,
    UNIQUE (fetched_at, sport, player_name, market, line, book)
);
CREATE INDEX IF NOT EXISTS idx_offers_market ON prop_offers(sport, market, player_name);
CREATE INDEX IF NOT EXISTS idx_offers_fetched ON prop_offers(fetched_at);

CREATE TABLE IF NOT EXISTS picks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at    TEXT NOT NULL,
    on_date         TEXT NOT NULL,
    sport           TEXT NOT NULL,
    player_name     TEXT NOT NULL,
    market          TEXT NOT NULL,
    side            TEXT NOT NULL,
    line            REAL NOT NULL,
    price_american  INTEGER NOT NULL,
    book            TEXT NOT NULL,
    model_prob      REAL NOT NULL,
    fair_prob       REAL NOT NULL,
    edge_pct        REAL NOT NULL,
    kelly_stake     REAL NOT NULL,
    rating          REAL NOT NULL,
    rationale       TEXT,
    graded          INTEGER DEFAULT 0,
    actual_value    REAL,
    won             INTEGER,
    payout_units    REAL
);
CREATE INDEX IF NOT EXISTS idx_picks_date ON picks(on_date, sport);

CREATE TABLE IF NOT EXISTS model_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    finished_at     TEXT NOT NULL,
    sport           TEXT NOT NULL,
    market          TEXT NOT NULL,
    rows            INTEGER,
    mae             REAL,
    brier           REAL,
    log_loss        REAL,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS lineups (
    sport       TEXT NOT NULL,
    game_id     TEXT NOT NULL,
    team        TEXT NOT NULL,
    player_id   TEXT,
    player_name TEXT NOT NULL,
    role        TEXT,
    starter     INTEGER DEFAULT 0,
    confirmed   INTEGER DEFAULT 0,
    PRIMARY KEY (game_id, player_name)
);

CREATE TABLE IF NOT EXISTS injuries (
    sport       TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    team        TEXT,
    player_name TEXT NOT NULL,
    status      TEXT NOT NULL,
    detail      TEXT,
    PRIMARY KEY (sport, player_name, fetched_at)
);

CREATE TABLE IF NOT EXISTS weather (
    game_id     TEXT PRIMARY KEY,
    fetched_at  TEXT NOT NULL,
    temp_f      REAL,
    wind_mph    REAL,
    wind_dir    TEXT,
    precip_pct  REAL,
    conditions  TEXT
);

CREATE TABLE IF NOT EXISTS metrics_daily (
    on_date     TEXT NOT NULL,
    sport       TEXT NOT NULL,
    n_picks     INTEGER,
    n_wins      INTEGER,
    n_losses    INTEGER,
    n_push      INTEGER,
    roi_units   REAL,
    brier       REAL,
    PRIMARY KEY (on_date, sport)
);

CREATE TABLE IF NOT EXISTS team_game_stats (
    sport       TEXT NOT NULL,
    game_id     TEXT NOT NULL,
    team        TEXT NOT NULL,
    opp_team    TEXT,
    game_date   TEXT NOT NULL,
    home        INTEGER,
    points_for  REAL,
    points_against REAL,
    stats_json  TEXT,
    PRIMARY KEY (game_id, team)
);
CREATE INDEX IF NOT EXISTS idx_tgs_team_date ON team_game_stats(team, game_date);
CREATE INDEX IF NOT EXISTS idx_tgs_sport_date ON team_game_stats(sport, game_date);

CREATE TABLE IF NOT EXISTS game_predictions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at    TEXT NOT NULL,
    on_date         TEXT NOT NULL,
    sport           TEXT NOT NULL,
    game_id         TEXT NOT NULL,
    home_team       TEXT,
    away_team       TEXT,
    pred_home_score REAL,
    pred_away_score REAL,
    pred_total      REAL,
    pred_spread     REAL,
    home_win_prob   REAL,
    rationale       TEXT
);
CREATE INDEX IF NOT EXISTS idx_gp_date ON game_predictions(on_date, sport);

CREATE TABLE IF NOT EXISTS alerts_sent (
    alert_key   TEXT PRIMARY KEY,
    sent_at     TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(str(CFG.db_path), isolation_level=None, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 60000")
    return conn


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with connection() as conn:
        conn.executescript(SCHEMA)


# -------- write helpers --------------------------------------------------


def upsert_games(rows: Iterable[dict]) -> int:
    sql = """
        INSERT INTO games (game_id, sport, game_date, start_utc, home_team, away_team, venue, status, home_score, away_score, extra)
        VALUES (:game_id, :sport, :game_date, :start_utc, :home_team, :away_team, :venue, :status, :home_score, :away_score, :extra)
        ON CONFLICT(game_id) DO UPDATE SET
            start_utc=excluded.start_utc,
            status=excluded.status,
            home_score=COALESCE(excluded.home_score, games.home_score),
            away_score=COALESCE(excluded.away_score, games.away_score),
            venue=COALESCE(excluded.venue, games.venue),
            extra=COALESCE(excluded.extra, games.extra)
    """
    n = 0
    with connection() as conn:
        for r in rows:
            conn.execute(sql, _with_defaults(r, ("start_utc","home_team","away_team","venue","status","home_score","away_score","extra")))
            n += 1
    return n


def upsert_players(rows: Iterable[dict]) -> int:
    sql = """
        INSERT INTO players (player_id, sport, full_name, team, position)
        VALUES (:player_id, :sport, :full_name, :team, :position)
        ON CONFLICT(player_id) DO UPDATE SET
            full_name=excluded.full_name,
            team=COALESCE(excluded.team, players.team),
            position=COALESCE(excluded.position, players.position)
    """
    n = 0
    with connection() as conn:
        for r in rows:
            conn.execute(sql, _with_defaults(r, ("team","position")))
            n += 1
    return n


def upsert_player_game_stats(rows: Iterable[dict]) -> int:
    sql = """
        INSERT INTO player_game_stats (sport, game_id, player_id, game_date, team, opp_team, home, minutes, stats_json)
        VALUES (:sport, :game_id, :player_id, :game_date, :team, :opp_team, :home, :minutes, :stats_json)
        ON CONFLICT(game_id, player_id) DO UPDATE SET
            team=excluded.team,
            opp_team=excluded.opp_team,
            home=excluded.home,
            minutes=excluded.minutes,
            stats_json=excluded.stats_json
    """
    n = 0
    with connection() as conn:
        for r in rows:
            conn.execute(sql, _with_defaults(r, ("team","opp_team","home","minutes")))
            n += 1
    return n


def upsert_team_game_stats(rows: Iterable[dict]) -> int:
    sql = """
        INSERT INTO team_game_stats (sport, game_id, team, opp_team, game_date, home, points_for, points_against, stats_json)
        VALUES (:sport, :game_id, :team, :opp_team, :game_date, :home, :points_for, :points_against, :stats_json)
        ON CONFLICT(game_id, team) DO UPDATE SET
            opp_team=excluded.opp_team,
            home=excluded.home,
            points_for=excluded.points_for,
            points_against=excluded.points_against,
            stats_json=excluded.stats_json
    """
    n = 0
    with connection() as conn:
        for r in rows:
            conn.execute(sql, _with_defaults(r, ("opp_team", "home", "points_for", "points_against", "stats_json")))
            n += 1
    return n


def insert_game_prediction(row: dict) -> int:
    sql = """
        INSERT INTO game_predictions
            (generated_at, on_date, sport, game_id, home_team, away_team,
             pred_home_score, pred_away_score, pred_total, pred_spread,
             home_win_prob, rationale)
        VALUES (:generated_at, :on_date, :sport, :game_id, :home_team, :away_team,
                :pred_home_score, :pred_away_score, :pred_total, :pred_spread,
                :home_win_prob, :rationale)
    """
    with connection() as conn:
        cur = conn.execute(sql, row)
        return int(cur.lastrowid)


def replace_game_predictions(on_date: str) -> None:
    with connection() as conn:
        conn.execute("DELETE FROM game_predictions WHERE on_date=?", (on_date,))


def fetch_game_predictions(on_date: str) -> list[dict]:
    with connection() as conn:
        cur = conn.execute(
            "SELECT * FROM game_predictions WHERE on_date=? ORDER BY sport, home_team",
            (on_date,),
        )
        return [dict(r) for r in cur.fetchall()]


def insert_prop_offers(rows: Iterable[dict]) -> int:
    sql = """
        INSERT OR IGNORE INTO prop_offers
            (fetched_at, sport, game_id, player_id, player_name, team, market, line, over_price, under_price, book)
        VALUES (:fetched_at, :sport, :game_id, :player_id, :player_name, :team, :market, :line, :over_price, :under_price, :book)
    """
    n = 0
    with connection() as conn:
        for r in rows:
            conn.execute(sql, _with_defaults(r, ("game_id","player_id","team","over_price","under_price")))
            n += 1
    return n


def insert_pick(row: dict) -> int:
    sql = """
        INSERT INTO picks
            (generated_at, on_date, sport, player_name, market, side, line, price_american, book,
             model_prob, fair_prob, edge_pct, kelly_stake, rating, rationale)
        VALUES (:generated_at, :on_date, :sport, :player_name, :market, :side, :line, :price_american, :book,
                :model_prob, :fair_prob, :edge_pct, :kelly_stake, :rating, :rationale)
    """
    with connection() as conn:
        cur = conn.execute(sql, row)
        return int(cur.lastrowid)


def replace_picks_for_date(on_date: str, sport: str | None = None) -> None:
    with connection() as conn:
        if sport:
            conn.execute("DELETE FROM picks WHERE on_date=? AND sport=? AND graded=0", (on_date, sport))
        else:
            conn.execute("DELETE FROM picks WHERE on_date=? AND graded=0", (on_date,))


def record_model_run(sport: str, market: str, rows: int, mae: float | None, brier: float | None,
                     log_loss: float | None, notes: str = "") -> None:
    with connection() as conn:
        conn.execute(
            """INSERT INTO model_runs (finished_at, sport, market, rows, mae, brier, log_loss, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (datetime.utcnow().isoformat(timespec="seconds"), sport, market, rows, mae, brier, log_loss, notes),
        )


def upsert_lineup(rows: Iterable[dict]) -> int:
    sql = """
        INSERT INTO lineups (sport, game_id, team, player_id, player_name, role, starter, confirmed)
        VALUES (:sport, :game_id, :team, :player_id, :player_name, :role, :starter, :confirmed)
        ON CONFLICT(game_id, player_name) DO UPDATE SET
            role=excluded.role, starter=excluded.starter, confirmed=excluded.confirmed
    """
    n = 0
    with connection() as conn:
        for r in rows:
            conn.execute(sql, _with_defaults(r, ("player_id","role","starter","confirmed")))
            n += 1
    return n


def upsert_injury(rows: Iterable[dict]) -> int:
    sql = """
        INSERT OR REPLACE INTO injuries (sport, fetched_at, team, player_name, status, detail)
        VALUES (:sport, :fetched_at, :team, :player_name, :status, :detail)
    """
    n = 0
    with connection() as conn:
        for r in rows:
            conn.execute(sql, _with_defaults(r, ("team","detail")))
            n += 1
    return n


def upsert_weather(row: dict) -> None:
    with connection() as conn:
        conn.execute(
            """INSERT INTO weather (game_id, fetched_at, temp_f, wind_mph, wind_dir, precip_pct, conditions)
               VALUES (:game_id, :fetched_at, :temp_f, :wind_mph, :wind_dir, :precip_pct, :conditions)
               ON CONFLICT(game_id) DO UPDATE SET
                   fetched_at=excluded.fetched_at, temp_f=excluded.temp_f, wind_mph=excluded.wind_mph,
                   wind_dir=excluded.wind_dir, precip_pct=excluded.precip_pct, conditions=excluded.conditions""",
            _with_defaults(row, ("temp_f","wind_mph","wind_dir","precip_pct","conditions")),
        )


# -------- read helpers ----------------------------------------------------


def fetch_player_history(sport: str, player_id: str | None, player_name: str | None,
                         before_date: str, limit: int = 30) -> list[dict]:
    """Returns the player's last <limit> games strictly before <before_date>."""
    sql = """
        SELECT p.*, g.home_team, g.away_team
        FROM player_game_stats p
        LEFT JOIN games g USING (game_id)
        WHERE p.sport = ? AND p.game_date < ?
          AND (p.player_id = ? OR (? IS NOT NULL AND p.player_id IN
               (SELECT player_id FROM players WHERE sport=? AND full_name=?)))
        ORDER BY p.game_date DESC
        LIMIT ?
    """
    with connection() as conn:
        cur = conn.execute(sql, (sport, before_date, player_id or "", player_name, sport, player_name or "", limit))
        return [dict(r) for r in cur.fetchall()]


def fetch_recent_offers(sport: str, since_iso: str) -> list[dict]:
    sql = """SELECT * FROM prop_offers WHERE sport=? AND fetched_at >= ? ORDER BY fetched_at DESC"""
    with connection() as conn:
        cur = conn.execute(sql, (sport, since_iso))
        return [dict(r) for r in cur.fetchall()]


def fetch_picks_on(on_date: str, sport: str | None = None) -> list[dict]:
    if sport:
        sql, args = "SELECT * FROM picks WHERE on_date=? AND sport=? ORDER BY rating DESC", (on_date, sport)
    else:
        sql, args = "SELECT * FROM picks WHERE on_date=? ORDER BY rating DESC", (on_date,)
    with connection() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def fetch_training_rows(sport: str, market: str, min_rows: int = 200) -> list[dict]:
    sql = """SELECT * FROM player_game_stats WHERE sport=? ORDER BY game_date"""
    with connection() as conn:
        rows = [dict(r) for r in conn.execute(sql, (sport,)).fetchall()]
    return rows


def fetch_games_on(sport: str, on_date: str) -> list[dict]:
    sql = "SELECT * FROM games WHERE sport=? AND game_date=? ORDER BY start_utc"
    with connection() as conn:
        return [dict(r) for r in conn.execute(sql, (sport, on_date)).fetchall()]


# -------- internal --------------------------------------------------------


def _with_defaults(row: dict, optional_keys: tuple[str, ...]) -> dict:
    out = dict(row)
    for k in optional_keys:
        out.setdefault(k, None)
    return out
