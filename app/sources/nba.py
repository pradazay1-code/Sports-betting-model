"""NBA — stats.nba.com public endpoints. Browser headers required."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from app.utils import http_get_json, safe_get

BASE = "https://stats.nba.com"
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}


def _num(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def _minutes_to_float(v: Any) -> float | None:
    if v is None:
        return None
    s = str(v)
    if ":" in s:
        m, sec = s.split(":", 1)
        try:
            return float(m) + float(sec) / 60.0
        except ValueError:
            return None
    return _num(s)


def _sum_or_none(*vals: Any) -> float | None:
    if any(v is None for v in vals):
        return None
    return float(sum(vals))


def fetch_schedule(on: date) -> list[dict]:
    data = http_get_json(
        f"{BASE}/stats/scoreboardv3",
        params={"GameDate": on.strftime("%m/%d/%Y"), "LeagueID": "00"},
        headers=HEADERS,
    ) or {}
    out: list[dict] = []
    for g in safe_get(data, "scoreboard", "games", default=[]) or []:
        out.append({
            "game_id": f"NBA-{g.get('gameId')}",
            "sport": "NBA",
            "game_date": on.isoformat(),
            "start_utc": g.get("gameTimeUTC"),
            "home_team": safe_get(g, "homeTeam", "teamName"),
            "away_team": safe_get(g, "awayTeam", "teamName"),
            "venue": safe_get(g, "arena", "arenaName"),
            "status": g.get("gameStatusText", "Scheduled"),
            "home_score": safe_get(g, "homeTeam", "score"),
            "away_score": safe_get(g, "awayTeam", "score"),
            "extra": None,
        })
    return out


def fetch_box_scores(on: date) -> tuple[list[dict], list[dict]]:
    sched = fetch_schedule(on)
    stats: list[dict] = []
    players: list[dict] = []
    for g in sched:
        gid = g["game_id"].removeprefix("NBA-")
        data = http_get_json(
            f"{BASE}/stats/boxscoretraditionalv3",
            params={
                "GameID": gid, "LeagueID": "00", "endPeriod": 0, "endRange": 28800,
                "rangeType": 0, "startPeriod": 0, "startRange": 0,
            },
            headers=HEADERS,
        )
        if not data:
            continue
        box = data.get("boxScoreTraditional") or {}
        for side, opp_side in (("homeTeam", "awayTeam"), ("awayTeam", "homeTeam")):
            tb = box.get(side, {}) or {}
            team = tb.get("teamName")
            opp = (box.get(opp_side) or {}).get("teamName")
            for p in tb.get("players", []) or []:
                s = p.get("statistics", {}) or {}
                pts = _num(s.get("points"))
                reb = _num(s.get("reboundsTotal"))
                ast = _num(s.get("assists"))
                full_name = f"{p.get('firstName','')} {p.get('familyName','')}".strip()
                if not full_name:
                    continue
                pid = f"NBA-{p.get('personId')}"
                players.append({
                    "player_id": pid,
                    "sport": "NBA",
                    "full_name": full_name,
                    "team": team,
                    "position": p.get("position"),
                })
                payload = {
                    "player_points": pts,
                    "player_rebounds": reb,
                    "player_assists": ast,
                    "player_threes": _num(s.get("threePointersMade")),
                    "player_steals": _num(s.get("steals")),
                    "player_blocks": _num(s.get("blocks")),
                    "player_turnovers": _num(s.get("turnovers")),
                    "player_minutes": _minutes_to_float(s.get("minutes")),
                    "player_fga": _num(s.get("fieldGoalsAttempted")),
                    "player_fta": _num(s.get("freeThrowsAttempted")),
                    "player_pra": _sum_or_none(pts, reb, ast),
                    "usage_rate": _num(s.get("usagePercentage")),
                }
                stats.append({
                    "sport": "NBA",
                    "game_id": g["game_id"],
                    "player_id": pid,
                    "game_date": on.isoformat(),
                    "team": team,
                    "opp_team": opp,
                    "home": 1 if side == "homeTeam" else 0,
                    "minutes": payload["player_minutes"],
                    "stats_json": json.dumps(payload),
                })
    return stats, players
