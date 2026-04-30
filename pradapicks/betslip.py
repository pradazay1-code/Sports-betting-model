"""Bet-slip analyzer V3 — rich, actionable output.

For each leg returns:
  - model_prob, predicted_value, confidence
  - implied_prob, no-vig fair_prob, edge_pct (with bootstrap CI)
  - season/L5/L10 averages, hit rate vs the line
  - opponent matchup rank
  - line shopping table (best book + alt lines)
  - per-leg Kelly stake

For the slip overall:
  - independent vs correlation-adjusted parlay probability
  - combined edge with CI
  - recommended stake (fractional Kelly)
  - verdict
  - same-game correlation notes
"""
from __future__ import annotations

import math
from datetime import date

from sqlalchemy.orm import Session

from .config import get_settings
from .db import BetSlip
from .features import build_features_for_target
from .models.trainer import load_active_model
from .picks import _resolve_player
from .scoring import rating_from_components
from .services.correlation import adjusted_parlay_prob
from .services.lineshop import best_price_table, alt_line_ladder
from .services.live_metrics import metrics_for_leg
from .utils import (
    american_to_decimal,
    american_to_implied,
    decimal_to_american,
    edge_pct,
    kelly_fraction,
)


def _bootstrap_edge_ci(model_prob: float, price_american: int, n: int = 1000, sigma: float = 0.05) -> tuple[float, float]:
    """Bootstrap a confidence interval on edge by sampling around model_prob."""
    import numpy as np
    rng = np.random.default_rng(42)
    samples = np.clip(rng.normal(model_prob, sigma, n), 0.01, 0.99)
    edges = [edge_pct(float(p), price_american) for p in samples]
    return float(np.percentile(edges, 5)), float(np.percentile(edges, 95))


def analyze_slip(
    db: Session,
    legs: list[dict],
    book: str | None = None,
    on: date | None = None,
    submitted_by: str | None = None,
    persist: bool = True,
    bankroll: float = 1000.0,
) -> dict:
    on = on or date.today()
    settings = get_settings()
    leg_results: list[dict] = []
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
            sample_size = model.metrics.n
        else:
            p_side = american_to_implied(price)  # fallback: zero edge
            mu = line
            sample_size = 0

        ed = edge_pct(p_side, price)
        edge_lo, edge_hi = _bootstrap_edge_ci(p_side, price)
        rating, breakdown = rating_from_components(
            model_prob=p_side, price_american=price, fair_prob=None,
            sample_size=sample_size, market_consensus_count=1,
        )
        kel = kelly_fraction(p_side, price, settings.kelly_fraction)
        recommended_stake = round(bankroll * kel, 2)

        # Live metrics block (recent form, hit rate, matchup).
        metrics = metrics_for_leg(
            db, sport=sport, player_name=player_name, market=market, line=line,
            side=side, price_american=price, opponent=leg.get("opponent"),
            is_home=leg.get("is_home"),
        )

        # Line shopping
        shop = best_price_table(db, sport, player_name, market, line, side)
        ladder = alt_line_ladder(db, sport, player_name, market, side)
        best_offer = shop[0] if shop else None
        price_lift = None
        if best_offer and best_offer["price_american"] != price:
            current_dec = american_to_decimal(price)
            best_dec = american_to_decimal(best_offer["price_american"])
            price_lift = round((best_dec / current_dec - 1.0) * 100.0, 2)

        # Update parlay running totals
        combined_decimal *= american_to_decimal(price)
        combined_implied *= american_to_implied(price)

        # For correlation analysis we need game_external_id on each leg.
        from .db import Game
        game_ext = None
        if player and player.team:
            g = (
                db.query(Game)
                .filter(Game.sport == sport, Game.game_date == on)
                .filter((Game.home_team == player.team) | (Game.away_team == player.team))
                .first()
            )
            if g:
                game_ext = g.external_id

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
            "edge_ci_low": round(edge_lo, 3),
            "edge_ci_high": round(edge_hi, 3),
            "rating": rating,
            "predicted_value": round(mu, 3),
            "kelly_fraction": round(kel, 4),
            "recommended_stake": recommended_stake,
            "rationale": breakdown,
            "metrics": metrics,
            "lineshop": {
                "best": best_offer,
                "all_books": shop[:6],
                "alt_lines": ladder[:8],
                "price_lift_vs_current_pct": price_lift,
            },
            "game_external_id": game_ext,
        })

    # --- parlay-level analysis ---
    indep_prob, adj_prob, corr_notes = adjusted_parlay_prob(leg_results)
    parlay_edge_indep = (indep_prob * (combined_decimal - 1.0) - (1.0 - indep_prob)) * 100.0
    parlay_edge_adj = (adj_prob * (combined_decimal - 1.0) - (1.0 - adj_prob)) * 100.0
    parlay_american = decimal_to_american(combined_decimal)

    rating, breakdown = rating_from_components(
        model_prob=adj_prob,
        price_american=parlay_american,
        fair_prob=None,
        sample_size=min((l.get("rationale", {}).get("sample_size") or 0) for l in leg_results) if leg_results else 0,
        market_consensus_count=1,
    )

    # Recommended overall stake (fractional Kelly on adjusted prob).
    overall_kelly = kelly_fraction(adj_prob, parlay_american, settings.kelly_fraction)
    recommended_stake = round(bankroll * overall_kelly, 2)

    result = {
        "book": book,
        "legs": leg_results,
        "combined_decimal_odds": round(combined_decimal, 3),
        "combined_american_odds": parlay_american,
        "combined_model_prob_independent": round(indep_prob, 4),
        "combined_model_prob_correlated": round(adj_prob, 4),
        "combined_implied_prob": round(combined_implied, 4),
        "combined_edge_pct_independent": round(parlay_edge_indep, 3),
        "combined_edge_pct_correlated": round(parlay_edge_adj, 3),
        "correlation_notes": corr_notes,
        "rating": rating,
        "rating_breakdown": breakdown,
        "recommended_stake_units": round(overall_kelly * 100, 2),
        "recommended_stake": recommended_stake,
        "bankroll": bankroll,
        "verdict": _verdict(rating, parlay_edge_adj),
        "warnings": _warnings(leg_results, corr_notes),
    }

    if persist:
        db.add(BetSlip(
            submitted_by=submitted_by,
            book=book,
            legs=leg_results,
            combined_odds_american=parlay_american,
            combined_prob=float(adj_prob),
            implied_prob=float(combined_implied),
            edge_pct=float(parlay_edge_adj),
            rating=float(rating),
            notes={"verdict": result["verdict"], "warnings": result["warnings"]},
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


def _warnings(legs: list[dict], corr_notes: list[dict]) -> list[str]:
    warns: list[str] = []
    # Same-game correlation
    same_game_count = sum(1 for n in corr_notes if abs(n["correlation"]) > 0)
    if same_game_count > 0:
        warns.append(
            f"{same_game_count} same-game correlation pair(s) detected — true parlay "
            "probability adjusted for non-independence."
        )
    # Negative-edge legs
    neg = [l for l in legs if l.get("edge_pct", 0) < 0]
    if neg:
        warns.append(f"{len(neg)} leg(s) have negative EV at the posted price.")
    # Low sample size
    low_samp = [l for l in legs if (l.get("rationale", {}).get("sample_size") or 0) < 100]
    if len(low_samp) == len(legs):
        warns.append("All legs have low historical sample size — model probabilities are weak priors.")
    # Better price available
    upgrades = [l for l in legs if (l.get("lineshop", {}).get("price_lift_vs_current_pct") or 0) > 2]
    if upgrades:
        names = ", ".join(f'{l["player_name"]} ({l["lineshop"]["best"]["book"]})' for l in upgrades[:3])
        warns.append(f"Better price available elsewhere: {names}")
    return warns
