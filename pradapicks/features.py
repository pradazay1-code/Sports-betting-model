"""Feature engineering: turn historical box scores into per-(player,market) features.

The same feature builder is used at training time (over historical rows) and at
inference time (build features as of the game date for an upcoming prop).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import PlayerGameStat, TeamGameStat


@dataclass
class FeatureSpec:
    sport: str
    market: str
    rolling_windows: tuple[int, ...] = (3, 5, 10, 20)


# Markets that are best modeled with a Poisson-style mean (counts), vs. ones
# that are essentially binary (e.g. home_runs > 0.5).
COUNT_MARKETS = {
    "batter_hits", "batter_total_bases", "batter_rbis", "batter_runs_scored",
    "batter_strikeouts", "pitcher_strikeouts", "pitcher_outs",
    "pitcher_earned_runs", "pitcher_hits_allowed",
    "player_points", "player_rebounds", "player_assists", "player_threes",
    "player_steals", "player_blocks", "player_turnovers",
    "player_pra", "player_pa", "player_pr", "player_ra",
    "player_shots_on_goal", "player_goals", "goalie_saves",
    "goalie_goals_against",
}


def _player_history_df(db: Session, sport: str, player_external_id: str, before: date) -> pd.DataFrame:
    rows = (
        db.execute(
            select(PlayerGameStat)
            .where(PlayerGameStat.sport == sport)
            .where(PlayerGameStat.player_external_id == player_external_id)
            .where(PlayerGameStat.game_date < before)
            .order_by(PlayerGameStat.game_date.desc())
            .limit(40)
        )
        .scalars()
        .all()
    )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([
        {
            "game_date": r.game_date,
            "team": r.team,
            "opponent": r.opponent,
            "is_home": r.is_home,
            **(r.stats or {}),
        }
        for r in rows
    ]).sort_values("game_date")
    return df


def _team_def_df(db: Session, sport: str, team: str, before: date, days: int = 30) -> pd.DataFrame:
    cutoff = before - timedelta(days=days)
    rows = (
        db.execute(
            select(TeamGameStat)
            .where(TeamGameStat.sport == sport)
            .where(TeamGameStat.opponent == team)  # rows where this team was the opponent
            .where(TeamGameStat.game_date < before)
            .where(TeamGameStat.game_date >= cutoff)
        )
        .scalars()
        .all()
    )
    return pd.DataFrame([{"game_date": r.game_date, **(r.stats or {})} for r in rows])


def build_features_for_target(
    db: Session,
    sport: str,
    market: str,
    player_external_id: str,
    game_date: date,
    opponent: str | None = None,
    is_home: bool | None = None,
    line: float | None = None,
) -> dict[str, float]:
    """Build a single feature vector (as a dict)."""
    hist = _player_history_df(db, sport, player_external_id, game_date)
    feats: dict[str, float] = {
        "line": float(line) if line is not None else 0.0,
        "is_home": 1.0 if is_home else 0.0,
        "n_history": float(len(hist)),
    }

    col = market if market in (hist.columns if not hist.empty else []) else None

    for w in (3, 5, 10, 20):
        if col is not None and len(hist) >= 1:
            window = hist[col].tail(w).astype(float)
            feats[f"mean_{w}"] = float(np.nanmean(window)) if len(window) else 0.0
            feats[f"std_{w}"] = float(np.nanstd(window)) if len(window) else 0.0
            feats[f"hit_rate_{w}"] = (
                float((window > (line or 0)).mean()) if line is not None and len(window) else 0.5
            )
        else:
            feats[f"mean_{w}"] = 0.0
            feats[f"std_{w}"] = 0.0
            feats[f"hit_rate_{w}"] = 0.5

    # Opponent defensive context (allowed values vs this team).
    if opponent:
        opp = _team_def_df(db, sport, opponent, game_date)
        if not opp.empty:
            for stat in ("def_rating", "pace", "team_era", "team_whip", "sog"):
                if stat in opp.columns:
                    feats[f"opp_{stat}"] = float(np.nanmean(opp[stat].astype(float)))

    # Recent usage / minutes signals (NBA-style; harmless zeros for other sports).
    if not hist.empty:
        for col_name in ("player_minutes", "usage_rate", "at_bats", "player_toi"):
            if col_name in hist.columns:
                feats[f"recent_{col_name}"] = float(np.nanmean(hist[col_name].tail(5).astype(float)))

    # Days of rest.
    if not hist.empty:
        last = hist["game_date"].iloc[-1]
        feats["days_rest"] = float((game_date - last).days)
    else:
        feats["days_rest"] = 3.0

    # Replace NaNs.
    for k, v in list(feats.items()):
        if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
            feats[k] = 0.0
    return feats


def build_training_frame(
    db: Session, sport: str, market: str
) -> tuple[pd.DataFrame, pd.Series]:
    """Build (X, y) over all historical player-games where `market` is observed."""
    rows = (
        db.execute(
            select(PlayerGameStat)
            .where(PlayerGameStat.sport == sport)
            .order_by(PlayerGameStat.game_date.asc())
        )
        .scalars()
        .all()
    )
    X_rows: list[dict] = []
    y_vals: list[float] = []
    for r in rows:
        stats = r.stats or {}
        if market not in stats or stats[market] is None:
            continue
        feats = build_features_for_target(
            db,
            sport=sport,
            market=market,
            player_external_id=r.player_external_id,
            game_date=r.game_date,
            opponent=r.opponent,
            is_home=r.is_home,
            line=None,
        )
        X_rows.append(feats)
        y_vals.append(float(stats[market]))
    if not X_rows:
        return pd.DataFrame(), pd.Series(dtype=float)
    X = pd.DataFrame(X_rows).fillna(0.0)
    y = pd.Series(y_vals, name=market)
    return X, y
