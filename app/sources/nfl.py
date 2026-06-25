"""NFL — ESPN public site API (free, no key).

Schedule:  site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=YYYYMMDD
Box score: site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event=<id>

ESPN groups box-score stats into categories (passing/rushing/receiving) whose
`keys` array names the columns and whose `athletes[].stats` list aligns to it.
We map the keys we care about into the canonical market names from
app.config.MARKETS["NFL"].
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from app.utils import get_logger, http_get_json, safe_get

LOG = get_logger("nfl")

BASE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"


def _num(v: Any) -> float | None:
    if v is None:
        return None
    s = str(v).strip()
    if s in ("", "-", "--"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fetch_schedule(on: date) -> list[dict]:
    data = http_get_json(f"{BASE}/scoreboard", params={"dates": on.strftime("%Y%m%d")}) or {}
    out: list[dict] = []
    for ev in data.get("events", []) or []:
        comp = safe_get(ev, "competitions", 0) or {}
        competitors = comp.get("competitors", []) or []
        home = next((c for c in competitors if c.get("homeAway") == "home"), {})
        away = next((c for c in competitors if c.get("homeAway") == "away"), {})
        out.append({
            "game_id": f"NFL-{ev.get('id')}",
            "sport": "NFL",
            "game_date": on.isoformat(),
            "start_utc": ev.get("date"),
            "home_team": safe_get(home, "team", "displayName"),
            "away_team": safe_get(away, "team", "displayName"),
            "venue": safe_get(comp, "venue", "fullName"),
            "status": safe_get(ev, "status", "type", "description") or "Scheduled",
            "home_score": _num(home.get("score")),
            "away_score": _num(away.get("score")),
            "extra": None,
        })
    return out


# (category name, espn stat key) -> canonical market. "C/ATT" combined keys
# are handled separately below.
_KEY_MAP = {
    ("passing", "passingYards"): "player_pass_yards",
    ("passing", "passingTouchdowns"): "player_pass_tds",
    ("passing", "interceptions"): "player_interceptions",
    ("rushing", "rushingYards"): "player_rush_yards",
    ("rushing", "rushingAttempts"): "player_rush_attempts",
    ("receiving", "receptions"): "player_receptions",
    ("receiving", "receivingYards"): "player_rec_yards",
}


def _parse_category(cat: dict, payloads: dict[str, dict]) -> None:
    name = (cat.get("name") or "").lower()
    keys = cat.get("keys") or []
    for ath in cat.get("athletes", []) or []:
        a = ath.get("athlete") or {}
        full = a.get("displayName")
        if not full:
            continue
        stats = ath.get("stats") or []
        row = payloads.setdefault(full, {"_id": a.get("id"), "_pos": safe_get(a, "position", "abbreviation")})
        for key, val in zip(keys, stats):
            market = _KEY_MAP.get((name, key))
            if market:
                row[market] = _num(val)
            # Combined "completions/attempts" -> "20/30".
            if name == "passing" and key in ("completions/passingAttempts", "C/ATT"):
                if isinstance(val, str) and "/" in val:
                    comp, att = val.split("/", 1)
                    row["player_pass_completions"] = _num(comp)
                    row["player_pass_attempts"] = _num(att)


def fetch_box_scores(on: date) -> tuple[list[dict], list[dict]]:
    sched = fetch_schedule(on)
    stats: list[dict] = []
    players: list[dict] = []
    for g in sched:
        eid = g["game_id"].removeprefix("NFL-")
        data = http_get_json(f"{BASE}/summary", params={"event": eid})
        if not data:
            continue
        teams = safe_get(data, "boxscore", "players", default=[]) or []
        team_names = {}
        for tb in teams:
            team_names[id(tb)] = safe_get(tb, "team", "displayName")
        for tb in teams:
            team = safe_get(tb, "team", "displayName")
            opp = next((safe_get(o, "team", "displayName") for o in teams if o is not tb), None)
            is_home = team == g.get("home_team")
            payloads: dict[str, dict] = {}
            for cat in tb.get("statistics", []) or []:
                _parse_category(cat, payloads)
            for full, payload in payloads.items():
                pid = f"NFL-{payload.pop('_id', None) or full}"
                pos = payload.pop("_pos", None)
                if not any(v is not None for v in payload.values()):
                    continue
                players.append({"player_id": pid, "sport": "NFL", "full_name": full,
                                "team": team, "position": pos})
                stats.append({
                    "sport": "NFL", "game_id": g["game_id"], "player_id": pid,
                    "game_date": on.isoformat(), "team": team, "opp_team": opp,
                    "home": 1 if is_home else 0, "minutes": None,
                    "stats_json": json.dumps(payload),
                })
    return stats, players
