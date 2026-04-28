"""Free odds + prop providers — no API key required.

Two unofficial public sources are aggregated:

  1) PrizePicks  -> https://api.prizepicks.com/projections
     Public JSON of current player projections (lines). PrizePicks payouts are
     fixed (single-pick = even-money, multi-pick parlays scale), so we attach a
     synthetic standard price of -119 per side to make the rating engine work.

  2) DraftKings  -> https://sportsbook-nash.draftkings.com/sites/US-SB/api/v5/eventgroups/{id}
     Public sportsbook JSON. We walk offer categories / subcategories looking
     for player-prop markets and normalize to our schema.

Both endpoints are unofficial and can change without notice. Each provider is
wrapped in try/except so a failure in one source does not block the other.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import Iterable

from .base import HTTPProvider

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PrizePicks
# ---------------------------------------------------------------------------

# Map PrizePicks `stat_type` strings to our internal market keys.
PP_STAT_MAP = {
    # NBA
    "Points": "player_points",
    "Rebounds": "player_rebounds",
    "Assists": "player_assists",
    "3-PT Made": "player_threes",
    "Pts+Rebs+Asts": "player_pra",
    "Pts+Asts": "player_pa",
    "Pts+Rebs": "player_pr",
    "Rebs+Asts": "player_ra",
    "Steals": "player_steals",
    "Blocks": "player_blocks",
    "Turnovers": "player_turnovers",
    # MLB
    "Hits": "batter_hits",
    "Total Bases": "batter_total_bases",
    "Home Runs": "batter_home_runs",
    "RBIs": "batter_rbis",
    "Runs": "batter_runs_scored",
    "Hitter Strikeouts": "batter_strikeouts",
    "Pitcher Strikeouts": "pitcher_strikeouts",
    "Pitcher Outs": "pitcher_outs",
    "Earned Runs Allowed": "pitcher_earned_runs",
    "Hits Allowed": "pitcher_hits_allowed",
    # NHL
    "Shots On Goal": "player_shots_on_goal",
    "Goals": "player_goals",
    "Points (NHL)": "player_points",  # disambiguated by league
    "Saves": "goalie_saves",
}

PP_LEAGUE_TO_SPORT = {
    "MLB": "MLB",
    "NBA": "NBA",
    "NHL": "NHL",
    "WNBA": None,
    "NFL": None,
}


class PrizePicksProvider(HTTPProvider):
    base_url = "https://api.prizepicks.com"
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 Pradapicks/0.1",
    }

    def fetch(self, sports: Iterable[str]) -> list[dict]:
        try:
            data = self._get("/projections", params={"per_page": 1000, "single_stat": "true"})
        except Exception as e:
            log.warning("prizepicks fetch failed: %s", e)
            return []

        included = {(i["type"], i["id"]): i for i in (data.get("included") or [])}
        rows: list[dict] = []
        wanted = set(sports)
        for proj in data.get("data") or []:
            attrs = proj.get("attributes") or {}
            rels = proj.get("relationships") or {}
            league_id = ((rels.get("league") or {}).get("data") or {}).get("id")
            league = (included.get(("league", league_id)) or {}).get("attributes", {}).get("name")
            sport = PP_LEAGUE_TO_SPORT.get(league)
            if not sport or sport not in wanted:
                continue

            stat_type = attrs.get("stat_type")
            market = PP_STAT_MAP.get(stat_type)
            if not market:
                continue

            player_id = ((rels.get("new_player") or {}).get("data") or {}).get("id")
            player = (included.get(("new_player", player_id)) or {}).get("attributes", {})
            player_name = player.get("name") or attrs.get("description")
            team = player.get("team")

            line = attrs.get("line_score")
            if line is None:
                continue

            game_date_iso = (attrs.get("start_time") or "")[:10]
            external_id = f"pp:{proj.get('id')}"

            for side, price in (("over", -119), ("under", -119)):
                rows.append({
                    "sport": sport,
                    "game_external_id": external_id,
                    "game_date": game_date_iso,
                    "player_name": player_name,
                    "team": team,
                    "market": market,
                    "line": float(line),
                    "side": side,
                    "price_american": price,
                    "book": "prizepicks",
                })
        return rows


# ---------------------------------------------------------------------------
# DraftKings
# ---------------------------------------------------------------------------

DK_EVENT_GROUPS = {
    "MLB": 84240,
    "NBA": 42648,
    "NHL": 42133,
}

# Map DK subcategory names (case-insensitive contains) to internal markets.
# Order matters — the first matching key wins.
DK_SUBCAT_MAP_NBA = [
    ("points + rebounds + assists", "player_pra"),
    ("points + assists", "player_pa"),
    ("points + rebounds", "player_pr"),
    ("rebounds + assists", "player_ra"),
    ("threes made", "player_threes"),
    ("3-pointers made", "player_threes"),
    ("points", "player_points"),
    ("rebounds", "player_rebounds"),
    ("assists", "player_assists"),
    ("steals", "player_steals"),
    ("blocks", "player_blocks"),
    ("turnovers", "player_turnovers"),
]

DK_SUBCAT_MAP_MLB = [
    ("total bases", "batter_total_bases"),
    ("home runs", "batter_home_runs"),
    ("hits", "batter_hits"),
    ("rbis", "batter_rbis"),
    ("runs scored", "batter_runs_scored"),
    ("strikeouts thrown", "pitcher_strikeouts"),
    ("strikeouts", "batter_strikeouts"),
    ("outs recorded", "pitcher_outs"),
    ("earned runs", "pitcher_earned_runs"),
    ("hits allowed", "pitcher_hits_allowed"),
]

DK_SUBCAT_MAP_NHL = [
    ("shots on goal", "player_shots_on_goal"),
    ("points", "player_points"),
    ("goals", "player_goals"),
    ("assists", "player_assists"),
    ("saves", "goalie_saves"),
    ("goals against", "goalie_goals_against"),
]

DK_MAP_BY_SPORT = {"NBA": DK_SUBCAT_MAP_NBA, "MLB": DK_SUBCAT_MAP_MLB, "NHL": DK_SUBCAT_MAP_NHL}


class DraftKingsProvider(HTTPProvider):
    base_url = "https://sportsbook-nash.draftkings.com"
    headers = {
        "Accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
    }

    def fetch(self, sports: Iterable[str]) -> list[dict]:
        rows: list[dict] = []
        for sport in sports:
            eg = DK_EVENT_GROUPS.get(sport)
            if not eg:
                continue
            try:
                rows.extend(self._fetch_sport(sport, eg))
            except Exception as e:
                log.warning("draftkings fetch failed %s: %s", sport, e)
        return rows

    def _fetch_sport(self, sport: str, event_group_id: int) -> list[dict]:
        # Discover offer categories.
        eg = self._get(
            f"/sites/US-SB/api/v5/eventgroups/{event_group_id}",
            params={"format": "json"},
        )
        out: list[dict] = []
        events_by_id = {
            str(e.get("eventId")): e
            for e in (eg.get("eventGroup", {}).get("events") or [])
        }
        cats = (eg.get("eventGroup", {}).get("offerCategories") or [])
        market_map = DK_MAP_BY_SPORT.get(sport, [])

        # The categories returned by the eventgroup root may not include
        # subcategory descriptors with offers — those require a second call.
        for cat in cats:
            cat_id = cat.get("offerCategoryId")
            descriptors = (cat.get("offerSubcategoryDescriptors") or [])
            for desc in descriptors:
                sub_id = desc.get("subcategoryId")
                sub_name = (desc.get("name") or "").lower()
                market = self._match_market(sub_name, market_map)
                if not market:
                    continue
                try:
                    sub = self._get(
                        f"/sites/US-SB/api/v5/eventgroups/{event_group_id}/"
                        f"categories/{cat_id}/subcategories/{sub_id}",
                        params={"format": "json"},
                    )
                except Exception:
                    continue
                offers = (
                    (sub.get("eventGroup", {}).get("offerCategories") or [{}])[0]
                    .get("offerSubcategoryDescriptors", [{}])[0]
                    .get("offerSubcategory", {})
                    .get("offers", [])
                )
                for offer_group in offers:
                    for offer in offer_group:
                        evt = events_by_id.get(str(offer.get("eventId"))) or {}
                        outcomes = offer.get("outcomes") or []
                        for o in outcomes:
                            label = (o.get("label") or "").lower()
                            side = "over" if "over" in label else "under" if "under" in label else None
                            if side is None:
                                continue
                            line = o.get("line")
                            if line is None:
                                continue
                            price = o.get("oddsAmerican")
                            try:
                                price = int(str(price).replace("−", "-"))
                            except (TypeError, ValueError):
                                continue
                            player_name = (
                                o.get("participant")
                                or o.get("name")
                                or _strip_side(o.get("label"))
                            )
                            out.append({
                                "sport": sport,
                                "game_external_id": f"dk:{offer.get('eventId')}",
                                "game_date": (evt.get("startDate") or "")[:10],
                                "player_name": player_name,
                                "team": None,
                                "market": market,
                                "line": float(line),
                                "side": side,
                                "price_american": price,
                                "book": "draftkings",
                            })
        return out

    @staticmethod
    def _match_market(name: str, market_map: list[tuple[str, str]]) -> str | None:
        for needle, market in market_map:
            if needle in name:
                return market
        return None


def _strip_side(label: str | None) -> str:
    if not label:
        return ""
    return re.sub(r"\b(over|under)\b\s*\d+(\.\d+)?", "", label, flags=re.IGNORECASE).strip()


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


class FreeOddsAggregator:
    """Combines all free providers. Use as a drop-in OddsAPIClient replacement."""

    def __init__(self) -> None:
        self.pp = PrizePicksProvider()
        self.dk = DraftKingsProvider()

    def fetch_all(self, sports: Iterable[str], on: date | None = None) -> list[dict]:
        sports = list(sports)
        rows: list[dict] = []
        rows.extend(self.pp.fetch(sports))
        rows.extend(self.dk.fetch(sports))

        if on:
            iso = on.isoformat()
            rows = [r for r in rows if (r.get("game_date") or "")[:10] in (iso, "")]
        return rows

    def close(self) -> None:
        self.pp.close()
        self.dk.close()
