"""Multi-source free odds layer with provider-health tracking and synthetic fallback.

Providers are tried in priority order. Each provider's success/failure is
tracked in PROVIDER_HEALTH so /health can show which sources are alive.

Providers (free, no API key required):
  1. ActionNetwork — aggregates DK/FD/MGM/Caesars player props. Cloud-friendly.
  2. Pinnacle (guest API) — sharp lines + props. Cloud-friendly with X-API-Key.
  3. Bovada — public coupon JSON. Mostly cloud-friendly.
  4. PrizePicks — fixed-payout projections. Often blocks cloud IPs.
  5. DraftKings — public sportsbook JSON. Often blocks cloud IPs.

If every live source fails or returns nothing, the SyntheticOddsProvider
generates lines from each player's recent rolling averages so picks still
publish (with the understanding that synthetic lines have no real edge —
they exist so the system stays usable while live sources are down).
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

from .base import HTTPProvider

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider health (module-level, simple)
# ---------------------------------------------------------------------------


@dataclass
class ProviderState:
    name: str
    last_success: float = 0.0
    last_failure: float = 0.0
    last_error: str = ""
    last_offer_count: int = 0


PROVIDER_HEALTH: dict[str, ProviderState] = {}


def _record_success(name: str, count: int) -> None:
    s = PROVIDER_HEALTH.setdefault(name, ProviderState(name=name))
    s.last_success = time.time()
    s.last_offer_count = count
    s.last_error = ""


def _record_failure(name: str, err: Exception) -> None:
    s = PROVIDER_HEALTH.setdefault(name, ProviderState(name=name))
    s.last_failure = time.time()
    s.last_error = f"{type(err).__name__}: {err}"
    log.warning("%s fetch failed: %s", name, err)


def health_snapshot() -> dict:
    out = {}
    for name, s in PROVIDER_HEALTH.items():
        out[name] = {
            "last_success_ts": s.last_success,
            "last_failure_ts": s.last_failure,
            "last_offer_count": s.last_offer_count,
            "last_error": s.last_error,
            "alive": s.last_success > s.last_failure,
        }
    return out


# ---------------------------------------------------------------------------
# Shared market mappings
# ---------------------------------------------------------------------------

# Generic market-name normalization. Keys are lowercased substrings; first
# match wins. Used by every provider.
MARKET_PATTERNS_NBA = [
    ("points + rebounds + assists", "player_pra"),
    ("pts+rebs+asts", "player_pra"),
    ("points + assists", "player_pa"),
    ("pts+asts", "player_pa"),
    ("points + rebounds", "player_pr"),
    ("pts+rebs", "player_pr"),
    ("rebounds + assists", "player_ra"),
    ("rebs+asts", "player_ra"),
    ("3-pt made", "player_threes"),
    ("threes made", "player_threes"),
    ("3-pointers", "player_threes"),
    ("points", "player_points"),
    ("rebounds", "player_rebounds"),
    ("assists", "player_assists"),
    ("steals", "player_steals"),
    ("blocks", "player_blocks"),
    ("turnovers", "player_turnovers"),
]
MARKET_PATTERNS_MLB = [
    ("total bases", "batter_total_bases"),
    ("home runs", "batter_home_runs"),
    ("rbis", "batter_rbis"),
    ("runs scored", "batter_runs_scored"),
    ("strikeouts thrown", "pitcher_strikeouts"),
    ("pitcher strikeouts", "pitcher_strikeouts"),
    ("hitter strikeouts", "batter_strikeouts"),
    ("strikeouts", "batter_strikeouts"),
    ("outs recorded", "pitcher_outs"),
    ("earned runs", "pitcher_earned_runs"),
    ("hits allowed", "pitcher_hits_allowed"),
    ("hits", "batter_hits"),
]
MARKET_PATTERNS_NHL = [
    ("shots on goal", "player_shots_on_goal"),
    ("saves", "goalie_saves"),
    ("goals against", "goalie_goals_against"),
    ("points", "player_points"),
    ("goals", "player_goals"),
    ("assists", "player_assists"),
]
MARKET_PATTERNS = {"NBA": MARKET_PATTERNS_NBA, "MLB": MARKET_PATTERNS_MLB, "NHL": MARKET_PATTERNS_NHL}


def map_market(sport: str, name: str) -> str | None:
    if not name:
        return None
    n = name.lower()
    for needle, market in MARKET_PATTERNS.get(sport, []):
        if needle in n:
            return market
    return None


# ---------------------------------------------------------------------------
# Action Network
# ---------------------------------------------------------------------------

AN_LEAGUE = {"NBA": "nba", "MLB": "mlb", "NHL": "nhl"}


class ActionNetworkProvider(HTTPProvider):
    base_url = "https://api.actionnetwork.com"
    headers = {
        "Accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Referer": "https://www.actionnetwork.com/",
    }

    def fetch(self, sports: Iterable[str]) -> list[dict]:
        rows: list[dict] = []
        for sport in sports:
            league = AN_LEAGUE.get(sport)
            if not league:
                continue
            try:
                data = self._get(
                    f"/web/v1/scoreboard/{league}",
                    params={"bookIds": "15,30,75,123,69,68,972,71,247,79"},
                )
                games = data.get("games") or []
                for g in games:
                    rows.extend(self._fetch_game_props(sport, league, g))
            except Exception as e:
                _record_failure("actionnetwork", e)
                return rows
        _record_success("actionnetwork", len(rows))
        return rows

    def _fetch_game_props(self, sport: str, league: str, game: dict) -> list[dict]:
        gid = game.get("id")
        if not gid:
            return []
        out: list[dict] = []
        # Action Network's v2/games/{id}/props endpoint returns 400 — the
        # current working path is per-league props by core_bet_type.
        # Try multiple known patterns; first one that returns data wins.
        candidates = [
            (f"/web/v1/leagues/{league}/props/core_bet_type_27_player_points", {}),
            (f"/web/v2/scoreboard/publicbetting/{league}", {"gameId": str(gid)}),
            (f"/web/v1/games/{gid}/polls", {}),
        ]
        data = None
        for path, params in candidates:
            try:
                data = self._get(path, params=params)
                if data:
                    break
            except Exception:
                continue
        if not data:
            return []

        teams = game.get("teams") or []
        home_team = away_team = None
        for t in teams:
            if t.get("id") == game.get("home_team_id"):
                home_team = t.get("display_name") or t.get("full_name")
            elif t.get("id") == game.get("away_team_id"):
                away_team = t.get("display_name") or t.get("full_name")
        start = game.get("start_time") or ""
        gd = start[:10] if start else ""

        markets = data.get("markets") or {}
        if isinstance(markets, dict):
            market_iter = markets.items()
        else:
            market_iter = enumerate(markets or [])

        for _, blob in market_iter:
            props = blob if isinstance(blob, list) else (blob.get("props") or blob.get("offers") or [])
            for prop in props or []:
                player_name = (
                    (prop.get("player") or {}).get("full_name")
                    or prop.get("player_name")
                    or (prop.get("participant") or {}).get("name")
                )
                market_name = (
                    prop.get("market_name")
                    or prop.get("name")
                    or prop.get("type")
                    or ""
                )
                market = map_market(sport, market_name)
                if not market or not player_name:
                    continue
                line = prop.get("value") or prop.get("line")
                if line is None:
                    options = prop.get("options") or prop.get("outcomes") or []
                    if options:
                        line = options[0].get("value") or options[0].get("line")
                if line is None:
                    continue
                outcomes = prop.get("options") or prop.get("outcomes") or []
                for o in outcomes:
                    label = (o.get("type") or o.get("name") or o.get("label") or "").lower()
                    side = "over" if "over" in label else "under" if "under" in label else None
                    if side is None:
                        continue
                    price = o.get("odds") or o.get("price") or o.get("american")
                    try:
                        price = int(price)
                    except (TypeError, ValueError):
                        continue
                    out.append({
                        "sport": sport,
                        "game_external_id": f"an:{gid}",
                        "game_date": gd,
                        "player_name": player_name,
                        "team": None,
                        "market": market,
                        "line": float(line),
                        "side": side,
                        "price_american": price,
                        "book": "actionnetwork",
                        "home_team": home_team,
                        "away_team": away_team,
                    })
        return out


# ---------------------------------------------------------------------------
# Pinnacle
# ---------------------------------------------------------------------------

PIN_LEAGUE = {"MLB": 246, "NBA": 487, "NHL": 1456}
PIN_GUEST_KEY = "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R"  # public guest key, stable


class PinnacleProvider(HTTPProvider):
    """Pinnacle guest API.

    Pinnacle's matchups response contains BOTH parent matchups (type="matchup")
    and prop "specials" (type="special") in the same list. Specials have a
    `parentId` and a `special.description` describing the prop, plus
    participants that include the player name. To get prices, hit
    /markets/related/straight on the special's id.
    """
    base_url = "https://guest.api.arcadia.pinnacle.com"
    headers = {
        "Accept": "application/json",
        "X-API-Key": PIN_GUEST_KEY,
        "Referer": "https://www.pinnacle.com/",
        "User-Agent": "Mozilla/5.0 Pradapicks/0.1",
    }

    def fetch(self, sports: Iterable[str]) -> list[dict]:
        rows: list[dict] = []
        for sport in sports:
            lid = PIN_LEAGUE.get(sport)
            if not lid:
                continue
            try:
                matchups = self._get(
                    f"/0.1/leagues/{lid}/matchups", params={"brandId": "0"}
                )
                if not isinstance(matchups, list):
                    continue
            except Exception as e:
                _record_failure("pinnacle", e)
                return rows

            # Build a quick parent lookup so specials know which game they belong to.
            parents = {m.get("id"): m for m in matchups if m.get("type") == "matchup"}
            specials = [m for m in matchups if m.get("type") == "special"]

            # Cap calls per league to avoid hammering.
            for special in specials[:120]:
                rows.extend(self._fetch_special_prices(sport, special, parents))
        if rows:
            _record_success("pinnacle", len(rows))
        return rows

    def _fetch_special_prices(self, sport: str, special: dict, parents: dict) -> list[dict]:
        sid = special.get("id")
        if not sid:
            return []
        sp = special.get("special") or {}
        description = sp.get("description") or ""
        category = (sp.get("category") or "").lower()
        # The category often tells us the market: "Total Points (Player)", etc.
        market = map_market(sport, category) or map_market(sport, description)
        if not market:
            return []

        # Find the player name from participants whose name is NOT "Over/Under".
        player_name = None
        for p in special.get("participants") or []:
            n = (p.get("name") or "").strip()
            if n and n.lower() not in ("over", "under"):
                player_name = n
                break
        if not player_name:
            # Fallback: parse description like "LeBron James (Total Points)"
            if "(" in description:
                player_name = description.split("(")[0].strip()
        if not player_name:
            return []

        # Parent game info
        parent = parents.get(special.get("parentId")) or {}
        gd = (parent.get("startTime") or special.get("startTime") or "")[:10]
        home = away = None
        for p in parent.get("participants") or []:
            if p.get("alignment") == "home":
                home = p.get("name")
            elif p.get("alignment") == "away":
                away = p.get("name")

        try:
            markets = self._get(f"/0.1/matchups/{sid}/markets/related/straight")
        except Exception:
            return []
        if not isinstance(markets, list):
            return []

        out: list[dict] = []
        for mk in markets:
            for pr in mk.get("prices") or []:
                designation = (pr.get("designation") or "").lower()
                side = "over" if designation == "over" else "under" if designation == "under" else None
                if side is None:
                    continue
                line = pr.get("points")
                if line is None:
                    line = sp.get("points")
                price = pr.get("price")
                try:
                    price = int(price)
                except (TypeError, ValueError):
                    continue
                if line is None:
                    continue
                out.append({
                    "sport": sport,
                    "game_external_id": f"pin:{special.get('parentId') or sid}",
                    "game_date": gd,
                    "player_name": player_name,
                    "team": None,
                    "market": market,
                    "line": float(line),
                    "side": side,
                    "price_american": price,
                    "book": "pinnacle",
                    "home_team": home,
                    "away_team": away,
                })
        return out


# ---------------------------------------------------------------------------
# Bovada
# ---------------------------------------------------------------------------

BOVADA_PATH = {
    "MLB": "/services/sports/event/coupon/events/A/description/baseball/mlb",
    "NBA": "/services/sports/event/coupon/events/A/description/basketball/nba",
    "NHL": "/services/sports/event/coupon/events/A/description/hockey/nhl",
}


class BovadaProvider(HTTPProvider):
    base_url = "https://www.bovada.lv"
    headers = {
        "Accept": "application/json",
        "Referer": "https://www.bovada.lv/",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
    }

    def fetch(self, sports: Iterable[str]) -> list[dict]:
        rows: list[dict] = []
        for sport in sports:
            path = BOVADA_PATH.get(sport)
            if not path:
                continue
            try:
                data = self._get(path, params={"marketFilterId": "def", "lang": "en"})
            except Exception as e:
                _record_failure("bovada", e)
                continue
            # Bovada returns a list of "groups", each containing "events" or "paths".
            events = []
            stack = list(data) if isinstance(data, list) else [data]
            while stack:
                node = stack.pop()
                if isinstance(node, dict):
                    if isinstance(node.get("events"), list):
                        events.extend(node["events"])
                    if isinstance(node.get("children"), list):
                        stack.extend(node["children"])
                elif isinstance(node, list):
                    stack.extend(node)
            for ev in events:
                gd_raw = ev.get("startTime") or 0
                try:
                    from datetime import datetime
                    gd_iso = datetime.utcfromtimestamp(int(gd_raw) / 1000).date().isoformat() if gd_raw else ""
                except Exception:
                    gd_iso = ""
                home_team = away_team = None
                for c in ev.get("competitors") or []:
                    if c.get("home"):
                        home_team = c.get("name")
                    else:
                        away_team = c.get("name")
                for dg in ev.get("displayGroups") or []:
                    for mk in dg.get("markets") or []:
                        desc = (mk.get("description") or "")
                        market = map_market(sport, desc)
                        if not market:
                            continue
                        # Player name often lives in the market description: "LeBron James - Total Points"
                        player_from_desc = None
                        if " - " in desc:
                            player_from_desc = desc.split(" - ")[0].strip()
                        for o in mk.get("outcomes") or []:
                            player_name = (
                                (o.get("competitor") or "").strip()
                                or player_from_desc
                                or (o.get("description") or "").strip()
                            )
                            price_obj = o.get("price") or {}
                            line = price_obj.get("handicap")
                            am = price_obj.get("american")
                            if am in (None, "", "EVEN"):
                                am = "100"
                            try:
                                price = int(str(am).replace("EVEN", "100").replace("+", ""))
                            except (TypeError, ValueError):
                                continue
                            side_label = (o.get("description") or "").lower()
                            side = "over" if "over" in side_label else "under" if "under" in side_label else None
                            if side is None or line is None:
                                continue
                            rows.append({
                                "sport": sport,
                                "game_external_id": f"bov:{ev.get('id')}",
                                "game_date": gd_iso,
                                "player_name": player_name,
                                "team": None,
                                "market": market,
                                "line": float(line),
                                "side": side,
                                "price_american": price,
                                "book": "bovada",
                                "home_team": home_team,
                                "away_team": away_team,
                            })
        if rows:
            _record_success("bovada", len(rows))
        return rows


# ---------------------------------------------------------------------------
# PrizePicks (often blocked from cloud IPs — kept as bonus source)
# ---------------------------------------------------------------------------

PP_STAT_MAP = {
    "Points": "player_points", "Rebounds": "player_rebounds", "Assists": "player_assists",
    "3-PT Made": "player_threes", "Pts+Rebs+Asts": "player_pra", "Pts+Asts": "player_pa",
    "Pts+Rebs": "player_pr", "Rebs+Asts": "player_ra", "Steals": "player_steals",
    "Blocks": "player_blocks", "Turnovers": "player_turnovers",
    "Hits": "batter_hits", "Total Bases": "batter_total_bases",
    "Home Runs": "batter_home_runs", "RBIs": "batter_rbis", "Runs": "batter_runs_scored",
    "Hitter Strikeouts": "batter_strikeouts", "Pitcher Strikeouts": "pitcher_strikeouts",
    "Pitcher Outs": "pitcher_outs", "Earned Runs Allowed": "pitcher_earned_runs",
    "Hits Allowed": "pitcher_hits_allowed",
    "Shots On Goal": "player_shots_on_goal", "Goals": "player_goals", "Saves": "goalie_saves",
}
PP_LEAGUE_TO_SPORT = {"MLB": "MLB", "NBA": "NBA", "NHL": "NHL"}


class PrizePicksProvider(HTTPProvider):
    base_url = "https://api.prizepicks.com"
    headers = {
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://app.prizepicks.com",
        "Referer": "https://app.prizepicks.com/",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
    }

    def fetch(self, sports: Iterable[str]) -> list[dict]:
        try:
            data = self._get("/projections", params={"per_page": 1000, "single_stat": "true"})
        except Exception as e:
            _record_failure("prizepicks", e)
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
            line = attrs.get("line_score")
            if line is None or not player_name:
                continue
            game_date_iso = (attrs.get("start_time") or "")[:10]
            external_id = f"pp:{proj.get('id')}"
            for side, price in (("over", -119), ("under", -119)):
                rows.append({
                    "sport": sport,
                    "game_external_id": external_id,
                    "game_date": game_date_iso,
                    "player_name": player_name,
                    "team": player.get("team"),
                    "market": market,
                    "line": float(line),
                    "side": side,
                    "price_american": price,
                    "book": "prizepicks",
                })
        if rows:
            _record_success("prizepicks", len(rows))
        return rows


# ---------------------------------------------------------------------------
# DraftKings (often blocked from cloud IPs)
# ---------------------------------------------------------------------------

DK_EVENT_GROUPS = {"MLB": 84240, "NBA": 42648, "NHL": 42133}


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
                data = self._get(
                    f"/sites/US-SB/api/v5/eventgroups/{eg}",
                    params={"format": "json"},
                )
            except Exception as e:
                _record_failure("draftkings", e)
                continue
            cats = (data.get("eventGroup", {}).get("offerCategories") or [])
            events_by_id = {
                str(e.get("eventId")): e
                for e in (data.get("eventGroup", {}).get("events") or [])
            }
            for cat in cats:
                cat_id = cat.get("offerCategoryId")
                for desc in cat.get("offerSubcategoryDescriptors") or []:
                    sub_id = desc.get("subcategoryId")
                    sub_name = (desc.get("name") or "")
                    market = map_market(sport, sub_name)
                    if not market:
                        continue
                    try:
                        sub = self._get(
                            f"/sites/US-SB/api/v5/eventgroups/{eg}/categories/{cat_id}/subcategories/{sub_id}",
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
                            for o in offer.get("outcomes") or []:
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
                                    or _strip_side(o.get("label"))
                                )
                                rows.append({
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
        if rows:
            _record_success("draftkings", len(rows))
        return rows


def _strip_side(label: str | None) -> str:
    if not label:
        return ""
    return re.sub(r"\b(over|under)\b\s*\d+(\.\d+)?", "", label, flags=re.IGNORECASE).strip()


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


class FreeOddsAggregator:
    """Tries every free provider in priority order, accumulates all rows."""

    def __init__(self) -> None:
        from .espn_odds import ESPNOddsProvider
        self.providers = [
            ("espn_odds", ESPNOddsProvider()),
            ("pinnacle", PinnacleProvider()),
            ("bovada", BovadaProvider()),
            ("actionnetwork", ActionNetworkProvider()),
            ("prizepicks", PrizePicksProvider()),
            ("draftkings", DraftKingsProvider()),
        ]

    def fetch_all(self, sports: Iterable[str], on: date | None = None) -> list[dict]:
        sports = list(sports)
        rows: list[dict] = []
        for name, prov in self.providers:
            try:
                got = prov.fetch(sports)
            except Exception as e:
                _record_failure(name, e)
                got = []
            log.info("free_odds.%s: %d offers", name, len(got))
            rows.extend(got)
        if on:
            iso = on.isoformat()
            rows = [r for r in rows if (r.get("game_date") or "")[:10] in (iso, "")]
        return rows

    def close(self) -> None:
        for _, p in self.providers:
            try:
                p.close()
            except Exception:
                pass
