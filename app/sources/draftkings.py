"""DraftKings public sportsbook JSON.

The eventgroups + subcategories endpoint exposes player prop offers with both
sides and American odds. Sometimes blocks cloud IPs.
"""

from __future__ import annotations

import re

from app.sources.markets import map_market
from app.utils import http_get_json, now_iso, safe_get

EVENT_GROUPS = {"MLB": 84240, "NBA": 42648, "NHL": 42133}

BASE = "https://sportsbook-nash.draftkings.com"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}


def _strip_side(label: str | None) -> str:
    if not label:
        return ""
    return re.sub(r"\b(over|under)\b\s*\d+(\.\d+)?", "", label, flags=re.IGNORECASE).strip()


def _to_int(price) -> int | None:
    if price in (None, "", "EVEN"):
        return 100
    try:
        return int(str(price).replace("−", "-").replace("+", ""))
    except (TypeError, ValueError):
        return None


def fetch_offers() -> list[dict]:
    fetched = now_iso()
    pairs: dict[tuple, dict] = {}
    for sport, eg in EVENT_GROUPS.items():
        root = http_get_json(f"{BASE}/sites/US-SB/api/v5/eventgroups/{eg}", params={"format": "json"}, headers=HEADERS)
        if not root:
            continue
        cats = safe_get(root, "eventGroup", "offerCategories", default=[]) or []
        events = {str(e.get("eventId")): e for e in safe_get(root, "eventGroup", "events", default=[]) or []}
        for cat in cats:
            cat_id = cat.get("offerCategoryId")
            for desc in cat.get("offerSubcategoryDescriptors") or []:
                sub_id = desc.get("subcategoryId")
                market = map_market(sport, desc.get("name"))
                if not market:
                    continue
                sub = http_get_json(
                    f"{BASE}/sites/US-SB/api/v5/eventgroups/{eg}/categories/{cat_id}/subcategories/{sub_id}",
                    params={"format": "json"},
                    headers=HEADERS,
                )
                if not sub:
                    continue
                try:
                    offers = (
                        safe_get(sub, "eventGroup", "offerCategories", default=[{}])[0]
                        .get("offerSubcategoryDescriptors", [{}])[0]
                        .get("offerSubcategory", {})
                        .get("offers", [])
                    )
                except (IndexError, AttributeError):
                    offers = []
                for offer_group in offers:
                    for offer in offer_group:
                        ev = events.get(str(offer.get("eventId"))) or {}
                        outcomes = offer.get("outcomes") or []
                        line_groups: dict[tuple, dict[str, int]] = {}
                        for o in outcomes:
                            label = (o.get("label") or "").lower()
                            side = "over" if "over" in label else "under" if "under" in label else None
                            line = o.get("line")
                            price = _to_int(o.get("oddsAmerican"))
                            if not side or line is None or price is None:
                                continue
                            name = o.get("participant") or _strip_side(o.get("label"))
                            if not name:
                                continue
                            key = (sport, name, market, float(line))
                            grp = line_groups.setdefault(key, {})
                            grp[side] = price
                        for (sport_, name, market_, line_val), grp in line_groups.items():
                            pairs[(sport_, name, market_, line_val, "draftkings")] = {
                                "fetched_at": fetched,
                                "sport": sport_,
                                "game_id": None,
                                "player_id": None,
                                "player_name": name,
                                "team": None,
                                "market": market_,
                                "line": line_val,
                                "over_price": grp.get("over"),
                                "under_price": grp.get("under"),
                                "book": "draftkings",
                            }
    return list(pairs.values())
