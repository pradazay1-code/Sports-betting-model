"""Game-level predictions: each team's projected score, total, spread, P(home win).

Approach is intentionally simple and transparent:
  - For each team build rolling averages of points_for and points_against
    (per-game) over the last 10 and 25 games.
  - Predicted score for a team in a matchup =
        0.5 * (team's last-25 pf  + opp's last-25 pa)
    with a home-court adjustment per sport.
  - Total = sum of the two predicted scores.
  - Spread (home - away).
  - P(home win) from a Normal CDF using the score standard deviation as noise.

It's a baseline — easy to improve later by replacing the closed-form formula
with a small LightGBM regressor over the team rolling stats. Until then it's
honest and fast.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm

from app.store import connection
from app.sources import parks
from app.utils import get_logger

LOG = get_logger("game_model")

# Per-sport homecourt edge in points (home minus away, baseline).
HOME_EDGE = {"NBA": 2.4, "MLB": 0.15, "NHL": 0.20}

# Per-sport game-score standard deviation used to convert spread to win prob.
GAME_STD = {"NBA": 12.0, "MLB": 3.8, "NHL": 2.4}


@dataclass
class GamePrediction:
    sport: str
    game_id: str
    home_team: str
    away_team: str
    pred_home_score: float
    pred_away_score: float
    pred_total: float
    pred_spread: float
    home_win_prob: float
    rationale: dict


def _team_history(sport: str) -> pd.DataFrame:
    with connection() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM team_game_stats WHERE sport=? ORDER BY game_date", (sport,)
        ).fetchall()]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df["points_for"] = pd.to_numeric(df["points_for"], errors="coerce")
    df["points_against"] = pd.to_numeric(df["points_against"], errors="coerce")
    return df.dropna(subset=["points_for", "points_against"]).sort_values(["team", "game_date"]).reset_index(drop=True)


def _rolling_mean(df: pd.DataFrame, col: str, window: int) -> pd.Series:
    return df.groupby("team", group_keys=False)[col].apply(lambda s: s.shift(1).rolling(window, min_periods=3).mean())


def _team_form(df: pd.DataFrame) -> dict[str, dict]:
    """Latest rolling-25 (pf, pa) per team."""
    if df.empty:
        return {}
    df = df.copy()
    df["pf25"] = _rolling_mean(df, "points_for", 25)
    df["pa25"] = _rolling_mean(df, "points_against", 25)
    out: dict[str, dict] = {}
    for team, g in df.groupby("team"):
        last = g.dropna(subset=["pf25", "pa25"]).tail(1)
        if last.empty:
            continue
        out[team] = {
            "pf25": float(last["pf25"].iloc[0]),
            "pa25": float(last["pa25"].iloc[0]),
        }
    return out


def predict_tennis(games: list[dict]) -> list[GamePrediction]:
    """Match-level total-games projection.

    Baseline expected total games by match format (best-of-3 ≈ 22, best-of-5 ≈
    37), nudged by how lopsided the matchup looks. When the book's total is
    later attached (via The Odds API) this projection is what we price against.
    """
    out: list[GamePrediction] = []
    for g in games:
        home, away = g.get("home_team"), g.get("away_team")
        if not home or not away:
            continue
        try:
            extra = json.loads(g.get("extra") or "{}")
        except Exception:
            extra = {}
        best_of = int(extra.get("best_of", 3))
        base = 37.5 if best_of == 5 else 22.5
        # Competitiveness prior: default even. If live/partial scores exist we
        # keep it simple and leave the base; hooks for ranking gaps go here.
        total = base
        per_side = total / 2.0
        out.append(GamePrediction(
            sport="TEN", game_id=g["game_id"], home_team=home, away_team=away,
            pred_home_score=round(per_side, 1), pred_away_score=round(per_side, 1),
            pred_total=round(total, 1), pred_spread=0.0, home_win_prob=0.5,
            rationale={"best_of": best_of, "basis": "format baseline",
                       "note": "total games projection (v1)"},
        ))
    return out


def predict_for_games(sport: str, games: list[dict]) -> list[GamePrediction]:
    if sport == "TEN":
        return predict_tennis(games)
    df = _team_history(sport)
    form = _team_form(df)
    if not form:
        return []
    home_edge = HOME_EDGE.get(sport, 0.0)
    sigma = GAME_STD.get(sport, 4.0)
    out: list[GamePrediction] = []
    for g in games:
        home = g.get("home_team")
        away = g.get("away_team")
        if not home or not away:
            continue
        h = form.get(home)
        a = form.get(away)
        if not h or not a:
            continue
        ph = 0.5 * (h["pf25"] + a["pa25"]) + home_edge / 2
        pa = 0.5 * (a["pf25"] + h["pa25"]) - home_edge / 2
        # MLB park factor multiplier (applies to expected runs scored).
        if sport == "MLB":
            pk = parks.factor_for(g.get("venue"))
            ph *= pk
            pa *= pk
        total = ph + pa
        spread = ph - pa
        win_prob = float(norm.cdf(spread / sigma))
        out.append(GamePrediction(
            sport=sport, game_id=g["game_id"],
            home_team=home, away_team=away,
            pred_home_score=round(ph, 2),
            pred_away_score=round(pa, 2),
            pred_total=round(total, 2),
            pred_spread=round(spread, 2),
            home_win_prob=round(win_prob, 4),
            rationale={
                "home_form": h, "away_form": a,
                "home_edge": home_edge, "sigma": sigma,
                "park_factor": parks.factor_for(g.get("venue")) if sport == "MLB" else None,
            },
        ))
    return out
