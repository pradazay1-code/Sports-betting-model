"""Tennis — ESPN public site API (ATP + WTA), schedule only.

Tennis is modelled at the match level (total games over/under) rather than as
player rolling props, so this source only feeds the schedule; the total-games
projection lives in app.models.game_model.predict_tennis.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from app.utils import get_logger, http_get_json, safe_get

LOG = get_logger("tennis")
BASE = "https://site.api.espn.com/apis/site/v2/sports/tennis"
TOURS = ("atp", "wta")

# Grand slams play best-of-5 for men (more games). Everything else best-of-3.
_BO5_HINTS = ("grand slam", "australian open", "french open", "roland garros",
              "wimbledon", "us open")


def _num(v: Any) -> float | None:
    try:
        return float(v) if v not in (None, "", "-") else None
    except (ValueError, TypeError):
        return None


def _competitor_name(c: dict) -> str | None:
    a = c.get("athlete") or {}
    return a.get("displayName") or c.get("displayName") or (c.get("roster") or [{}])[0].get("displayName")


def fetch_schedule(on: date) -> list[dict]:
    out: list[dict] = []
    for tour in TOURS:
        data = http_get_json(f"{BASE}/{tour}/scoreboard",
                             params={"dates": on.strftime("%Y%m%d")}) or {}
        league = safe_get(data, "leagues", 0, "name") or tour.upper()
        for ev in data.get("events", []) or []:
            comp = safe_get(ev, "competitions", 0) or {}
            comps = comp.get("competitors", []) or []
            if len(comps) < 2:
                continue
            p1, p2 = _competitor_name(comps[0]), _competitor_name(comps[1])
            if not p1 or not p2:
                continue  # skip doubles / malformed
            note = " ".join(str(x) for x in (league, safe_get(ev, "name", default=""))).lower()
            bo5 = tour == "atp" and any(h in note for h in _BO5_HINTS)
            out.append({
                "game_id": f"TEN-{ev.get('id')}",
                "sport": "TEN",
                "game_date": on.isoformat(),
                "start_utc": ev.get("date"),
                "home_team": p1,
                "away_team": p2,
                "venue": league,
                "status": safe_get(ev, "status", "type", "description") or "Scheduled",
                "home_score": _num(safe_get(comps[0], "score")),
                "away_score": _num(safe_get(comps[1], "score")),
                "extra": json.dumps({"tour": tour, "best_of": 5 if bo5 else 3}),
            })
    return out


def fetch_box_scores(on: date) -> tuple[list[dict], list[dict]]:
    # Tennis is projected at match level; no per-player rolling stats yet.
    return [], []
