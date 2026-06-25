"""Soccer — ESPN public site API (free, no key).

Covered under the internal sport code "EPL" but actually spans the major
leagues ESPN exposes: Premier League, La Liga, Bundesliga, Serie A, Ligue 1,
Champions League and MLS. Each has its own slug under /sports/soccer/<slug>.

Schedule:  site.api.espn.com/apis/site/v2/sports/soccer/<slug>/scoreboard?dates=YYYYMMDD
Box score: site.api.espn.com/apis/site/v2/sports/soccer/<slug>/summary?event=<id>

Player-level soccer stats in ESPN's free feed are less consistent than the US
sports, so the box-score parser is best-effort and returns an empty list
rather than raising when a match has no published per-player stats.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from app.utils import get_logger, http_get_json, safe_get

LOG = get_logger("soccer")

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# Leagues/competitions we sweep. World Cup first so its matches take priority
# while the tournament is live. Order is also the de-dup priority for a player
# appearing in multiple comps.
LEAGUES = (
    "fifa.world",            # FIFA World Cup (live Jun–Jul 2026)
    "fifa.friendly",         # international friendlies / warmups
    "uefa.euro",             # Euros
    "conmebol.america",      # Copa America
    "eng.1", "esp.1", "ger.1", "ita.1", "fra.1",
    "uefa.champions", "uefa.europa",
    "usa.1", "mex.1",
)

# ESPN soccer stat label/abbreviation -> canonical market.
_STAT_MAP = {
    "shots": "player_shots",
    "totalshots": "player_shots",
    "shotsontarget": "player_shots_on_target",
    "shots on goal": "player_shots_on_target",
    "goals": "player_goals",
    "goalassists": "player_assists",
    "assists": "player_assists",
    "totalpasses": "player_passes",
    "passes": "player_passes",
    "totaltackles": "player_tackles",
    "tackles": "player_tackles",
    "saves": "goalie_saves",
}


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


def _norm_key(s: str | None) -> str:
    return (s or "").lower().replace(" ", "").replace("_", "")


def fetch_schedule(on: date) -> list[dict]:
    out: list[dict] = []
    for slug in LEAGUES:
        data = http_get_json(f"{BASE}/{slug}/scoreboard",
                             params={"dates": on.strftime("%Y%m%d")}) or {}
        for ev in data.get("events", []) or []:
            comp = safe_get(ev, "competitions", 0) or {}
            competitors = comp.get("competitors", []) or []
            home = next((c for c in competitors if c.get("homeAway") == "home"), {})
            away = next((c for c in competitors if c.get("homeAway") == "away"), {})
            out.append({
                "game_id": f"EPL-{ev.get('id')}",
                "sport": "EPL",
                "game_date": on.isoformat(),
                "start_utc": ev.get("date"),
                "home_team": safe_get(home, "team", "displayName"),
                "away_team": safe_get(away, "team", "displayName"),
                "venue": safe_get(comp, "venue", "fullName"),
                "status": safe_get(ev, "status", "type", "description") or "Scheduled",
                "home_score": _num(home.get("score")),
                "away_score": _num(away.get("score")),
                "extra": json.dumps({"league": slug}),
            })
    return out


def _athlete_stats(stats_block: list[dict]) -> dict:
    """ESPN rosters give a list of {name/abbreviation/displayValue}. Map the
    ones we recognise into canonical markets."""
    out: dict[str, float | None] = {}
    for st in stats_block or []:
        label = _norm_key(st.get("abbreviation") or st.get("name") or st.get("displayName"))
        market = _STAT_MAP.get(label)
        if market:
            out[market] = _num(st.get("displayValue") if "displayValue" in st else st.get("value"))
    return out


def fetch_box_scores(on: date) -> tuple[list[dict], list[dict]]:
    sched = fetch_schedule(on)
    stats: list[dict] = []
    players: list[dict] = []
    for g in sched:
        eid = g["game_id"].removeprefix("EPL-")
        league = "eng.1"
        try:
            league = json.loads(g.get("extra") or "{}").get("league", "eng.1")
        except Exception:
            pass
        data = http_get_json(f"{BASE}/{league}/summary", params={"event": eid})
        if not data:
            continue
        rosters = data.get("rosters") or []
        for ros in rosters:
            team = safe_get(ros, "team", "displayName")
            opp = next((safe_get(o, "team", "displayName") for o in rosters if o is not ros), None)
            is_home = team == g.get("home_team")
            for entry in ros.get("roster", []) or []:
                a = entry.get("athlete") or {}
                full = a.get("displayName")
                if not full:
                    continue
                payload = _athlete_stats(entry.get("stats") or [])
                if not any(v is not None for v in payload.values()):
                    continue
                pid = f"EPL-{a.get('id') or full}"
                players.append({"player_id": pid, "sport": "EPL", "full_name": full,
                                "team": team, "position": safe_get(a, "position", "abbreviation")})
                stats.append({
                    "sport": "EPL", "game_id": g["game_id"], "player_id": pid,
                    "game_date": on.isoformat(), "team": team, "opp_team": opp,
                    "home": 1 if is_home else 0, "minutes": None,
                    "stats_json": json.dumps(payload),
                })
    return stats, players
