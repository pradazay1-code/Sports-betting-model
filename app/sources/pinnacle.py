"""Pinnacle guest API — sharp lines, our best de-vig anchor.

Pinnacle takes high limits so its no-vig prices are close to the true
probability. We weight Pinnacle's de-vig heavier when computing consensus
fair probability.
"""

from __future__ import annotations

from app.sources.markets import map_market
from app.utils import http_get_json, now_iso

SPORTS = {"NBA": 487, "MLB": 246, "NHL": 1456}  # Pinnacle sport IDs

BASE = "https://guest.api.arcadia.pinnacle.com/0.1"
HEADERS = {
    "Accept": "application/json",
    "X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",  # public guest key
    "Referer": "https://www.pinnacle.com/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}


def _amer(v) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def fetch_offers() -> list[dict]:
    fetched = now_iso()
    out: dict[tuple, dict] = {}
    for sport, sid in SPORTS.items():
        matchups = http_get_json(f"{BASE}/sports/{sid}/matchups", headers=HEADERS) or []
        if not isinstance(matchups, list):
            continue
        for m in matchups:
            mid = m.get("id")
            if not mid:
                continue
            markets = http_get_json(f"{BASE}/matchups/{mid}/markets/related/straight",
                                    headers=HEADERS) or []
            if not isinstance(markets, list):
                continue
            for mk in markets:
                desc = (mk.get("key") or "") + " " + (mk.get("type") or "")
                # Pinnacle classifies player props under "special" matchups —
                # we only ingest game-level totals/spreads here. Prop lines
                # exist via /specials/* but the schema is messier; we leave
                # that as a TODO. For now Pinnacle contributes game lines.
                market = None
                if mk.get("type") == "total":
                    market = "game_total"
                elif mk.get("type") == "spread":
                    market = "game_spread"
                elif mk.get("type") == "moneyline":
                    market = "game_moneyline"
                if not market:
                    continue
                for price in mk.get("prices") or []:
                    designation = (price.get("designation") or "").lower()
                    points = price.get("points")
                    p = _amer(price.get("price"))
                    if p is None:
                        continue
                    side = (
                        "over" if designation == "over" else
                        "under" if designation == "under" else
                        "home" if designation == "home" else
                        "away" if designation == "away" else None
                    )
                    if not side:
                        continue
                    key = (sport, str(mid), market, points or 0.0, side)
                    out[key] = {
                        "fetched_at": fetched,
                        "sport": sport,
                        "game_id": None,
                        "player_id": None,
                        "player_name": f"GAME-{mid}",
                        "team": None,
                        "market": market,
                        "line": float(points) if points is not None else 0.0,
                        # Store as the side that won the row.
                        "over_price": p if side in ("over", "home") else None,
                        "under_price": p if side in ("under", "away") else None,
                        "book": "pinnacle",
                    }
    return list(out.values())
