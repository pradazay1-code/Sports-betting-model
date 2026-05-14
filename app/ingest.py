"""Pull schedules + box scores into SQLite.

This is the only place that mutates games/players/player_game_stats; the
modelling code reads from those tables only.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from app.config import CFG
from app.sources import injuries as injuries_src
from app.sources import lineups as lineups_src
from app.sources import mlb, nba, nhl
from app.sources import weather as weather_src
from app.store import (
    upsert_games,
    upsert_injury,
    upsert_lineup,
    upsert_players,
    upsert_player_game_stats,
    upsert_weather,
)
from app.utils import get_logger

LOG = get_logger("ingest")

SPORT_MODULES = {"NBA": nba, "MLB": mlb, "NHL": nhl}


def ingest_date(on: date) -> dict:
    out: dict[str, int] = {}
    for sport, mod in SPORT_MODULES.items():
        try:
            games = mod.fetch_schedule(on)
            n_games = upsert_games(games)
            stats, players = mod.fetch_box_scores(on)
            n_players = upsert_players(players)
            n_stats = upsert_player_game_stats(stats)
            out[sport] = n_stats
            LOG.info("ingest %s %s: games=%d players=%d stats=%d",
                     sport, on, n_games, n_players, n_stats)
        except Exception as e:  # noqa: BLE001
            LOG.warning("ingest %s %s failed: %s", sport, on, e)
            out[sport] = 0
    return out


def ingest_today_context(on: date) -> dict:
    """Fetch the day-of context: injuries, MLB lineups, MLB weather."""
    out: dict[str, int] = {}
    try:
        inj = injuries_src.fetch_all()
        out["injuries"] = upsert_injury(inj)
    except Exception as e:  # noqa: BLE001
        LOG.warning("injuries failed: %s", e)
        out["injuries"] = 0

    try:
        lineup_rows = lineups_src.fetch_all(on)
        out["lineups"] = upsert_lineup(lineup_rows)
    except Exception as e:  # noqa: BLE001
        LOG.warning("lineups failed: %s", e)
        out["lineups"] = 0

    # Weather for MLB games on this date.
    wx_count = 0
    try:
        for g in mlb.fetch_schedule(on):
            if not g.get("venue"):
                continue
            wx = weather_src.forecast_for(g["game_id"], g["venue"], g.get("start_utc"))
            if wx:
                upsert_weather(wx)
                wx_count += 1
    except Exception as e:  # noqa: BLE001
        LOG.warning("weather failed: %s", e)
    out["weather"] = wx_count
    return out


def backfill(days: int = None) -> dict[str, int]:
    days = days or CFG.backfill_days
    total: dict[str, int] = {"NBA": 0, "MLB": 0, "NHL": 0}
    end = date.today()
    start = end - timedelta(days=days)
    d = start
    while d <= end:
        per_day = ingest_date(d)
        for k, v in per_day.items():
            total[k] = total.get(k, 0) + v
        d += timedelta(days=1)
    LOG.info("backfill %d days: %s", days, total)
    return total
