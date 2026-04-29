"""Defensive matchup ratings — for each (sport, market), rank teams by
how much of the stat they allow opponents (last 30 days)."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import mean

from sqlalchemy.orm import Session

from ..db import PlayerGameStat


# Markets to rank for matchup difficulty per sport.
RANKED_MARKETS = {
    "NBA": ["player_points", "player_rebounds", "player_assists", "player_threes"],
    "MLB": ["batter_hits", "batter_total_bases", "pitcher_strikeouts"],
    "NHL": ["player_shots_on_goal", "player_points", "goalie_saves"],
}


def defensive_rankings(db: Session, sport: str, days: int = 30) -> dict[str, list[dict]]:
    """Returns per-market list of {team, allowed_avg, rank} sorted hardest-to-easiest."""
    cutoff = date.today() - timedelta(days=days)
    rows = (
        db.query(PlayerGameStat)
        .filter(
            PlayerGameStat.sport == sport,
            PlayerGameStat.game_date >= cutoff,
        )
        .all()
    )
    out: dict[str, list[dict]] = {}
    for market in RANKED_MARKETS.get(sport, []):
        # For each opponent team, average the player stat allowed.
        bucket: dict[str, list[float]] = defaultdict(list)
        for r in rows:
            v = (r.stats or {}).get(market)
            if v is None:
                continue
            try:
                bucket[r.opponent].append(float(v))
            except (TypeError, ValueError):
                continue
        ranked = [
            {"team": team, "allowed_avg": round(mean(vals), 2), "n": len(vals)}
            for team, vals in bucket.items()
            if len(vals) >= 5
        ]
        ranked.sort(key=lambda x: -x["allowed_avg"])
        for i, item in enumerate(ranked, 1):
            item["rank"] = i  # 1 = most allowed (worst defense for that stat)
        out[market] = ranked
    return out


def matchup_for_team(db: Session, sport: str, team: str, days: int = 30) -> dict:
    rankings = defensive_rankings(db, sport, days=days)
    out: dict[str, dict] = {}
    for market, ranked in rankings.items():
        for r in ranked:
            if r["team"] and team and r["team"].lower() == team.lower():
                out[market] = {
                    "rank": r["rank"],
                    "of": len(ranked),
                    "allowed_avg": r["allowed_avg"],
                }
                break
    return out
