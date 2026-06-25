"""The Odds API (the-odds-api.com) — reliable live odds for every sport.

This is the recommended live-data backbone. Direct sportsbook scraping
(DraftKings/FanDuel/...) gets IP-blocked from cloud runners; The Odds API
aggregates the same books behind a stable, documented endpoint that works
from GitHub Actions.

Free tier = 500 requests/month and covers the FIFA World Cup, every major US
league, and player-prop markets. Set the ``ODDS_API_KEY`` environment variable
(a repo Actions secret) to turn it on; with no key this module is a no-op so
the rest of the pipeline keeps working on the free scrapers.

Docs: https://the-odds-api.com/liveapi/guides/v4/
"""

from __future__ import annotations

import os
from collections import defaultdict

from app.utils import get_logger, now_iso, safe_get

try:  # config is optional here; fall back to env if unavailable
    from app.config import CFG
    _DEFAULT_MAX_EVENTS = getattr(CFG, "odds_api_max_events", 8)
except Exception:  # noqa: BLE001
    _DEFAULT_MAX_EVENTS = 8

LOG = get_logger("oddsapi")
BASE = "https://api.the-odds-api.com/v4"

# Our internal sport code -> one or more Odds API sport keys. Soccer fans out
# across the live competitions, World Cup first.
SPORT_KEYS: dict[str, list[str]] = {
    "NBA": ["basketball_nba"],
    "MLB": ["baseball_mlb"],
    "NHL": ["icehockey_nhl"],
    "NFL": ["americanfootball_nfl"],
    "EPL": [
        "soccer_fifa_world_cup",
        "soccer_uefa_european_championship",
        "soccer_conmebol_copa_america",
        "soccer_epl",
        "soccer_spain_la_liga",
        "soccer_germany_bundesliga",
        "soccer_italy_serie_a",
        "soccer_france_ligue_one",
        "soccer_uefa_champs_league",
        "soccer_usa_mls",
    ],
}

# Odds API market key -> our canonical market, per sport.
MARKETS: dict[str, dict[str, str]] = {
    "NBA": {
        "player_points": "player_points", "player_rebounds": "player_rebounds",
        "player_assists": "player_assists", "player_threes": "player_threes",
        "player_blocks": "player_blocks", "player_steals": "player_steals",
        "player_points_rebounds_assists": "player_pra",
    },
    "MLB": {
        "batter_total_bases": "batter_total_bases", "batter_hits": "batter_hits",
        "batter_runs_scored": "batter_runs", "batter_rbis": "batter_rbis",
        "batter_strikeouts": "batter_strikeouts",
        "pitcher_strikeouts": "pitcher_strikeouts", "pitcher_outs": "pitcher_outs",
        "pitcher_earned_runs": "pitcher_earned_runs",
    },
    "NHL": {
        "player_points": "player_points", "player_shots_on_goal": "player_shots_on_goal",
        "player_goals": "player_goals", "player_assists": "player_assists",
        "player_total_saves": "goalie_saves",
    },
    "NFL": {
        "player_pass_yds": "player_pass_yards", "player_pass_tds": "player_pass_tds",
        "player_pass_completions": "player_pass_completions",
        "player_pass_attempts": "player_pass_attempts",
        "player_pass_interceptions": "player_interceptions",
        "player_rush_yds": "player_rush_yards", "player_rush_attempts": "player_rush_attempts",
        "player_receptions": "player_receptions", "player_reception_yds": "player_rec_yards",
    },
    "EPL": {
        "player_shots_on_target": "player_shots_on_target", "player_shots": "player_shots",
        "player_assists": "player_assists",
    },
}


def _api_key() -> str | None:
    return os.environ.get("ODDS_API_KEY") or None


def _get(url: str, params: dict):
    # Local import so tests can monkeypatch app.utils.http_get_json cleanly.
    from app.utils import http_get_json
    return http_get_json(url, params=params)


def _parse_event(sport: str, data: dict, fetched: str) -> list[dict]:
    """Collapse one event's bookmaker prop markets into prop_offers rows."""
    market_map = MARKETS.get(sport, {})
    # (book, player, canonical_market, line) -> {"over":px, "under":px}
    grouped: dict[tuple, dict[str, int]] = defaultdict(dict)
    for bm in data.get("bookmakers", []) or []:
        book = bm.get("key") or bm.get("title") or "oddsapi"
        for mk in bm.get("markets", []) or []:
            canon = market_map.get(mk.get("key"))
            if not canon:
                continue
            for oc in mk.get("outcomes", []) or []:
                name = (oc.get("name") or "").lower()
                side = "over" if name == "over" else "under" if name == "under" else None
                player = oc.get("description")
                line = oc.get("point")
                price = oc.get("price")
                if not (side and player and line is not None and price is not None):
                    continue
                try:
                    price = int(price)
                    line = float(line)
                except (TypeError, ValueError):
                    continue
                grouped[(book, player, canon, line)][side] = price

    rows: list[dict] = []
    for (book, player, canon, line), sides in grouped.items():
        rows.append({
            "fetched_at": fetched, "sport": sport, "game_id": None,
            "player_id": None, "player_name": player, "team": None,
            "market": canon, "line": line,
            "over_price": sides.get("over"), "under_price": sides.get("under"),
            "book": book,
        })
    return rows


def fetch_offers(max_events_per_sport: int | None = None) -> list[dict]:
    key = _api_key()
    if not key:
        LOG.info("oddsapi: ODDS_API_KEY not set — skipping (using free scrapers)")
        return []
    cap = max_events_per_sport or int(os.environ.get("ODDS_API_MAX_EVENTS", _DEFAULT_MAX_EVENTS))
    fetched = now_iso()
    out: list[dict] = []
    for sport, sport_keys in SPORT_KEYS.items():
        markets = ",".join(MARKETS.get(sport, {}).keys())
        if not markets:
            continue
        for sk in sport_keys:
            events = _get(f"{BASE}/sports/{sk}/events", {"apiKey": key}) or []
            if not events:
                continue
            LOG.info("oddsapi: %s/%s has %d events", sport, sk, len(events))
            for ev in events[:cap]:
                eid = ev.get("id")
                if not eid:
                    continue
                data = _get(
                    f"{BASE}/sports/{sk}/events/{eid}/odds",
                    {"apiKey": key, "regions": "us,uk,eu", "markets": markets,
                     "oddsFormat": "american"},
                )
                if not data:
                    continue
                out.extend(_parse_event(sport, data, fetched))
    LOG.info("oddsapi: parsed %d prop offers", len(out))
    return out


def remaining_quota() -> dict | None:
    """Cheap call to read how many API credits are left this month."""
    key = _api_key()
    if not key:
        return None
    from app.utils import http_get_json  # noqa: F401
    import httpx
    try:
        with httpx.Client(timeout=15) as c:
            r = c.get(f"{BASE}/sports", params={"apiKey": key})
        return {
            "used": r.headers.get("x-requests-used"),
            "remaining": r.headers.get("x-requests-remaining"),
        }
    except Exception as e:  # noqa: BLE001
        LOG.warning("oddsapi quota check failed: %s", e)
        return None
