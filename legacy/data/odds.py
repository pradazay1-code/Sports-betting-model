"""Player-prop odds via The Odds API (https://the-odds-api.com).

The free tier covers core markets; player-prop markets require a paid plan but
the request shape is identical, so a key with prop access drops in.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Iterable

from ..config import get_settings
from .base import HTTPProvider

log = logging.getLogger(__name__)

SPORT_KEY = {
    "MLB": "baseball_mlb",
    "NBA": "basketball_nba",
    "NHL": "icehockey_nhl",
}

# Player-prop markets per sport on The Odds API. Adjust if your plan exposes more.
PROP_MARKETS = {
    "MLB": [
        "batter_hits", "batter_total_bases", "batter_home_runs", "batter_rbis",
        "batter_runs_scored", "batter_strikeouts",
        "pitcher_strikeouts", "pitcher_outs", "pitcher_earned_runs", "pitcher_hits_allowed",
    ],
    "NBA": [
        "player_points", "player_rebounds", "player_assists", "player_threes",
        "player_steals", "player_blocks", "player_turnovers",
        "player_points_rebounds_assists", "player_points_assists",
        "player_points_rebounds", "player_rebounds_assists",
    ],
    "NHL": [
        "player_shots_on_goal", "player_points", "player_goals", "player_assists",
        "player_total_saves", "player_goals_against",
    ],
}

# Map Odds-API market names to our internal market keys.
INTERNAL_MARKET = {
    "player_points_rebounds_assists": "player_pra",
    "player_points_assists": "player_pa",
    "player_points_rebounds": "player_pr",
    "player_rebounds_assists": "player_ra",
    "player_total_saves": "goalie_saves",
    "player_goals_against": "goalie_goals_against",
}


class OddsAPIClient(HTTPProvider):
    base_url = "https://api.the-odds-api.com"

    def __init__(self) -> None:
        super().__init__()
        self._key = get_settings().odds_api_key
        self._regions = get_settings().odds_regions
        self._books = set(get_settings().odds_books)

    def list_events(self, sport: str, on: date | None = None) -> list[dict]:
        if not self._key:
            return []
        sk = SPORT_KEY[sport]
        events = self._get(f"/v4/sports/{sk}/events", params={"apiKey": self._key})
        if on:
            events = [e for e in events if (e.get("commence_time", ""))[:10] == on.isoformat()]
        return events

    def fetch_props(self, sport: str, on: date | None = None) -> list[dict]:
        """Return normalized prop offers for a sport on a given date."""
        if not self._key:
            log.warning("ODDS_API_KEY not set — skipping odds fetch for %s", sport)
            return []
        sk = SPORT_KEY[sport]
        markets = ",".join(PROP_MARKETS[sport])
        out: list[dict] = []
        for ev in self.list_events(sport, on):
            event_id = ev.get("id")
            try:
                data = self._get(
                    f"/v4/sports/{sk}/events/{event_id}/odds",
                    params={
                        "apiKey": self._key,
                        "regions": self._regions,
                        "markets": markets,
                        "oddsFormat": "american",
                    },
                )
            except Exception as e:
                log.warning("odds fetch failed for %s/%s: %s", sport, event_id, e)
                continue
            for bm in data.get("bookmakers", []) or []:
                book = bm.get("key")
                if self._books and book not in self._books:
                    continue
                for m in bm.get("markets", []) or []:
                    market_key = m.get("key")
                    internal = INTERNAL_MARKET.get(market_key, market_key)
                    for o in m.get("outcomes", []) or []:
                        out.append({
                            "sport": sport,
                            "game_external_id": event_id,
                            "game_date": (data.get("commence_time", "") or "")[:10],
                            "player_name": o.get("description") or o.get("name"),
                            "team": None,
                            "market": internal,
                            "line": float(o.get("point") or 0.0),
                            "side": (o.get("name") or "").lower(),  # "Over" / "Under"
                            "price_american": int(o.get("price") or 0),
                            "book": book,
                            "home_team": data.get("home_team"),
                            "away_team": data.get("away_team"),
                        })
        return out

    def fetch_all(self, sports: Iterable[str], on: date | None = None) -> list[dict]:
        results: list[dict] = []
        for s in sports:
            results.extend(self.fetch_props(s, on))
        return results
