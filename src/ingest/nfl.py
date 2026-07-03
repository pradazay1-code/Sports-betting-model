"""NFL stats ingest — nflverse weekly player stats (spec §2.2).

Downloads the nflverse player_stats CSV release (the same data nfl_data_py
wraps) and stores the columns the volume/efficiency models need. Parsed with
stdlib csv so Phase 4 adds no dependencies.
"""

from __future__ import annotations

import csv
import io

import requests

from src import config, db

PLAYER_STATS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "player_stats/player_stats_{season}.csv"
)

_COLS = {
    "player_id": str, "player_display_name": str, "position": str,
    "recent_team": str, "season": int, "week": int,
    "targets": int, "receptions": int, "receiving_yards": float, "receiving_tds": int,
    "carries": int, "rushing_yards": float, "rushing_tds": int,
    "attempts": int, "passing_yards": float, "passing_tds": int,
}


def parse_weekly_csv(text: str) -> list[dict]:
    rows = []
    for rec in csv.DictReader(io.StringIO(text)):
        row = {}
        for col, cast in _COLS.items():
            val = rec.get(col)
            try:
                row[col] = cast(float(val)) if cast is int and val not in (None, "", "NA") \
                    else (cast(val) if val not in (None, "", "NA") else None)
            except (TypeError, ValueError):
                row[col] = None
        if row.get("player_id") and row.get("week"):
            row["player_name"] = row.pop("player_display_name")
            row["team"] = row.pop("recent_team")
            rows.append(row)
    return rows


def store_weekly(conn, rows: list[dict]) -> int:
    now = db.utcnow()
    before = conn.total_changes
    conn.executemany(
        """INSERT INTO nfl_player_weekly
           (player_id, player_name, position, team, season, week,
            targets, receptions, receiving_yards, receiving_tds,
            carries, rushing_yards, rushing_tds,
            attempts, passing_yards, passing_tds, fetched_at)
           VALUES (:player_id, :player_name, :position, :team, :season, :week,
                   :targets, :receptions, :receiving_yards, :receiving_tds,
                   :carries, :rushing_yards, :rushing_tds,
                   :attempts, :passing_yards, :passing_tds, :fetched_at)
           ON CONFLICT (player_id, season, week) DO UPDATE SET
             targets=excluded.targets, receptions=excluded.receptions,
             receiving_yards=excluded.receiving_yards, carries=excluded.carries,
             rushing_yards=excluded.rushing_yards, passing_yards=excluded.passing_yards,
             fetched_at=excluded.fetched_at""",
        [{**r, "fetched_at": now} for r in rows])
    conn.commit()
    return conn.total_changes - before


def pull_season(conn, season: int) -> int:
    http = config.sources()["http"]
    try:
        resp = requests.get(PLAYER_STATS_URL.format(season=season),
                            timeout=http["timeout_seconds"] * 3)
        if resp.status_code != 200:
            return 0
    except requests.RequestException:
        return 0
    day_dir = config.raw_dir() / "nfl"
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / f"player_stats_{season}.csv").write_text(resp.text)
    return store_weekly(conn, parse_weekly_csv(resp.text))


def player_recent_weeks(conn, player_id: str, limit: int = 17) -> list[dict]:
    """Most recent first."""
    return [dict(r) for r in conn.execute(
        """SELECT * FROM nfl_player_weekly WHERE player_id = ?
           ORDER BY season DESC, week DESC LIMIT ?""", (player_id, limit)).fetchall()]


def find_player(conn, name: str) -> str | None:
    row = conn.execute(
        "SELECT player_id FROM nfl_player_weekly WHERE player_name = ? LIMIT 1",
        (name,)).fetchone()
    return row["player_id"] if row else None
