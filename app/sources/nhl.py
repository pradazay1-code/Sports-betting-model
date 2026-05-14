"""NHL — api-web.nhle.com (public, no key)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from app.utils import http_get_json

BASE = "https://api-web.nhle.com"


def _num(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def _team_name(t: dict) -> str:
    n = t.get("commonName") or t.get("name") or {}
    if isinstance(n, dict):
        return n.get("default") or t.get("abbrev") or ""
    return n or t.get("abbrev") or ""


def fetch_schedule(on: date) -> list[dict]:
    data = http_get_json(f"{BASE}/v1/schedule/{on.isoformat()}") or {}
    out: list[dict] = []
    for week in data.get("gameWeek", []) or []:
        if week.get("date") != on.isoformat():
            continue
        for g in week.get("games", []) or []:
            home = g.get("homeTeam", {}) or {}
            away = g.get("awayTeam", {}) or {}
            out.append({
                "game_id": f"NHL-{g.get('id')}",
                "sport": "NHL",
                "game_date": on.isoformat(),
                "start_utc": g.get("startTimeUTC"),
                "home_team": _team_name(home),
                "away_team": _team_name(away),
                "venue": (g.get("venue") or {}).get("default"),
                "status": g.get("gameState", "FUT"),
                "home_score": home.get("score"),
                "away_score": away.get("score"),
                "extra": None,
            })
    return out


def fetch_box_scores(on: date) -> tuple[list[dict], list[dict]]:
    sched = fetch_schedule(on)
    stats: list[dict] = []
    players: list[dict] = []
    for g in sched:
        gid = g["game_id"].removeprefix("NHL-")
        box = http_get_json(f"{BASE}/v1/gamecenter/{gid}/boxscore")
        if not box:
            continue
        pbg = box.get("playerByGameStats") or {}
        for side, _opp_side in (("homeTeam", "awayTeam"), ("awayTeam", "homeTeam")):
            team = g["home_team"] if side == "homeTeam" else g["away_team"]
            opp = g["away_team"] if side == "homeTeam" else g["home_team"]
            squad = pbg.get(side, {}) or {}
            for group in ("forwards", "defense", "goalies"):
                for p in squad.get(group, []) or []:
                    is_goalie = group == "goalies"
                    nm = p.get("name")
                    full_name = nm.get("default") if isinstance(nm, dict) else nm
                    if not full_name:
                        continue
                    pid = f"NHL-{p.get('playerId')}"
                    players.append({
                        "player_id": pid,
                        "sport": "NHL",
                        "full_name": full_name,
                        "team": team,
                        "position": "G" if is_goalie else (p.get("position") or group[:1].upper()),
                    })
                    if is_goalie:
                        payload = {
                            "goalie_saves": _num(p.get("saves")),
                            "goalie_shots_against": _num(p.get("shotsAgainst")),
                            "goalie_goals_against": _num(p.get("goalsAgainst")),
                        }
                    else:
                        payload = {
                            "player_goals": _num(p.get("goals")),
                            "player_assists": _num(p.get("assists")),
                            "player_points": _num(p.get("points")),
                            "player_shots_on_goal": _num(p.get("sog")),
                            "player_pim": _num(p.get("pim")),
                            "player_hits": _num(p.get("hits")),
                            "player_blocks": _num(p.get("blockedShots")),
                        }
                    stats.append({
                        "sport": "NHL",
                        "game_id": g["game_id"],
                        "player_id": pid,
                        "game_date": on.isoformat(),
                        "team": team,
                        "opp_team": opp,
                        "home": 1 if side == "homeTeam" else 0,
                        "minutes": None,
                        "stats_json": json.dumps(payload),
                    })
    return stats, players
