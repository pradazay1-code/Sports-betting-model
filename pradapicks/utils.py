"""Shared math helpers for odds and probabilities."""
from __future__ import annotations

import math
from typing import Iterable


def american_to_decimal(american: int) -> float:
    if american == 0:
        return 1.0
    if american > 0:
        return 1.0 + american / 100.0
    return 1.0 + 100.0 / abs(american)


def decimal_to_american(dec: float) -> int:
    if dec <= 1.0:
        return 0
    if dec >= 2.0:
        return int(round((dec - 1.0) * 100.0))
    return int(round(-100.0 / (dec - 1.0)))


def american_to_implied(american: int) -> float:
    if american == 0:
        return 0.5
    if american > 0:
        return 100.0 / (american + 100.0)
    return abs(american) / (abs(american) + 100.0)


def two_way_no_vig(over_american: int, under_american: int) -> tuple[float, float]:
    """Remove vig from a 2-way market, return (p_over, p_under)."""
    o = american_to_implied(over_american)
    u = american_to_implied(under_american)
    s = o + u
    if s <= 0:
        return 0.5, 0.5
    return o / s, u / s


def edge_pct(model_prob: float, american: int) -> float:
    """Expected value % per $1 risked."""
    dec = american_to_decimal(american)
    ev = model_prob * (dec - 1.0) - (1.0 - model_prob)
    return ev * 100.0


def kelly_fraction(model_prob: float, american: int, fraction: float = 1.0) -> float:
    dec = american_to_decimal(american)
    b = dec - 1.0
    if b <= 0:
        return 0.0
    q = 1.0 - model_prob
    f = (b * model_prob - q) / b
    return max(0.0, f * fraction)


def combine_legs_decimal(legs_american: Iterable[int]) -> float:
    dec = 1.0
    for a in legs_american:
        dec *= american_to_decimal(a)
    return dec


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b else default


def clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)
