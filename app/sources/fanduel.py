"""FanDuel public sportsbook JSON.

FanDuel exposes /api/sports/* endpoints that mirror the consumer site. We
grab the "all-markets" tab per event group; each market's outcomes carry
a participant + line + American odds.
"""

from __future__ import annotations

import re

from app.sources.markets import map_market
from app.utils import http_get_json, now_iso

EVENT_GROUPS = {
    # FanDuel's "compId" per league.
    "NBA": 10547864,
    "MLB": 9926401,
    "NHL": 8946682,
}

BASE = "https://sbapi.nj.sportsbook.fanduel.com"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://sportsbook.fanduel.com/",
}


def _amer(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _strip_side(label: str | None) -> str:
    if not label:
        return ""
    return re.sub(r"\b(over|under)\b\s*\d+(\.\d+)?", "", label, flags=re.IGNORECASE).strip()


def fetch_offers() -> list[dict]:
    fetched = now_iso()
    pairs: dict[tuple, dict] = {}
    for sport, eg in EVENT_GROUPS.items():
        data = http_get_json(
            f"{BASE}/api/content-managed-page",
            params={
                "page": "CUSTOM",
                "customPageId": str(eg),
                "_ak": "FhMFpcPWXMeyZxOx",
                "timezone": "America/New_York",
            },
            headers=HEADERS,
        )
        if not data:
            continue
        attachments = (data.get("attachments") or {})
        markets = attachments.get("markets") or {}
        events = attachments.get("events") or {}
        for _mid, mk in markets.items():
            market = map_market(sport, mk.get("marketName"))
            if not market:
                continue
            event_id = str(mk.get("eventId") or "")
            event = events.get(event_id) or {}
            outcomes = mk.get("runners") or []
            grouped: dict[tuple, dict[str, int]] = {}
            for o in outcomes:
                label = (o.get("runnerName") or "").lower()
                side = "over" if "over" in label else "under" if "under" in label else None
                line = o.get("handicap")
                price = _amer((o.get("winRunnerOdds") or {}).get("americanDisplayOdds", {}).get("americanOdds"))
                if price is None:
                    price = _amer((o.get("winRunnerOdds") or {}).get("americanOdds"))
                if side is None or line is None or price is None:
                    continue
                name = (mk.get("eventName") and _strip_side(mk.get("marketName"))) or _strip_side(o.get("runnerName"))
                # FanDuel often packages player in marketName as "<Player> - <stat>"
                if " - " in (mk.get("marketName") or ""):
                    name = (mk.get("marketName") or "").split(" - ")[0].strip()
                if not name:
                    continue
                key = (name, market, float(line))
                grouped.setdefault(key, {})[side] = price
            for (name, market_, line_val), grp in grouped.items():
                pairs[(sport, name, market_, line_val, "fanduel")] = {
                    "fetched_at": fetched,
                    "sport": sport,
                    "game_id": None,
                    "player_id": None,
                    "player_name": name,
                    "team": None,
                    "market": market_,
                    "line": line_val,
                    "over_price": grp.get("over"),
                    "under_price": grp.get("under"),
                    "book": "fanduel",
                }
            _ = event  # available for future game-id mapping
    return list(pairs.values())
