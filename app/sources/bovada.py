"""Bovada public coupon JSON — second free book."""

from __future__ import annotations

from datetime import datetime

from app.sources.markets import map_market
from app.utils import http_get_json, now_iso

BASE = "https://www.bovada.lv"
HEADERS = {
    "Accept": "application/json",
    "Referer": "https://www.bovada.lv/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}
PATHS = {
    "MLB": "/services/sports/event/coupon/events/A/description/baseball/mlb",
    "NBA": "/services/sports/event/coupon/events/A/description/basketball/nba",
    "NHL": "/services/sports/event/coupon/events/A/description/hockey/nhl",
}


def _walk(node, out):
    if isinstance(node, list):
        for x in node:
            _walk(x, out)
    elif isinstance(node, dict):
        if isinstance(node.get("events"), list):
            out.extend(node["events"])
        if isinstance(node.get("children"), list):
            _walk(node["children"], out)


def _amer(val) -> int | None:
    if val in (None, "", "EVEN"):
        return 100
    try:
        return int(str(val).replace("+", ""))
    except (TypeError, ValueError):
        return None


def fetch_offers() -> list[dict]:
    fetched = now_iso()
    pairs: dict[tuple, dict] = {}
    for sport, path in PATHS.items():
        data = http_get_json(f"{BASE}{path}", params={"marketFilterId": "def", "lang": "en"}, headers=HEADERS)
        if not data:
            continue
        events: list[dict] = []
        _walk(data, events)
        for ev in events:
            home = away = None
            for c in ev.get("competitors") or []:
                if c.get("home"):
                    home = c.get("name")
                else:
                    away = c.get("name")
            for dg in ev.get("displayGroups") or []:
                for mk in dg.get("markets") or []:
                    desc = mk.get("description") or ""
                    market = map_market(sport, desc)
                    if not market:
                        continue
                    player_from_desc = desc.split(" - ")[0].strip() if " - " in desc else None
                    grouped: dict[tuple, dict[str, int]] = {}
                    for o in mk.get("outcomes") or []:
                        name = (o.get("competitor") or "").strip() or player_from_desc or (o.get("description") or "").strip()
                        if not name:
                            continue
                        price_obj = o.get("price") or {}
                        line = price_obj.get("handicap")
                        if line is None:
                            continue
                        price = _amer(price_obj.get("american"))
                        if price is None:
                            continue
                        side_label = (o.get("description") or "").lower()
                        side = "over" if "over" in side_label else "under" if "under" in side_label else None
                        if not side:
                            continue
                        key = (name, market, float(line))
                        grouped.setdefault(key, {})[side] = price
                    for (name, market_, line_val), grp in grouped.items():
                        pairs[(sport, name, market_, line_val, "bovada")] = {
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
                            "book": "bovada",
                        }
                    _ = home, away  # available for future game-id mapping
    return list(pairs.values())
