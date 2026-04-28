"""Convert (model_prob, market_prob, edge) into a 0..100 rating."""
from __future__ import annotations

from .utils import american_to_implied, edge_pct, two_way_no_vig


def rating_from_components(
    model_prob: float,
    price_american: int,
    fair_prob: float | None = None,
    sample_size: int = 0,
    market_consensus_count: int = 1,
) -> tuple[float, dict]:
    """Return (rating in [0,100], breakdown).

    Inputs:
      model_prob: model's calibrated P(side wins)
      price_american: posted American odds for the side
      fair_prob: vig-removed market probability if available (used as a sanity prior)
      sample_size: how many historical games informed the model
      market_consensus_count: number of books offering this market (more = more reliable line)
    """
    implied = american_to_implied(price_american)
    edge = edge_pct(model_prob, price_american)  # in %

    # Component scores (each 0..1 then weighted).
    # 1) Edge component: 0% edge -> 0; 8% edge -> ~0.85; capped.
    edge_score = max(0.0, min(1.0, edge / 8.0))

    # 2) Confidence: how far from 50/50 — high-confidence picks get bonus,
    #    but we cap to avoid the model overrating extreme priors.
    conf_score = max(0.0, min(1.0, (abs(model_prob - 0.5) - 0.05) / 0.35))

    # 3) Disagreement vs market: if model differs from fair_prob in our favor.
    if fair_prob is not None:
        disagreement = max(0.0, model_prob - fair_prob)
        disagreement_score = max(0.0, min(1.0, disagreement / 0.10))
    else:
        disagreement_score = 0.5

    # 4) Sample-size discount: priors with little data get penalized.
    sample_score = max(0.0, min(1.0, sample_size / 200.0))

    # 5) Market depth: more books -> trust the line more, penalize less.
    depth_score = max(0.3, min(1.0, market_consensus_count / 4.0))

    weights = {
        "edge": 0.45,
        "confidence": 0.15,
        "disagreement": 0.20,
        "sample": 0.10,
        "depth": 0.10,
    }
    raw = (
        weights["edge"] * edge_score
        + weights["confidence"] * conf_score
        + weights["disagreement"] * disagreement_score
        + weights["sample"] * sample_score
        + weights["depth"] * depth_score
    )
    rating = round(100.0 * raw, 1)

    breakdown = {
        "edge_pct": round(edge, 3),
        "implied_prob": round(implied, 4),
        "model_prob": round(model_prob, 4),
        "fair_prob": round(fair_prob, 4) if fair_prob is not None else None,
        "components": {
            "edge_score": round(edge_score, 3),
            "confidence_score": round(conf_score, 3),
            "disagreement_score": round(disagreement_score, 3),
            "sample_score": round(sample_score, 3),
            "depth_score": round(depth_score, 3),
        },
        "weights": weights,
    }
    return rating, breakdown


def fair_two_way(over_american: int | None, under_american: int | None) -> tuple[float | None, float | None]:
    if over_american is None or under_american is None:
        return None, None
    p_o, p_u = two_way_no_vig(over_american, under_american)
    return p_o, p_u
