"""Aggregate player_game_stats + games into team_game_stats.

Idempotent — re-running just upserts. Called from the nightly job after
player box scores are ingested.
"""

from __future__ import annotations

import json

from app.store import connection, upsert_team_game_stats
from app.utils import get_logger

LOG = get_logger("team_stats")


def rebuild() -> int:
    """Rebuild team_game_stats from the latest games + player_game_stats."""
    with connection() as conn:
        games = [dict(r) for r in conn.execute(
            """SELECT game_id, sport, game_date, home_team, away_team,
                      home_score, away_score
               FROM games
               WHERE home_team IS NOT NULL AND away_team IS NOT NULL"""
        ).fetchall()]
        player_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM player_game_stats"
        ).fetchall()]

    by_game: dict[tuple[str, str], dict] = {}
    for r in player_rows:
        gid = r["game_id"]
        team = r["team"]
        if not team:
            continue
        key = (gid, team)
        agg = by_game.setdefault(key, {
            "sport": r["sport"],
            "game_id": gid,
            "team": team,
            "opp_team": r["opp_team"],
            "game_date": r["game_date"],
            "home": r.get("home"),
            "stats": {},
        })
        try:
            stats = json.loads(r["stats_json"]) if r["stats_json"] else {}
        except Exception:
            stats = {}
        for k, v in stats.items():
            if v is None:
                continue
            try:
                agg["stats"][k] = agg["stats"].get(k, 0.0) + float(v)
            except (TypeError, ValueError):
                continue

    out: list[dict] = []
    games_by_id = {g["game_id"]: g for g in games}
    for (gid, team), row in by_game.items():
        g = games_by_id.get(gid) or {}
        # Determine points_for vs points_against using box score totals
        # when the game has finished. Otherwise leave None.
        home_score = g.get("home_score")
        away_score = g.get("away_score")
        is_home = g.get("home_team") == team
        pf = None
        pa = None
        if home_score is not None and away_score is not None:
            pf = home_score if is_home else away_score
            pa = away_score if is_home else home_score
        out.append({
            "sport": row["sport"],
            "game_id": gid,
            "team": team,
            "opp_team": row["opp_team"] or (g.get("away_team") if is_home else g.get("home_team")),
            "game_date": row["game_date"],
            "home": 1 if is_home else (0 if g else row.get("home")),
            "points_for": pf,
            "points_against": pa,
            "stats_json": json.dumps(row["stats"]),
        })
    n = upsert_team_game_stats(out) if out else 0
    LOG.info("team_stats: rebuilt %d rows", n)
    return n
