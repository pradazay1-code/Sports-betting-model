"""Shared probability utilities for all sport models (spec §3).

Count props -> Poisson / negative binomial. Continuous props -> normal
(or Monte Carlo when inputs interact). Recency weighting, small-sample
regression to the mean, and calibration shrinkage live here too.

Pure stdlib math — no scipy needed for the core distributions.
"""

from __future__ import annotations

import math
import random
from statistics import NormalDist


# ------------------------------------------------------------ distributions

def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(k * math.log(lam) - lam - math.lgamma(k + 1))


def poisson_cdf(k: int, lam: float) -> float:
    if k < 0:
        return 0.0
    return sum(poisson_pmf(i, lam) for i in range(k + 1))


def prob_over_poisson(line: float, lam: float) -> float:
    """P(X > line) for a count stat. For a 6.5 line this is 1 - CDF(6)."""
    return 1.0 - poisson_cdf(math.floor(line), lam)


def negbin_pmf(k: int, mean: float, dispersion: float) -> float:
    """Negative binomial with mean m and size r (var = m + m^2/r).

    dispersion (r) -> infinity recovers Poisson; small r = fat tails.
    """
    r, m = dispersion, mean
    if m <= 0:
        return 1.0 if k == 0 else 0.0
    p = r / (r + m)
    return math.exp(
        math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1)
        + r * math.log(p) + k * math.log(1 - p)
    )


def prob_over_negbin(line: float, mean: float, dispersion: float) -> float:
    k = math.floor(line)
    return 1.0 - sum(negbin_pmf(i, mean, dispersion) for i in range(k + 1))


def prob_over_normal(line: float, mu: float, sigma: float) -> float:
    """P(X > line) for a continuous stat (yards, points)."""
    if sigma <= 0:
        return 1.0 if mu > line else 0.0
    return 1.0 - NormalDist(mu, sigma).cdf(line)


def monte_carlo_over(line: float, sampler, n: int = 10_000, seed: int | None = 7) -> float:
    """P(X > line) by simulation. `sampler(rng)` returns one outcome draw."""
    rng = random.Random(seed)
    hits = sum(1 for _ in range(n) if sampler(rng) > line)
    return hits / n


# --------------------------------------------------------- projection tools

def decay_weights(n: int, decay: float = 0.85) -> list[float]:
    """Exponential recency weights, most recent game first (weight 1.0)."""
    return [decay ** i for i in range(n)]


def weighted_recent_rate(values: list[float], decay: float = 0.85,
                         window: int = 15) -> float:
    """Decay-weighted mean of the most recent `window` values
    (values ordered most recent first)."""
    vals = values[:window]
    if not vals:
        raise ValueError("no values to weight")
    weights = decay_weights(len(vals), decay)
    return sum(v * w for v, w in zip(vals, weights)) / sum(weights)


def regress_to_mean(player_rate: float, n: int, league_rate: float, k: float) -> float:
    """adjusted = (n*player + k*league)/(n+k) — spec §3 small-sample shrinkage."""
    return (n * player_rate + k * league_rate) / (n + k)


def opponent_adjustment(opp_allowed_rate: float, league_rate: float,
                        power: float = 1.0) -> float:
    """Multiplier: opponent's allowed rate vs league average.

    power < 1 dampens the adjustment (opponent samples are noisy).
    """
    if league_rate <= 0:
        return 1.0
    return (opp_allowed_rate / league_rate) ** power


def shrink_probability(p: float, factor: float, anchor: float = 0.5) -> float:
    """Calibration shrinkage toward an anchor (default coin-flip).

    factor 1.0 = trust the model fully; 0.0 = pure anchor. weekly_review
    (Phase 6) derives the factor from realized calibration buckets.
    """
    factor = max(0.0, min(1.0, factor))
    return anchor + factor * (p - anchor)
