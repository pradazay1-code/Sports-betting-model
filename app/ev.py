"""EV math: de-vig, fair probability, edge, Kelly stake, rating."""

from __future__ import annotations

from dataclasses import dataclass

from app.utils import american_to_decimal, american_to_prob


@dataclass(frozen=True)
class Priced:
    side: str            # "over" or "under"
    model_prob: float    # model's predicted P(side wins) in [0, 1]
    fair_prob: float     # no-vig book-implied prob in [0, 1]
    price_american: int
    decimal: float
    edge_pct: float      # (decimal * model_prob - 1) * 100
    kelly_stake: float   # fractional Kelly stake in [0, 1]


def devig_two_way(over_american: int, under_american: int) -> tuple[float, float]:
    """Multiplicative de-vig of a 2-way market.

    Returns (fair_over_prob, fair_under_prob)."""
    po = american_to_prob(over_american)
    pu = american_to_prob(under_american)
    total = po + pu
    if total <= 0:
        return 0.5, 0.5
    return po / total, pu / total


def kelly_fraction(model_prob: float, price_american: int) -> float:
    d = american_to_decimal(price_american)
    b = d - 1.0
    p = max(0.0, min(1.0, model_prob))
    q = 1.0 - p
    if b <= 0:
        return 0.0
    k = (b * p - q) / b
    return max(0.0, min(1.0, k))


def price(side: str, model_prob: float, fair_prob: float, price_american: int) -> Priced:
    d = american_to_decimal(price_american)
    edge_pct = (d * model_prob - 1.0) * 100.0
    k = kelly_fraction(model_prob, price_american)
    return Priced(
        side=side,
        model_prob=model_prob,
        fair_prob=fair_prob,
        price_american=price_american,
        decimal=d,
        edge_pct=edge_pct,
        kelly_stake=k,
    )


# --- rating ---------------------------------------------------------------

RATING_WEIGHTS = {
    "edge": 0.45,
    "confidence": 0.15,
    "disagreement": 0.20,
    "sample": 0.10,
    "depth": 0.10,
}


def rating(*, edge_pct: float, model_prob: float, fair_prob: float,
           n_train_rows: int, n_books: int) -> tuple[float, dict[str, float]]:
    """Return (0-100 rating, components)."""

    edge_score = _clip01(edge_pct / 15.0)  # 15%+ edge maxes the bar
    confidence_score = _clip01(abs(model_prob - 0.5) / 0.25)  # |0.5 - 0.25..0.75|
    disagreement_score = _clip01(abs(model_prob - fair_prob) / 0.10)
    sample_score = _clip01(n_train_rows / 2000.0)
    depth_score = _clip01((n_books - 1) / 3.0)

    parts = {
        "edge": edge_score, "confidence": confidence_score,
        "disagreement": disagreement_score, "sample": sample_score,
        "depth": depth_score,
    }
    total = sum(RATING_WEIGHTS[k] * v for k, v in parts.items())
    return round(100.0 * total, 1), parts


def _clip01(x: float) -> float:
    if x < 0:
        return 0.0
    if x > 1:
        return 1.0
    return float(x)
