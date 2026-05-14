"""PrizePicks public projections — fixed payout, treat as -119/-119 each side.

This endpoint sometimes blocks cloud IPs (Cloudflare). When that happens the
pipeline falls back to whichever book endpoint is alive."""

from __future__ import annotations

from app.utils import http_get_json, now_iso

PP_STAT_MAP = {
    "Points": "player_points",
    "Rebounds": "player_rebounds",
    "Assists": "player_assists",
    "3-PT Made": "player_threes",
    "Pts+Rebs+Asts": "player_pra",
    "Steals": "player_steals",
    "Blocks": "player_blocks",
    "Hits": "batter_hits",
    "Total Bases": "batter_total_bases",
    "RBIs": "batter_rbis",
    "Runs": "batter_runs",
    "Hitter Strikeouts": "batter_strikeouts",
    "Pitcher Strikeouts": "pitcher_strikeouts",
    "Pitcher Outs": "pitcher_outs",
    "Earned Runs Allowed": "pitcher_earned_runs",
    "Shots On Goal": "player_shots_on_goal",
    "Goals": "player_goals",
    "Saves": "goalie_saves",
}
LEAGUE_TO_SPORT = {"MLB": "MLB", "NBA": "NBA", "NHL": "NHL"}

HEADERS = {
    "Accept": "application/json",
    "Origin": "https://app.prizepicks.com",
    "Referer": "https://app.prizepicks.com/",
}


def fetch_offers() -> list[dict]:
    data = http_get_json(
        "https://api.prizepicks.com/projections",
        params={"per_page": 1000, "single_stat": "true"},
        headers=HEADERS,
    )
    if not data:
        return []
    included = {(i["type"], i["id"]): i for i in (data.get("included") or [])}
    fetched = now_iso()
    out: list[dict] = []
    for proj in data.get("data") or []:
        attrs = proj.get("attributes") or {}
        rels = proj.get("relationships") or {}
        league_id = ((rels.get("league") or {}).get("data") or {}).get("id")
        league = (included.get(("league", league_id)) or {}).get("attributes", {}).get("name")
        sport = LEAGUE_TO_SPORT.get(league)
        if not sport:
            continue
        market = PP_STAT_MAP.get(attrs.get("stat_type"))
        if not market:
            continue
        pid = ((rels.get("new_player") or {}).get("data") or {}).get("id")
        player = (included.get(("new_player", pid)) or {}).get("attributes", {})
        name = player.get("name")
        line = attrs.get("line_score")
        if not name or line is None:
            continue
        out.append({
            "fetched_at": fetched,
            "sport": sport,
            "game_id": None,
            "player_id": None,
            "player_name": name,
            "team": player.get("team"),
            "market": market,
            "line": float(line),
            # PrizePicks pays roughly -119 on each side of a single stat pick.
            "over_price": -119,
            "under_price": -119,
            "book": "prizepicks",
        })
    return out
