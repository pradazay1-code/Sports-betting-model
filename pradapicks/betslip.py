"""Bet-slip analyzer.

Input: a list of legs, each with sport, player_name, market, line, side, price.
Output: per-leg model_prob/edge/rating + combined parlay metrics + 0..100 rating
for the slip overall.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable

from sqlalchemy.orm import Session

from .db import BetSlip
from .features import build_features_for_target
from .models.trainer import load_active_model
from .picks import _resolve_player
from .scoring import rating_from_components
from .utils import (
    american_to_decimal,
    american_to_implied,
    decimal_to_american,
    edge_pct,
)


def analyze_slip(
    db: Session,
    legs: list[dict],
    book: str | None = None,
    on: date | None = None,
    submitted_by: str | None = None,
    persist: bool = True,
) -> dict:
    on = on or date.today()
    leg_results: list[dict] = []
    combined_prob = 1.0
    combined_decimal = 1.0
    combined_implied = 1.0

    for leg in legs:
        sport = leg["sport"].upper()
        market = leg["market"]
        line = float(leg["line"])
        side = leg["side"].lower()
        price = int(leg["price_american"])
        player_name = leg["player_name"]

        player = _resolve_player(db, sport, player_name)
        model = load_active_model(db, sport, market)

        if model and player:
            feats = build_features_for_target(
                db, sport=sport, market=market,
                player_external_id=player.external_id, game_date=on,
                opponent=leg.get("opponent"), is_home=leg.get("is_home"), line=line,
            )
            p_over, mu = model.predict_over_prob(feats, line)
            p_side = p_over if side.startswith("over") else 1.0 - p_over
            sample = model.metrics.n
        else:
            # fallback: use vig-laden implied prob (no edge, conservative)
            p_side = american_to_implied(price)
            mu = line
            sample = 0

        ed = edge_pct(p_side, price)
        rating, breakdown = rating_from_components(
            model_prob=p_side,
            price_american=price,
            fair_prob=None,
            sample_size=sample,
            market_consensus_count=1,
        )

        combined_prob *= p_side
        combined_decimal *= american_to_decimal(price)
        combined_implied *= american_to_implied(price)

        leg_results.append({
            "sport": sport,
            "player_name": player_name,
            "market": market,
            "line": line,
            "side": side,
            "price_american": price,
            "model_prob": round(p_side, 4),
            "implied_prob": round(american_to_implied(price), 4),
            "edge_pct": round(ed, 3),
            "rating": rating,
            "predicted_value": round(mu, 3),
            "rationale": breakdown,
        })

    parlay_edge = (combined_prob * (combined_decimal - 1.0) - (1.0 - combined_prob)) * 100.0
    parlay_american = decimal_to_american(combined_decimal)
    rating, breakdown = rating_from_components(
        model_prob=combined_prob,
        price_american=parlay_american,
        fair_prob=None,
        sample_size=min((l.get("rationale", {}).get("sample_size") or 0) for l in leg_results) if leg_results else 0,
        market_consensus_count=1,
    )

    result = {
        "book": book,
        "legs": leg_results,
        "combined_decimal_odds": round(combined_decimal, 3),
        "combined_american_odds": parlay_american,
        "combined_model_prob": round(combined_prob, 4),
        "combined_implied_prob": round(combined_implied, 4),
        "combined_edge_pct": round(parlay_edge, 3),
        "rating": rating,
        "rating_breakdown": breakdown,
        "verdict": _verdict(rating, parlay_edge),
    }

    if persist:
        db.add(BetSlip(
            submitted_by=submitted_by,
            book=book,
            legs=leg_results,
            combined_odds_american=parlay_american,
            combined_prob=float(combined_prob),
            implied_prob=float(combined_implied),
            edge_pct=float(parlay_edge),
            rating=float(rating),
            notes={"verdict": result["verdict"]},
        ))
        db.commit()

    return result


def _verdict(rating: float, edge_pct_val: float) -> str:
    if rating >= 80 and edge_pct_val >= 8:
        return "ELITE — strong, place"
    if rating >= 65 and edge_pct_val >= 4:
        return "STRONG — value present"
    if rating >= 50:
        return "NEUTRAL — marginal"
    return "PASS — negative or weak EV"
