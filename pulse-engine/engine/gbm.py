"""Brownian-motion fair value for 15-minute up/down windows.

This is the pricing model the practitioner ecosystem converges on for these
markets: treat the window as a driftless diffusion, so the probability the
window closes above its open given the move so far is

    P(up) = Phi( ln(spot / window_open) / (sigma * sqrt(seconds_remaining)) )

with sigma the realized volatility per sqrt-second from trailing 1-minute
log returns. Early in the window this sits near 50%; as time runs out the
same move pins the probability toward 0/1. It is both a strong standalone
fallback and a feature the ML model can refine.
"""
from __future__ import annotations

import math

import numpy as np

_DEFAULT_SIGMA_15M = 0.0015  # 0.15% per 15 minutes — fallback when data is thin
DEFAULT_SIGMA_PER_SQRT_S = _DEFAULT_SIGMA_15M / math.sqrt(15 * 60)

PROB_FLOOR, PROB_CAP = 0.01, 0.99


def phi(z: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def sigma_per_sqrt_second(minute_closes: np.ndarray, lookback: int = 60) -> float:
    """Realized vol per sqrt-second from trailing 1-minute closes."""
    closes = np.asarray(minute_closes, dtype=float)
    closes = closes[closes > 0][-(lookback + 1):]
    if len(closes) < 15:
        return DEFAULT_SIGMA_PER_SQRT_S
    rets = np.diff(np.log(closes))
    s_min = float(np.std(rets))
    if not math.isfinite(s_min) or s_min <= 0:
        return DEFAULT_SIGMA_PER_SQRT_S
    return s_min / math.sqrt(60.0)


def prob_up(window_open: float, spot: float, sigma_s: float,
            seconds_remaining: float) -> float:
    """P(close > window open) under driftless Brownian motion, in [0.01, 0.99]."""
    if window_open <= 0 or spot <= 0:
        return 0.5
    x = math.log(spot / window_open)
    tau = max(float(seconds_remaining), 0.0)
    if tau < 1.0:  # effectively settled
        return PROB_CAP if x > 0 else PROB_FLOOR if x < 0 else 0.5
    denom = max(sigma_s, 1e-12) * math.sqrt(tau)
    z = x / denom
    return float(min(max(phi(z), PROB_FLOOR), PROB_CAP))
