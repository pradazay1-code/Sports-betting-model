"""Game-level prediction model.

For each upcoming game, predict:
  - home_score, away_score (expected values)
  - total = home + away
  - spread = home - away
  - home_win_prob via Monte Carlo simulation

Approach (free-data-only, robust to missing data):
  1. Compute rolling team offensive rating (points scored / pace) and
     defensive rating (points allowed / pace) over the last 20 games.
  2. Predict each team's score = (team_off + opp_def) / 2 with home-court
     adjustment.
  3. Estimate score variance per team from historical residuals.
  4. Run 5,000 Monte Carlo samples drawing from N(mu, sigma) per team to
     get win probability + total/spread distributions.

This isn't going to beat closing lines on its own, but it gives a
calibrated probability we can use to compute edge vs the posted market.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from statistics import mean, pstdev
from typing import Iterable

import numpy as np
from sqlalchemy.orm import Session

from ..db import GamePrediction, Game, TeamGameStat, PlayerGameStat

log = logging.getLogger(__name__)

# Per-sport scoring stat keys used to build offense/defense ratings.
SCORE_KEYS = {
    "MLB": ["runs"],
    "NBA": ["pts", "points", "off_rating"],
    "NHL": ["score"],
}

HOME_ADVANTAGE = {"MLB": 0.15, "NBA": 2.5, "NHL": 0.20}
DEFAULT_LEAGUE_AVG = {"MLB": 4.5, "NBA": 113.0, "NHL": 3.1}
SCORE_STD = {"MLB": 3.0, "NBA": 12.0, "NHL": 1.6}


def _team_score_history(db: Session, sport: str, team: str, before: date, n: int = 20) -> tuple[list[float], list[float]]:
    """Return (scored_for, scored_against) lists for the team's recent games."""
    rows = (
        db.query(TeamGameStat)
        .filter(
            TeamGameStat.sport == sport,
            TeamGameStat.team == team,
            TeamGameStat.game_date < before,
        )
        .order_by(TeamGameStat.game_date.desc())
        .limit(n)
        .all()
    )
    scored_for: list[float] = []
    scored_against: list[float] = []
    for r in rows:
        s = r.stats or {}
        for k in SCORE_KEYS.get(sport, []):
            if k in s and s[k] is not None:
                try:
                    scored_for.append(float(s[k]))
                except (TypeError, ValueError):
                    pass
                break
        # Look up the opponent's row in the same game to get points-against.
        opp_row = (
            db.query(TeamGameStat)
            .filter(
                TeamGameStat.sport == sport,
                TeamGameStat.game_external_id == r.game_external_id,
                TeamGameStat.team == r.opponent,
            )
            .one_or_none()
        )
        if opp_row:
            opp_stats = opp_row.stats or {}
            for k in SCORE_KEYS.get(sport, []):
                if k in opp_stats and opp_stats[k] is not None:
                    try:
                        scored_against.append(float(opp_stats[k]))
                    except (TypeError, ValueError):
                        pass
                    break
    return scored_for, scored_against


def _team_score_history_from_player_rows(db: Session, sport: str, team: str, before: date, n: int = 20):
    """Fallback when team-level rows are sparse: aggregate player scores."""
    if sport != "NBA":
        return [], []
    rows = (
        db.query(PlayerGameStat)
        .filter(
            PlayerGameStat.sport == sport,
            PlayerGameStat.team == team,
            PlayerGameStat.game_date < before,
        )
        .order_by(PlayerGameStat.game_date.desc())
        .limit(n * 15)
        .all()
    )
    by_game: dict[str, dict[str, float]] = {}
    for r in rows:
        g = by_game.setdefault(r.game_external_id, {"for": 0.0, "opp": r.opponent or ""})
        v = (r.stats or {}).get("player_points")
        try:
            g["for"] += float(v) if v is not None else 0
        except (TypeError, ValueError):
            pass
    scored_for = [g["for"] for g in by_game.values() if g["for"] > 0]
    return scored_for[:n], []


def _team_avg_for_against(
    db: Session, sport: str, team: str, before: date
) -> tuple[float, float]:
    sf, sa = _team_score_history(db, sport, team, before)
    if len(sf) < 3:
        sf2, sa2 = _team_score_history_from_player_rows(db, sport, team, before)
        sf = sf2 if sf2 else sf
    league_avg = DEFAULT_LEAGUE_AVG[sport]
    avg_for = mean(sf) if sf else league_avg
    avg_against = mean(sa) if sa else league_avg
    return avg_for, avg_against


def predict_game(
    db: Session, sport: str, home_team: str, away_team: str, game_date: date,
    n_simulations: int = 5000,
) -> dict:
    """Return a dict with score predictions, ML prob, and confidence."""
    home_for, home_against = _team_avg_for_against(db, sport, home_team, game_date)
    away_for, away_against = _team_avg_for_against(db, sport, away_team, game_date)
    league_avg = DEFAULT_LEAGUE_AVG[sport]

    # Project each team's score: blend their offense with opponent's defense.
    home_proj = (home_for + away_against) / 2.0 + HOME_ADVANTAGE[sport]
    away_proj = (away_for + home_against) / 2.0

    sigma = SCORE_STD[sport]

    # Monte Carlo simulation
    rng = np.random.default_rng(42)
    home_samples = rng.normal(home_proj, sigma, size=n_simulations)
    away_samples = rng.normal(away_proj, sigma, size=n_simulations)
    if sport in ("MLB", "NHL"):
        home_samples = np.maximum(0, np.round(home_samples))
        away_samples = np.maximum(0, np.round(away_samples))
    home_win_prob = float(np.mean(home_samples > away_samples))
    push_prob = float(np.mean(home_samples == away_samples))
    # Adjust for ties (MLB has very few; NBA effectively zero)
    if push_prob > 0:
        home_win_prob += push_prob / 2.0

    totals = home_samples + away_samples
    spreads = home_samples - away_samples

    # Confidence: how decisive is the model?
    confidence = float(min(1.0, abs(home_win_prob - 0.5) * 2 + 0.1))

    return {
        "sport": sport,
        "home_team": home_team,
        "away_team": away_team,
        "game_date": game_date.isoformat(),
        "pred_home_score": round(float(np.mean(home_samples)), 2),
        "pred_away_score": round(float(np.mean(away_samples)), 2),
        "pred_total": round(float(np.mean(totals)), 2),
        "pred_spread": round(float(np.mean(spreads)), 2),
        "home_win_prob": round(home_win_prob, 4),
        "away_win_prob": round(1.0 - home_win_prob, 4),
        "confidence": round(confidence, 3),
        "score_distribution": {
            "home_p10": float(np.percentile(home_samples, 10)),
            "home_p90": float(np.percentile(home_samples, 90)),
            "away_p10": float(np.percentile(away_samples, 10)),
            "away_p90": float(np.percentile(away_samples, 90)),
            "total_p10": float(np.percentile(totals, 10)),
            "total_p90": float(np.percentile(totals, 90)),
        },
        "rationale": {
            "home_avg_for": round(home_for, 2),
            "home_avg_against": round(home_against, 2),
            "away_avg_for": round(away_for, 2),
            "away_avg_against": round(away_against, 2),
            "league_avg": league_avg,
            "home_advantage": HOME_ADVANTAGE[sport],
        },
    }


def generate_game_predictions(db: Session, on: date | None = None) -> list[GamePrediction]:
    on = on or date.today()
    games = (
        db.query(Game)
        .filter(Game.game_date == on)
        .all()
    )
    if not games:
        log.info("game_model: no games on %s", on)
        return []

    out: list[GamePrediction] = []
    for g in games:
        try:
            pred = predict_game(db, g.sport, g.home_team, g.away_team, on)
        except Exception:
            log.exception("game_model: failed for %s/%s", g.sport, g.external_id)
            continue
        existing = (
            db.query(GamePrediction)
            .filter(
                GamePrediction.sport == g.sport,
                GamePrediction.game_external_id == g.external_id,
            )
            .one_or_none()
        )
        if existing:
            existing.pred_home_score = pred["pred_home_score"]
            existing.pred_away_score = pred["pred_away_score"]
            existing.pred_total = pred["pred_total"]
            existing.pred_spread = pred["pred_spread"]
            existing.home_win_prob = pred["home_win_prob"]
            existing.confidence = pred["confidence"]
            existing.rationale = pred["rationale"]
            out.append(existing)
        else:
            obj = GamePrediction(
                sport=g.sport,
                game_external_id=g.external_id,
                game_date=on,
                home_team=g.home_team,
                away_team=g.away_team,
                pred_home_score=pred["pred_home_score"],
                pred_away_score=pred["pred_away_score"],
                pred_total=pred["pred_total"],
                pred_spread=pred["pred_spread"],
                home_win_prob=pred["home_win_prob"],
                confidence=pred["confidence"],
                rationale=pred["rationale"],
            )
            db.add(obj)
            out.append(obj)
    db.commit()
    log.info("game_model: predicted %d games", len(out))
    return out
