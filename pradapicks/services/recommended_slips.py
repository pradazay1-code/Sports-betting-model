"""Auto-generated recommended bet slips for the day.

Curates 5 ready-to-place tickets from the daily picks pool:
  1. Safe Single — single highest-rated leg
  2. 3-Leg High Confidence — 3 legs with rating >= 65, edge >= 3%
  3. 5-Leg Lottery — 5 highest-rated picks for higher payout
  4. ML Lock — biggest game-prediction favorite
  5. SGP Stack — 2 same-game legs with positive correlation

Stored in the picks JSON as a synthetic Pick row family or returned
on-demand. We compute these on demand from current picks + game preds
so the user always sees fresh slips after every refresh cycle.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy.orm import Session

from ..db import Pick, GamePrediction
from ..services.correlation import adjusted_parlay_prob
from ..utils import (
    american_to_decimal, american_to_implied, decimal_to_american,
    edge_pct, kelly_fraction,
)


def _pick_to_leg(p: Pick) -> dict:
    return {
        "sport": p.sport,
        "player_name": p.player_name,
        "team": p.team,
        "opponent": p.opponent,
        "market": p.market,
        "line": p.line,
        "side": p.side,
        "price_american": p.price_american,
        "model_prob": p.model_prob,
        "implied_prob": p.implied_prob,
        "edge_pct": p.edge_pct,
        "rating": p.rating,
        "book": p.book,
        "game_external_id": p.game_external_id,
    }


def _slip_summary(legs: list[dict], label: str, blurb: str) -> dict:
    if not legs:
        return None
    indep, adj, corr_notes = adjusted_parlay_prob(legs)
    combined_dec = 1.0
    combined_implied = 1.0
    for l in legs:
        combined_dec *= american_to_decimal(int(l["price_american"]))
        combined_implied *= american_to_implied(int(l["price_american"]))
    parlay_american = decimal_to_american(combined_dec)
    parlay_edge = (adj * (combined_dec - 1.0) - (1.0 - adj)) * 100.0
    avg_rating = sum(l.get("rating", 0) for l in legs) / max(1, len(legs))
    kelly = kelly_fraction(adj, parlay_american, 0.25)
    return {
        "label": label,
        "blurb": blurb,
        "n_legs": len(legs),
        "legs": legs,
        "combined_decimal_odds": round(combined_dec, 3),
        "combined_american_odds": parlay_american,
        "combined_model_prob": round(adj, 4),
        "combined_implied_prob": round(combined_implied, 4),
        "edge_pct": round(parlay_edge, 3),
        "avg_rating": round(avg_rating, 1),
        "correlation_notes": corr_notes,
        "kelly_fraction": round(kelly, 4),
    }


def generate_recommended_slips(db: Session, on: date | None = None) -> list[dict]:
    on = on or date.today()
    picks = (
        db.query(Pick)
        .filter(Pick.pick_date == on)
        .order_by(Pick.rating.desc())
        .all()
    )
    out: list[dict] = []
    if not picks:
        return out

    # 1. Safe Single
    s1 = _slip_summary(
        [_pick_to_leg(picks[0])],
        "Safe Single",
        "Highest-rated single play — lowest variance.",
    )
    if s1: out.append(s1)

    # 2. 3-Leg High Confidence
    high_conf = [p for p in picks if p.rating >= 65 and p.edge_pct >= 3]
    if len(high_conf) >= 3:
        s2 = _slip_summary(
            [_pick_to_leg(p) for p in high_conf[:3]],
            "3-Leg High Confidence",
            "Three top-rated legs, every one a clear edge.",
        )
        if s2: out.append(s2)

    # 3. 5-Leg Lottery
    if len(picks) >= 5:
        s3 = _slip_summary(
            [_pick_to_leg(p) for p in picks[:5]],
            "5-Leg Lottery",
            "Five highest-rated legs — bigger payout, more variance.",
        )
        if s3: out.append(s3)

    # 4. ML Lock from game predictions
    preds = (
        db.query(GamePrediction)
        .filter(GamePrediction.game_date == on)
        .all()
    )
    if preds:
        preds.sort(key=lambda g: max(g.home_win_prob, 1 - g.home_win_prob), reverse=True)
        g = preds[0]
        is_home_fav = g.home_win_prob > 0.5
        fav = g.home_team if is_home_fav else g.away_team
        fav_prob = g.home_win_prob if is_home_fav else 1.0 - g.home_win_prob
        synthetic_price = -150
        ml_leg = {
            "sport": g.sport,
            "player_name": fav,
            "team": fav,
            "opponent": g.away_team if is_home_fav else g.home_team,
            "market": "moneyline",
            "line": 0,
            "side": "win",
            "price_american": synthetic_price,
            "model_prob": round(fav_prob, 4),
            "implied_prob": round(american_to_implied(synthetic_price), 4),
            "edge_pct": round(edge_pct(fav_prob, synthetic_price), 3),
            "rating": round(fav_prob * 100, 1),
            "book": "model",
            "game_external_id": g.game_external_id,
        }
        s4 = _slip_summary(
            [ml_leg],
            "ML Lock",
            f"Biggest game-prediction favorite: {fav} at {fav_prob*100:.0f}% to win.",
        )
        if s4: out.append(s4)

    # 5. SGP Stack — find a game with 2+ picks and bundle them
    by_game: dict[str, list[Pick]] = defaultdict(list)
    for p in picks:
        if p.game_external_id:
            by_game[(p.sport, p.game_external_id)].append(p)
    for (sport, gid), group in by_game.items():
        if len(group) >= 2:
            sgp_legs = [_pick_to_leg(p) for p in group[:3]]
            s5 = _slip_summary(
                sgp_legs,
                "Same-Game Stack",
                f"Multiple high-rated legs from one game — correlation-adjusted.",
            )
            if s5:
                out.append(s5)
                break

    return out
