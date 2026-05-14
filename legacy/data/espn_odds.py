"""ESPN game odds extractor.

ESPN's scoreboard response embeds odds inside `competitions[0].odds[]` —
moneyline, spread, total. We already hit this endpoint for box scores so
this adds zero new HTTP load. Returns offers in the same internal shape
as the player-prop providers but for game-level markets.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Iterable

from .base import HTTPProvider

log = logging.getLogger(__name__)

ESPN_PATH = {
    "MLB": "baseball/mlb",
    "NBA": "basketball/nba",
    "NHL": "hockey/nhl",
}


class ESPNOddsProvider(HTTPProvider):
    """Game-level odds (h2h / spread / total) from ESPN's scoreboard."""

    base_url = "https://site.api.espn.com"
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 Pradapicks/0.1",
    }

    def fetch(self, sports: Iterable[str], on: date | None = None) -> list[dict]:
        out: list[dict] = []
        for sport in sports:
            path = ESPN_PATH.get(sport)
            if not path:
                continue
            params = {}
            if on:
                params["dates"] = on.strftime("%Y%m%d")
            try:
                data = self._get(f"/apis/site/v2/sports/{path}/scoreboard", params=params)
            except Exception as e:
                log.warning("espn_odds %s failed: %s", sport, e)
                continue
            for ev in data.get("events") or []:
                comps = (ev.get("competitions") or [{}])[0]
                competitors = comps.get("competitors") or []
                home = away = None
                for c in competitors:
                    name = (c.get("team") or {}).get("displayName")
                    if c.get("homeAway") == "home":
                        home = name
                    else:
                        away = name
                gd = (ev.get("date") or "")[:10]
                gid = str(ev.get("id"))

                for o in comps.get("odds") or []:
                    book = (o.get("provider") or {}).get("name") or "espn"
                    book_norm = _normalize_book(book)

                    # h2h / moneyline
                    home_ml = (o.get("homeTeamOdds") or {}).get("moneyLine")
                    away_ml = (o.get("awayTeamOdds") or {}).get("moneyLine")
                    if home_ml is not None:
                        out.append(_offer(sport, gid, gd, home, "moneyline", 0,
                                          "home", int(home_ml), book_norm, home, away))
                    if away_ml is not None:
                        out.append(_offer(sport, gid, gd, away, "moneyline", 0,
                                          "away", int(away_ml), book_norm, home, away))

                    # spread
                    spread = o.get("spread")
                    if spread is not None:
                        # ESPN gives a single signed spread for the favorite.
                        # We synthesize a -110/-110 line (spread market is
                        # rarely far off from -110 in posted odds).
                        try:
                            sp = float(spread)
                            out.append(_offer(sport, gid, gd, home, "spread", sp,
                                              "home", -110, book_norm, home, away))
                            out.append(_offer(sport, gid, gd, away, "spread", -sp,
                                              "away", -110, book_norm, home, away))
                        except (ValueError, TypeError):
                            pass

                    # total
                    ou = o.get("overUnder")
                    if ou is not None:
                        try:
                            t = float(ou)
                            out.append(_offer(sport, gid, gd, "total", "total", t,
                                              "over", -110, book_norm, home, away))
                            out.append(_offer(sport, gid, gd, "total", "total", t,
                                              "under", -110, book_norm, home, away))
                        except (ValueError, TypeError):
                            pass
        if out:
            log.info("espn_odds: %d offers", len(out))
        return out


def _offer(sport, gid, gd, player_or_team, market, line, side, price, book, home, away):
    return {
        "sport": sport,
        "game_external_id": f"espn:{gid}",
        "game_date": gd,
        "player_name": player_or_team,
        "team": None,
        "market": market,
        "line": float(line),
        "side": side,
        "price_american": int(price),
        "book": book,
        "home_team": home,
        "away_team": away,
    }


def _normalize_book(name: str) -> str:
    n = (name or "").lower()
    for k in ("draftkings", "fanduel", "betmgm", "caesars", "espnbet", "espn",
             "pointsbet", "bet365", "consensus"):
        if k in n:
            return k
    return n or "espn"
