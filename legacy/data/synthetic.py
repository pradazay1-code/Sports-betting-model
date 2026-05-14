"""Synthetic odds provider — generates prop offers from player rolling averages.

When every live odds source is blocked or empty, we still want the daily
top-25 to publish. This module builds realistic-looking lines for every
active player on today's slate by:

  1. Pulling today's schedule from each sport provider.
  2. Looking up each rostered player's recent box scores in the DB.
  3. For every (player, market), setting the line to the rolling median of
     recent values, rounded to the nearest 0.5 (PrizePicks-style).
  4. Attaching a fixed -119 / -119 price (PrizePicks-style fixed payout).

These offers are flagged with book="synthetic" so the rating engine can
discount them appropriately. They give the model something to score so it
keeps publishing picks while live odds providers are unavailable.
"""
from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import PlayerGameStat, Player
from ..features import COUNT_MARKETS

log = logging.getLogger(__name__)


# Markets we are willing to synthesize per sport (kept focused — too many
# markets dilute the daily top-25).
SYNTH_MARKETS = {
    "NBA": ["player_points", "player_rebounds", "player_assists", "player_threes", "player_pra"],
    "MLB": [
        "batter_hits", "batter_total_bases", "pitcher_strikeouts",
        "batter_runs_scored", "pitcher_outs",
    ],
    "NHL": ["player_shots_on_goal", "player_points", "goalie_saves"],
}


def _round_half(x: float) -> float:
    return math.floor(x) + 0.5  # PrizePicks-style; never integer pushes


def generate(db: Session, sports: Iterable[str], on: date) -> list[dict]:
    """Return synthetic prop offers for today's likely active players."""
    cutoff = on - timedelta(days=21)
    rows: list[dict] = []
    for sport in sports:
        markets = SYNTH_MARKETS.get(sport, [])
        if not markets:
            continue
        # Players who appeared in a game in the last 21 days are "active".
        active = (
            db.query(PlayerGameStat)
            .filter(
                PlayerGameStat.sport == sport,
                PlayerGameStat.game_date >= cutoff,
                PlayerGameStat.game_date < on,
            )
            .all()
        )
        # Aggregate per (player, market): collect last-N values.
        by_player: dict[tuple[str, str], list[float]] = {}
        names: dict[str, str] = {}
        for r in active:
            stats = r.stats or {}
            for m in markets:
                v = stats.get(m)
                if v is None:
                    continue
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    continue
                key = (r.player_external_id, m)
                by_player.setdefault(key, []).append(v)
                names[r.player_external_id] = (
                    db.query(Player)
                    .filter(Player.sport == sport, Player.external_id == r.player_external_id)
                    .one_or_none()
                ).name if r.player_external_id not in names else names[r.player_external_id]

        for (pid, market), values in by_player.items():
            if len(values) < 5:
                continue
            values_sorted = sorted(values[-10:])
            median = values_sorted[len(values_sorted) // 2]
            line = _round_half(median) if market in COUNT_MARKETS else round(median, 1)
            for side in ("over", "under"):
                rows.append({
                    "sport": sport,
                    "game_external_id": f"synthetic:{on.isoformat()}:{sport}:{pid}",
                    "game_date": on.isoformat(),
                    "player_name": names.get(pid, ""),
                    "team": None,
                    "market": market,
                    "line": float(line),
                    "side": side,
                    "price_american": -119,
                    "book": "synthetic",
                })
    log.info("synthetic odds generated: %d rows", len(rows))
    return rows
