"""Confirmed starting lineups.

MLB:  statsapi /api/v1/game/{gamePk}/boxscore exposes starting lineups.
NBA:  ESPN sometimes carries projected starters in /sports/basketball/nba/teams/{abbrev}/roster.
NHL:  not yet wired; placeholder so the table is populated for MLB at minimum.

Anything we can't fetch reliably is just omitted — the feature pipeline
falls back to "implied from recent box scores" when lineups is empty.
"""

from __future__ import annotations

from datetime import date

from app.sources import mlb
from app.utils import http_get_json


def fetch_mlb(on: date) -> list[dict]:
    sched = mlb.fetch_schedule(on)
    out: list[dict] = []
    for g in sched:
        gid = g["game_id"].removeprefix("MLB-")
        box = http_get_json(f"https://statsapi.mlb.com/api/v1/game/{gid}/boxscore")
        if not box:
            continue
        for side in ("home", "away"):
            tb = (box.get("teams") or {}).get(side) or {}
            team = (tb.get("team") or {}).get("name")
            batting_order = tb.get("battingOrder") or []
            starters = tb.get("pitchers") or []
            for order_idx, pid in enumerate(batting_order):
                pdata = (tb.get("players") or {}).get(f"ID{pid}") or {}
                name = (pdata.get("person") or {}).get("fullName")
                if not name:
                    continue
                out.append({
                    "sport": "MLB",
                    "game_id": g["game_id"],
                    "team": team,
                    "player_id": f"MLB-{pid}",
                    "player_name": name,
                    "role": f"BAT{order_idx + 1}",
                    "starter": 1,
                    "confirmed": 1,
                })
            for pid in starters[:1]:  # starting pitcher only
                pdata = (tb.get("players") or {}).get(f"ID{pid}") or {}
                name = (pdata.get("person") or {}).get("fullName")
                if not name:
                    continue
                out.append({
                    "sport": "MLB",
                    "game_id": g["game_id"],
                    "team": team,
                    "player_id": f"MLB-{pid}",
                    "player_name": name,
                    "role": "SP",
                    "starter": 1,
                    "confirmed": 1,
                })
    return out


def fetch_all(on: date) -> list[dict]:
    out = []
    try:
        out.extend(fetch_mlb(on))
    except Exception:
        pass
    return out
