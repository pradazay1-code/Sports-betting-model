"""Fee-aware edge calculation and pick decision vs Kalshi prices.

Prices/probabilities are dollars in [0, 1] throughout ("points" = cents).
A pick is flagged only when the model's calibrated probability beats the
market's implied probability by more than (taker fee + edge buffer) AND the
model probability sits outside the no-confidence band around 50%.
NO PLAY is a first-class output — it should be the most common one.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import config

NO_PLAY = "NO PLAY"
UP = "UP"
DOWN = "DOWN"


@dataclass
class Decision:
    pick: str                     # UP | DOWN | NO PLAY
    prob_up: float                # decision prob (model shrunk toward market)
    implied_up: float | None     # None when Kalshi has no market
    edge: float | None           # signed, for the side picked (or best side)
    fee: float | None            # per-contract fee at the entry price
    entry_price: float | None    # price paid per contract for the picked side
    raw_prob_up: float | None = None   # model prob before market shrinkage
    reasons: list[str] = field(default_factory=list)


def implied_from_quotes(yes_bid: float | None, yes_ask: float | None) -> float | None:
    """Mid-quote implied P(up), from cent quotes (0-100)."""
    if yes_bid is None or yes_ask is None:
        return None
    if yes_bid <= 0 and yes_ask <= 0:
        return None
    return round(((yes_bid + yes_ask) / 2.0) / 100.0, 4)


def decide(
    prob_up: float,
    yes_bid: float | None,
    yes_ask: float | None,
    buffer: float | None = None,
    band: tuple[float, float] = config.CONFIDENCE_BAND,
) -> Decision:
    """Decide UP / DOWN / NO PLAY for one window.

    yes_bid/yes_ask are Kalshi cent quotes (0-100). Buying UP fills at the
    yes ask; buying DOWN fills at the no ask == 100 - yes_bid. Edge for a side
    is model P(side) minus the price paid, and must clear fee + buffer.
    """
    buffer = config.MIN_EDGE_BUFFER if buffer is None else buffer
    implied = implied_from_quotes(yes_bid, yes_ask)
    d = Decision(pick=NO_PLAY, prob_up=prob_up, implied_up=implied,
                 edge=None, fee=None, entry_price=None, raw_prob_up=prob_up)

    if implied is None:
        d.reasons.append("no Kalshi market/quotes for this window")
        return d

    # Winner's-curse correction: shrink the model toward the market's price.
    # Large model-vs-market gaps are where the model is most often the one
    # that's wrong; requiring the shrunk probability to still clear the
    # threshold keeps only the fattest, most defensible disagreements.
    prob_up = implied + config.MODEL_MARKET_SHRINK * (prob_up - implied)
    d.prob_up = round(prob_up, 4)

    in_band = band[0] <= prob_up <= band[1]

    up_price = (yes_ask or 0) / 100.0
    down_price = (100.0 - (yes_bid or 100)) / 100.0
    up_fee = config.kalshi_fee_per_contract(up_price) if 0 < up_price < 1 else None
    down_fee = config.kalshi_fee_per_contract(down_price) if 0 < down_price < 1 else None

    up_edge = prob_up - up_price if up_fee is not None else None
    down_edge = (1.0 - prob_up) - down_price if down_fee is not None else None

    candidates: list[tuple[str, float, float, float]] = []  # (side, edge, fee, price)
    if up_edge is not None and up_edge > up_fee + buffer:
        candidates.append((UP, up_edge, up_fee, up_price))
    if down_edge is not None and down_edge > down_fee + buffer:
        candidates.append((DOWN, down_edge, down_fee, down_price))

    if not candidates:
        best = max(filter(None, [up_edge, down_edge]), default=None)
        d.edge = round(best, 4) if best is not None else None
        d.reasons.append(
            f"edge {d.edge if d.edge is not None else 'n/a'} does not clear "
            f"fee + {buffer:.2f} buffer")
        return d

    if in_band:
        best = max(candidates, key=lambda c: c[1])
        d.edge = round(best[1], 4)
        d.reasons.append(
            f"model prob {prob_up:.3f} inside {band[0]:.0%}-{band[1]:.0%} band")
        return d

    side, edge_v, fee_v, price = max(candidates, key=lambda c: c[1])
    d.pick, d.edge, d.fee, d.entry_price = side, round(edge_v, 4), fee_v, price
    d.reasons.append(f"{side}: edge {edge_v:.3f} > fee {fee_v:.4f} + buffer {buffer:.2f}")
    return d


def kelly_suggestion(p: float, price: float) -> dict:
    """Fractional-Kelly stake suggestion for buying a binary at `price` with
    win probability `p`. Display guidance only — nothing sizes real money.
    """
    if not (0 < price < 1) or p <= price:
        return {"fraction": 0.0, "contracts": 0}
    b = (1.0 - price) / price               # net odds
    f_star = (b * p - (1.0 - p)) / b        # full Kelly
    frac = max(f_star, 0.0) * config.KELLY_FRACTION
    dollars = frac * config.PAPER_BANKROLL
    return {"fraction": round(frac, 4), "contracts": int(dollars / price)}


def dual_side_arb(yes_ask: float | None, no_ask: float | None) -> float | None:
    """Guaranteed gross profit in cents per pair when YES ask + NO ask < 100
    (one side always settles at $1). Returns None when there is no arb.
    Caller must still net out the two entry fees before acting on it.
    """
    if yes_ask is None or no_ask is None or yes_ask <= 0 or no_ask <= 0:
        return None
    total = yes_ask + no_ask
    return round(100.0 - total, 2) if total < 100.0 else None


def paper_pnl(pick: str, entry_price: float, won: bool,
              contracts: int | None = None) -> float:
    """Paper P&L in dollars for a resolved pick, entry taker fee included.

    Settlement at $1 (win) or $0 (loss); Kalshi charges no settlement fee.
    """
    if pick == NO_PLAY:
        return 0.0
    n = contracts or config.PAPER_CONTRACTS
    fee = config.kalshi_fee_dollars(n, entry_price)
    payout = n * 1.0 if won else 0.0
    return round(payout - n * entry_price - fee, 2)
