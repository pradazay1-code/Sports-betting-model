"""NBA stats ingest — balldontlie API (spec §2.2).

Player game logs (minutes, pts/reb/ast/3PM, volume stats) feed the minutes
model — which is 70% of NBA props. Raw responses cached like every source.
Set BALLDONTLIE_API_KEY in .env (free tier available).
"""

from __future__ import annotations

import json
import os

import requests

from src import config, db

BASE = "https://api.balldontlie.io/v1"


def parse_minutes(raw: str | int | None) -> float | None:
    """balldontlie 'min' comes as '34', '34:12', or None."""
    if raw in (None, ""):
        return None
    s = str(raw)
    if ":" in s:
        m, _, sec = s.partition(":")
        return int(m) + int(sec) / 60.0
    return float(s)


def parse_stat_rows(payload: dict) -> list[dict]:
    rows = []
    for s in payload.get("data", []):
        player = s.get("player") or {}
        game = s.get("game") or {}
        rows.append({
            "player_id": player.get("id"),
            "player_name": f"{player.get('first_name', '')} {player.get('last_name', '')}".strip(),
            "team": (s.get("team") or {}).get("abbreviation"),
            "game_date": (game.get("date") or "")[:10],
            "opponent": None,   # resolvable via team ids; not needed by the model
            "minutes": parse_minutes(s.get("min")),
            "pts": s.get("pts"), "reb": s.get("reb"), "ast": s.get("ast"),
            "fg3m": s.get("fg3m"), "fga": s.get("fga"), "fta": s.get("fta"),
            "tov": s.get("turnover"),
        })
    return [r for r in rows if r["player_id"] and r["game_date"]]


def store_player_logs(conn, rows: list[dict]) -> int:
    now = db.utcnow()
    before = conn.total_changes
    conn.executemany(
        """INSERT INTO nba_player_logs
           (player_id, player_name, team, game_date, opponent, minutes,
            pts, reb, ast, fg3m, fga, fta, tov, fetched_at)
           VALUES (:player_id, :player_name, :team, :game_date, :opponent, :minutes,
                   :pts, :reb, :ast, :fg3m, :fga, :fta, :tov, :fetched_at)
           ON CONFLICT (player_id, game_date) DO UPDATE SET
             minutes=excluded.minutes, pts=excluded.pts, reb=excluded.reb,
             ast=excluded.ast, fg3m=excluded.fg3m, fetched_at=excluded.fetched_at""",
        [{**r, "fetched_at": now} for r in rows])
    conn.commit()
    return conn.total_changes - before


def pull_player_logs(conn, player_ids: list[int], season: int) -> int:
    key = os.environ.get("BALLDONTLIE_API_KEY")
    headers = {"Authorization": key} if key else {}
    http = config.sources()["http"]
    pulled_at = db.utcnow()
    total, cursor = 0, None
    while True:
        params = {"seasons[]": season, "player_ids[]": player_ids, "per_page": 100}
        if cursor:
            params["cursor"] = cursor
        try:
            resp = requests.get(f"{BASE}/stats", params=params, headers=headers,
                                timeout=http["timeout_seconds"])
            if resp.status_code != 200:
                break
        except requests.RequestException:
            break
        payload = resp.json()
        day_dir = config.raw_dir() / "nba" / pulled_at[:10]
        day_dir.mkdir(parents=True, exist_ok=True)
        (day_dir / f"stats_{cursor or 0}.json").write_text(json.dumps(payload))
        total += store_player_logs(conn, parse_stat_rows(payload))
        cursor = (payload.get("meta") or {}).get("next_cursor")
        if not cursor:
            break
    return total


def player_recent_games(conn, player_id: int, limit: int = 20) -> list[dict]:
    """Most recent first."""
    return [dict(r) for r in conn.execute(
        """SELECT * FROM nba_player_logs WHERE player_id = ? AND minutes IS NOT NULL
           ORDER BY game_date DESC LIMIT ?""", (player_id, limit)).fetchall()]


def defense_factor(conn, team: str, season: int, stat: str) -> float:
    """Opponent-allowed multiplier vs league average; 1.0 when unknown."""
    row = conn.execute(
        """SELECT allowed_per_game, league_avg FROM nba_team_defense
           WHERE team = ? AND season = ? AND stat = ?""",
        (team, season, stat)).fetchone()
    if not row or not row["league_avg"]:
        return 1.0
    return row["allowed_per_game"] / row["league_avg"]
