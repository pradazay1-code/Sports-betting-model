"""NBA — ESPN's site.api.espn.com endpoints.

We use ESPN instead of stats.nba.com because:
  - stats.nba.com aggressively rate-limits cloud IPs (Github Actions
    runners get HTTP timeouts on most requests)
  - ESPN's scoreboard+summary endpoints are public, cloud-friendly,
    and serve the same box-score data we need

Same function signatures as the other sport modules so ingest.py is unchanged.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from app.utils import http_get_json

BASE = "https://site.api.espn.com"
PATH = "basketball/nba"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        s = str(v).strip()
        if "-" in s and not s.startswith("-"):
            # "8-12" style — take the made portion
            return float(s.split("-")[0])
        return float(s)
    except (ValueError, TypeError):
        return None


def _sum_or_none(*vals) -> float | None:
    if any(v is None for v in vals):
        return None
    return float(sum(vals))


def _drop_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def fetch_schedule(on: date) -> list[dict]:
    ymd = on.strftime("%Y%m%d")
    data = http_get_json(
        f"{BASE}/apis/site/v2/sports/{PATH}/scoreboard",
        params={"dates": ymd},
        headers=HEADERS,
    ) or {}
    out: list[dict] = []
    for ev in data.get("events") or []:
        comps = (ev.get("competitions") or [{}])[0].get("competitors") or []
        home = away = venue = None
        home_score = away_score = None
        for c in comps:
            team = c.get("team") or {}
            name = team.get("displayName")
            try:
                score = int(c.get("score")) if c.get("score") not in (None, "") else None
            except (TypeError, ValueError):
                score = None
            if c.get("homeAway") == "home":
                home = name; home_score = score
            else:
                away = name; away_score = score
        venue = ((ev.get("competitions") or [{}])[0].get("venue") or {}).get("fullName")
        out.append({
            "game_id": f"NBA-{ev.get('id')}",
            "sport": "NBA",
            "game_date": on.isoformat(),
            "start_utc": ev.get("date"),
            "home_team": home,
            "away_team": away,
            "venue": venue,
            "status": ((ev.get("status") or {}).get("type") or {}).get("description", "Scheduled"),
            "home_score": home_score,
            "away_score": away_score,
            "extra": None,
        })
    return out


def fetch_box_scores(on: date) -> tuple[list[dict], list[dict]]:
    sched = fetch_schedule(on)
    stats: list[dict] = []
    players: list[dict] = []
    for g in sched:
        gid = g["game_id"].removeprefix("NBA-")
        summary = http_get_json(
            f"{BASE}/apis/site/v2/sports/{PATH}/summary",
            params={"event": gid},
            headers=HEADERS,
        )
        if not summary:
            continue
        box = summary.get("boxscore") or {}
        for team_block in box.get("players") or []:
            team_name = (team_block.get("team") or {}).get("displayName")
            opp = g["away_team"] if team_name == g["home_team"] else g["home_team"]
            is_home = team_name == g["home_team"]
            for grp in team_block.get("statistics") or []:
                names = [n.lower() for n in (grp.get("names") or [])]
                idx = {n: i for i, n in enumerate(names)}

                def get(*keys: str, _vals=None) -> float | None:
                    if _vals is None:
                        return None
                    for k in keys:
                        if k in idx and idx[k] < len(_vals):
                            return _num(_vals[idx[k]])
                    return None

                for ath in grp.get("athletes") or []:
                    person = ath.get("athlete") or {}
                    stats_arr = ath.get("stats") or []
                    if not stats_arr:
                        continue
                    pts   = get("pts", _vals=stats_arr)
                    reb   = get("reb", _vals=stats_arr)
                    ast   = get("ast", _vals=stats_arr)
                    three = get("3pt", _vals=stats_arr)
                    stl   = get("stl", _vals=stats_arr)
                    blk   = get("blk", _vals=stats_arr)
                    to_   = get("to",  _vals=stats_arr)
                    mins  = get("min", _vals=stats_arr)
                    full_name = person.get("displayName")
                    if not full_name:
                        continue
                    pid = f"NBA-{person.get('id')}"
                    players.append({
                        "player_id": pid,
                        "sport": "NBA",
                        "full_name": full_name,
                        "team": team_name,
                        "position": (person.get("position") or {}).get("abbreviation")
                                    if isinstance(person.get("position"), dict) else person.get("position"),
                    })
                    payload = _drop_none({
                        "player_points": pts,
                        "player_rebounds": reb,
                        "player_assists": ast,
                        "player_threes": three,
                        "player_steals": stl,
                        "player_blocks": blk,
                        "player_turnovers": to_,
                        "player_minutes": mins,
                        "player_pra": _sum_or_none(pts, reb, ast),
                    })
                    if not payload:
                        continue
                    stats.append({
                        "sport": "NBA",
                        "game_id": g["game_id"],
                        "player_id": pid,
                        "game_date": on.isoformat(),
                        "team": team_name,
                        "opp_team": opp,
                        "home": 1 if is_home else 0,
                        "minutes": mins,
                        "stats_json": json.dumps(payload),
                    })
    return stats, players
