"""Per-sport provider chain. ESPN is primary (cloud-IP-friendly); native
sources are fallbacks. Each provider exposes the same interface so callers
don't care which backend served the data."""
from __future__ import annotations

import logging
from datetime import date

from .base import SportProvider
from .espn import ESPNProvider
from .mlb import MLBProvider
from .nba import NBAProvider
from .nhl import NHLProvider
from .odds import OddsAPIClient
from .free_odds import FreeOddsAggregator

log = logging.getLogger(__name__)


class ChainedProvider(SportProvider):
    """Tries primary, falls back to secondary on empty/exception."""

    def __init__(self, sport: str, primary: SportProvider, fallback: SportProvider):
        self.sport = sport
        self._primary = primary
        self._fallback = fallback

    @property
    def supported_markets(self) -> list[str]:
        return self._primary.supported_markets or self._fallback.supported_markets

    def _try(self, method_name: str, *args, **kwargs):
        for label, prov in (("primary", self._primary), ("fallback", self._fallback)):
            try:
                rows = getattr(prov, method_name)(*args, **kwargs)
                if rows:
                    return rows
            except Exception as e:
                log.warning("%s %s.%s failed: %s", self.sport, label, method_name, e)
        return []

    def fetch_schedule(self, on: date) -> list[dict]:
        return self._try("fetch_schedule", on)

    def fetch_player_box_scores(self, on: date) -> list[dict]:
        return self._try("fetch_player_box_scores", on)

    def fetch_team_box_scores(self, on: date) -> list[dict]:
        return self._try("fetch_team_box_scores", on)

    def close(self) -> None:
        for p in (self._primary, self._fallback):
            try:
                p.close()
            except Exception:
                pass


def _make_mlb():
    return ChainedProvider("MLB", ESPNProvider("MLB"), MLBProvider())


def _make_nba():
    # ESPN first — stats.nba.com blocks Render IPs aggressively.
    return ChainedProvider("NBA", ESPNProvider("NBA"), NBAProvider())


def _make_nhl():
    return ChainedProvider("NHL", ESPNProvider("NHL"), NHLProvider())


PROVIDERS = {"MLB": _make_mlb, "NBA": _make_nba, "NHL": _make_nhl}
