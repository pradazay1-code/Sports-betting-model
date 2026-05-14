"""ESPN public injury feeds — same shape across sports."""

from __future__ import annotations

from app.utils import http_get_json, now_iso

SPORT_PATHS = {
    "NBA": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries",
    "MLB": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/injuries",
    "NHL": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/injuries",
}


def fetch_all() -> list[dict]:
    fetched = now_iso()
    out: list[dict] = []
    for sport, url in SPORT_PATHS.items():
        data = http_get_json(url)
        if not data:
            continue
        for team in data.get("injuries", []) or []:
            team_name = (team.get("displayName") or team.get("name") or "").strip()
            for item in team.get("injuries", []) or []:
                ath = item.get("athlete") or {}
                name = ath.get("displayName") or ath.get("fullName")
                if not name:
                    continue
                status = item.get("status") or item.get("type") or "Unknown"
                detail = (item.get("longComment") or item.get("shortComment") or "").strip()[:240]
                out.append({
                    "sport": sport,
                    "fetched_at": fetched,
                    "team": team_name,
                    "player_name": name,
                    "status": status,
                    "detail": detail or None,
                })
    return out
