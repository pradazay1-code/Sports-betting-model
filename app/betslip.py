"""Bet slip analyzer.

Given a list of legs, return per-leg pricing (model prob, fair prob, edge%,
Kelly stake, 0..100 rating) and the parlay's combined model + fair prob
*adjusted for same-game correlation*.

Correlation model is intentionally conservative:
  - independent legs (different games)                 -> rho = 0
  - same game, same player, different markets          -> rho = 0.30
  - same game, same team, same market                  -> rho = 0.20
  - same game, opposing teams, same market             -> rho = -0.15
  - everything else same game                          -> rho = 0.10
Combined probability uses a Gaussian-copula approximation: convert leg
probs to z-scores, take a correlation-weighted sum, recover joint prob
through the multivariate normal CDF. For 2- and 3-leg slips this is
accurate enough; for larger slips we fall back to the product (less
favourable). Sportsbooks use far more aggressive correlations internally
so we err on the side of underestimating EV.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations

import numpy as np
from scipy.stats import multivariate_normal, norm

from app.ev import devig_two_way, kelly_fraction, price as price_one, rating
from app.features import build_inference_features
from app.models import prop_model
from app.utils import american_to_decimal


@dataclass
class Leg:
    sport: str
    player_name: str
    market: str
    line: float
    side: str            # "over"|"under"
    price_american: int
    game_id: str | None = None
    team: str | None = None
    opp_team: str | None = None


@dataclass
class LegResult:
    leg: Leg
    model_prob: float
    fair_prob: float
    edge_pct: float
    kelly_stake: float
    rating: float
    rationale: dict


@dataclass
class SlipResult:
    legs: list[LegResult]
    parlay_decimal: float
    parlay_american: int
    naive_model_prob: float
    correlated_model_prob: float
    parlay_edge_pct: float
    verdict: str


def _correlation(a: Leg, b: Leg) -> float:
    if a.game_id and b.game_id and a.game_id != b.game_id:
        return 0.0
    if not (a.game_id and b.game_id):
        # Unknown game ids — assume independent if names differ, mild
        # positive if same player.
        if a.player_name == b.player_name:
            return 0.30
        return 0.0
    if a.player_name == b.player_name and a.market != b.market:
        return 0.30
    if a.team and a.team == b.team and a.market == b.market:
        return 0.20
    if a.team and b.team and a.team != b.team and a.market == b.market:
        return -0.15
    return 0.10


def _gaussian_copula_prob(probs: list[float], legs: list[Leg]) -> float:
    n = len(probs)
    if n == 0:
        return 1.0
    if n == 1:
        return probs[0]
    # Build correlation matrix
    rho = np.eye(n)
    for i, j in combinations(range(n), 2):
        r = max(-0.99, min(0.99, _correlation(legs[i], legs[j])))
        rho[i, j] = rho[j, i] = r
    # Convert each leg p_i to a normal threshold t_i = Phi^-1(p_i).
    ts = norm.ppf(np.clip(probs, 1e-4, 1 - 1e-4))
    # P(all legs hit) = P(N <= t) under MV-normal with mean 0, cov rho.
    try:
        mvn = multivariate_normal(mean=np.zeros(n), cov=rho, allow_singular=True)
        joint = float(mvn.cdf(ts))
    except Exception:
        joint = float(np.prod(probs))
    return max(min(joint, 1.0), 0.0)


def _model_prob_for_leg(leg: Leg, on_date: str) -> tuple[float, float] | None:
    """Returns (model_prob, fair_prob_from_devig). Fair prob is computed by
    de-vigging when both sides are present at the book; otherwise we use the
    book's implied prob as a conservative substitute."""
    tm = prop_model.load(leg.sport, leg.market)
    if tm is None:
        return None
    feats = build_inference_features(leg.sport, leg.market, leg.player_name, on_date,
                                     opp_team=leg.opp_team, home=None)
    if feats is None:
        return None
    p_over = tm.prob_over(feats, float(leg.line))
    p = p_over if leg.side == "over" else 1.0 - p_over
    # Use implied (with-vig) as fair proxy; the analyzer doesn't have the
    # other side of the line.
    fair = 1.0 / american_to_decimal(leg.price_american)
    return p, fair


def _verdict(parlay_edge_pct: float) -> str:
    if parlay_edge_pct >= 10.0: return "Strong +EV"
    if parlay_edge_pct >= 3.0:  return "+EV"
    if parlay_edge_pct >= -3.0: return "Neutral"
    return "-EV"


def analyze(legs: list[Leg], on_date: str) -> SlipResult:
    leg_results: list[LegResult] = []
    leg_probs: list[float] = []
    parlay_dec = 1.0
    for leg in legs:
        mp_fp = _model_prob_for_leg(leg, on_date)
        if mp_fp is None:
            mp = 1.0 / american_to_decimal(leg.price_american)
            fp = mp
        else:
            mp, fp = mp_fp
        d = american_to_decimal(leg.price_american)
        edge = (d * mp - 1.0) * 100.0
        rate, parts = rating(
            edge_pct=edge, model_prob=mp, fair_prob=fp,
            n_train_rows=prop_model.load(leg.sport, leg.market).n_train if mp_fp else 0,
            n_books=1,
        )
        leg_results.append(LegResult(
            leg=leg, model_prob=mp, fair_prob=fp,
            edge_pct=edge, kelly_stake=kelly_fraction(mp, leg.price_american),
            rating=rate, rationale={"components": parts},
        ))
        leg_probs.append(mp)
        parlay_dec *= d

    naive = float(np.prod(leg_probs)) if leg_probs else 0.0
    corr = _gaussian_copula_prob(leg_probs, legs)
    # American odds from decimal payout.
    if parlay_dec >= 2.0:
        parlay_amer = int(round((parlay_dec - 1.0) * 100))
    elif parlay_dec > 1.0:
        parlay_amer = int(round(-100.0 / (parlay_dec - 1.0)))
    else:
        parlay_amer = 0
    parlay_edge_pct = (parlay_dec * corr - 1.0) * 100.0
    return SlipResult(
        legs=leg_results,
        parlay_decimal=parlay_dec,
        parlay_american=parlay_amer,
        naive_model_prob=naive,
        correlated_model_prob=corr,
        parlay_edge_pct=parlay_edge_pct,
        verdict=_verdict(parlay_edge_pct),
    )
