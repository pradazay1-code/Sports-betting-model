"""MLB — statsapi.mlb.com (public, no key)."""

from __future__ import annotations

import json
from datetime import date

from app.utils import http_get_json, safe_get

BASE = "https://statsapi.mlb.com"


def fetch_schedule(on: date) -> list[dict]:
    data = http_get_json(
        f"{BASE}/api/v1/schedule",
        params={
            "sportId": 1,
            "date": on.isoformat(),
            "hydrate": "probablePitcher,linescore,team,venue,weather",
        },
    ) or {}
    out: list[dict] = []
    for d in data.get("dates", []) or []:
        for g in d.get("games", []) or []:
            teams = g.get("teams", {}) or {}
            home = (teams.get("home") or {}).get("team") or {}
            away = (teams.get("away") or {}).get("team") or {}
            out.append({
                "game_id": f"MLB-{g.get('gamePk')}",
                "sport": "MLB",
                "game_date": on.isoformat(),
                "start_utc": g.get("gameDate"),
                "home_team": home.get("name"),
                "away_team": away.get("name"),
                "venue": (g.get("venue") or {}).get("name"),
                "status": safe_get(g, "status", "abstractGameState", default="Scheduled"),
                "home_score": safe_get(teams, "home", "score"),
                "away_score": safe_get(teams, "away", "score"),
                "extra": json.dumps({
                    "probable_pitchers": {
                        "home": safe_get(teams, "home", "probablePitcher", "fullName"),
                        "away": safe_get(teams, "away", "probablePitcher", "fullName"),
                    },
                    "weather": g.get("weather"),
                }),
            })
    return out


def _innings_to_outs(ip) -> float | None:
    if ip is None:
        return None
    try:
        whole, _, frac = str(ip).partition(".")
        return int(whole) * 3 + int(frac or 0)
    except (ValueError, TypeError):
        return None


def fetch_box_scores(on: date) -> tuple[list[dict], list[dict]]:
    """Returns (player_stats_rows, player_rows)."""
    sched = fetch_schedule(on)
    stats: list[dict] = []
    players: list[dict] = []
    for g in sched:
        gid = g["game_id"].removeprefix("MLB-")
        box = http_get_json(f"{BASE}/api/v1/game/{gid}/boxscore")
        if not box:
            continue
        for side in ("home", "away"):
            tb = safe_get(box, "teams", side, default={}) or {}
            team_name = safe_get(tb, "team", "name")
            opp = g["away_team"] if side == "home" else g["home_team"]
            for _pid, pdata in (tb.get("players") or {}).items():
                person = pdata.get("person") or {}
                stat = pdata.get("stats") or {}
                bat = stat.get("batting") or {}
                pit = stat.get("pitching") or {}
                if not bat and not pit:
                    continue
                pid = f"MLB-{person.get('id')}"
                full_name = person.get("fullName")
                if not full_name:
                    continue
                players.append({
                    "player_id": pid,
                    "sport": "MLB",
                    "full_name": full_name,
                    "team": team_name,
                    "position": safe_get(pdata, "position", "abbreviation"),
                })
                payload = {
                    "batter_hits": bat.get("hits"),
                    "batter_total_bases": bat.get("totalBases"),
                    "batter_home_runs": bat.get("homeRuns"),
                    "batter_rbis": bat.get("rbi"),
                    "batter_runs": bat.get("runs"),
                    "batter_strikeouts": bat.get("strikeOuts"),
                    "batter_walks": bat.get("baseOnBalls"),
                    "at_bats": bat.get("atBats"),
                    "pitcher_strikeouts": pit.get("strikeOuts"),
                    "pitcher_outs": _innings_to_outs(pit.get("inningsPitched")),
                    "pitcher_earned_runs": pit.get("earnedRuns"),
                    "pitcher_hits_allowed": pit.get("hits"),
                    "pitcher_walks": pit.get("baseOnBalls"),
                }
                stats.append({
                    "sport": "MLB",
                    "game_id": g["game_id"],
                    "player_id": pid,
                    "game_date": on.isoformat(),
                    "team": team_name,
                    "opp_team": opp,
                    "home": 1 if side == "home" else 0,
                    "minutes": None,
                    "stats_json": json.dumps(payload),
                })
    return stats, players
