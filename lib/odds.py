"""
Price math for The Desk.

Deliberately stdlib-only. This module is the arithmetic backbone of every
recommendation, so it must run even when nothing else is installed and the
network is down.

Conventions used throughout:
  - "american"  : American odds, int or float (-110, +150). Never 0.
  - "decimal"   : Decimal odds, float > 1.0.
  - "prob"      : Probability in [0, 1].
  - "q"         : *Raw* implied probability off a posted price. Includes vig.
                  A two-way market's q values sum to > 1.
  - "p" / "fair": Devigged probability. Sums to 1 across a market.

CLI:
    python3 -m lib.odds devig -110 -110
    python3 -m lib.odds devig +120 -140 --method power
    python3 -m lib.odds ev --fair -105 --offered +100
    python3 -m lib.odds kelly --prob 0.55 --odds +100
    python3 -m lib.odds parlay -110 -110 +150
    python3 -m lib.odds hold -110 -110
    python3 -m lib.odds clv --taken +100 --closed -110
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
from dataclasses import dataclass, asdict
from typing import Sequence

__all__ = [
    "american_to_decimal",
    "decimal_to_american",
    "implied_prob",
    "prob_to_decimal",
    "prob_to_american",
    "overround",
    "hold",
    "devig",
    "devig_all",
    "devig_spread",
    "ev",
    "ev_from_american",
    "kelly",
    "stake_units",
    "parlay_decimal",
    "parlay_analysis",
    "round_robin",
    "sharp_anchor",
    "clv",
    "SHARP_BOOK_PRIORITY",
    "SOFT_BOOKS",
    "DEVIG_METHODS",
]

# ---------------------------------------------------------------------------
# House constants
# ---------------------------------------------------------------------------

#: Books we estimate *from*, in priority order. Lower index = sharper.
SHARP_BOOK_PRIORITY: tuple[str, ...] = (
    "pinnacle",
    "circa",
    "circasports",
    "betonlineag",
    "betonline",
    "bookmaker",
    "bookmakereu",
    "heritage",
    "lowvig",
    "betcris",
    "pinnaclesports",
)

#: Books we bet *into*. Never anchor a fair price on these.
SOFT_BOOKS: frozenset[str] = frozenset(
    {
        "draftkings",
        "fanduel",
        "betmgm",
        "caesars",
        "williamhill_us",
        "espnbet",
        "fanatics",
        "betrivers",
        "pointsbetus",
        "unibet",
        "bet365",
        "hardrockbet",
        "ballybet",
        "betparx",
        "windcreek",
        "superbook",
        "wynnbet",
    }
)

DEVIG_METHODS: tuple[str, ...] = ("multiplicative", "additive", "power", "shin")

#: EV below this after devig is inside our own method error. Not a bet.
MIN_EV = 0.02

#: Quarter Kelly is the house default.
DEFAULT_KELLY_DIVISOR = 4.0

#: Hard ceiling, in units. This is a rule, not a setting.
MAX_STAKE_UNITS = 2.0

#: Probability points of disagreement between devig methods that we consider
#: "meaningful" and therefore worth quoting as a range instead of a point.
DEVIG_DISAGREEMENT_THRESHOLD = 0.015

_EPS = 1e-12


# ---------------------------------------------------------------------------
# Conversions
# ---------------------------------------------------------------------------


def american_to_decimal(american: float) -> float:
    """-110 -> 1.9091, +150 -> 2.50."""
    a = float(american)
    if -100.0 < a < 100.0:
        raise ValueError(f"invalid American odds: {american!r} (must be <=-100 or >=+100)")
    if a > 0:
        return 1.0 + a / 100.0
    return 1.0 + 100.0 / abs(a)


def decimal_to_american(dec: float) -> float:
    """1.9091 -> -110.0, 2.50 -> +150.0."""
    d = float(dec)
    if d <= 1.0:
        raise ValueError(f"invalid decimal odds: {dec!r} (must be > 1.0)")
    if d >= 2.0:
        return round((d - 1.0) * 100.0, 2)
    return round(-100.0 / (d - 1.0), 2)


def implied_prob(american: float) -> float:
    """Raw implied probability off a posted American price. Includes vig."""
    return 1.0 / american_to_decimal(american)


def prob_to_decimal(prob: float) -> float:
    if not (0.0 < prob < 1.0):
        raise ValueError(f"probability out of range: {prob!r}")
    return 1.0 / prob


def prob_to_american(prob: float) -> float:
    """Fair American price for a probability. 0.5 -> +100."""
    return decimal_to_american(prob_to_decimal(prob))


def _as_probs(prices: Sequence[float], *, decimal: bool = False) -> list[float]:
    if not prices:
        raise ValueError("no prices given")
    if decimal:
        return [1.0 / float(p) for p in prices]
    return [implied_prob(p) for p in prices]


# ---------------------------------------------------------------------------
# Vig measurement
# ---------------------------------------------------------------------------


def overround(prices: Sequence[float], *, decimal: bool = False) -> float:
    """Sum of raw implied probabilities. 1.0476 means a 4.76% overround."""
    return sum(_as_probs(prices, decimal=decimal))


def hold(prices: Sequence[float], *, decimal: bool = False) -> float:
    """
    The book's theoretical hold on a balanced book.

    hold = 1 - 1/overround. A standard -110/-110 two-way holds ~4.55%.
    Note this is *not* the same as the overround minus one.
    """
    return 1.0 - 1.0 / overround(prices, decimal=decimal)


# ---------------------------------------------------------------------------
# Devigging
# ---------------------------------------------------------------------------


def _devig_multiplicative(q: Sequence[float]) -> list[float]:
    """Proportional / normalized. Scales every outcome by the same factor.

    Simple and stable. Its weakness is that it assumes vig is applied
    proportionally, which overstates longshot fair probability in markets with
    real favorite-longshot bias.
    """
    total = sum(q)
    return [x / total for x in q]


def _devig_additive(q: Sequence[float]) -> list[float]:
    """Subtracts an equal share of the overround from every outcome.

    The mirror-image bias of multiplicative: it takes proportionally more away
    from longshots. Can drive extreme longshots negative, in which case we clamp
    at a floor and renormalize (and the result should be distrusted).
    """
    n = len(q)
    excess = (sum(q) - 1.0) / n
    out = [x - excess for x in q]
    if any(x <= 0.0 for x in out):
        floor = 1e-6
        out = [max(x, floor) for x in out]
        total = sum(out)
        out = [x / total for x in out]
    return out


def _devig_power(q: Sequence[float], *, tol: float = 1e-12, max_iter: int = 200) -> list[float]:
    """Solve sum(q_i ** k) = 1 for k, return q_i ** k.

    Because every q_i < 1, raising to k > 1 shrinks the sum monotonically, so a
    plain bisection on k is safe and converges fast. This is the default for
    two-way markets: it removes proportionally more vig from the longshot, which
    is what books actually do.
    """
    if any(x <= 0.0 or x >= 1.0 for x in q):
        # A price at or beyond even money on a single outcome breaks the
        # exponent solve. Fall back rather than return nonsense.
        return _devig_multiplicative(q)

    lo, hi = 1.0, 2.0
    # Expand the bracket until sum(q**hi) <= 1.
    for _ in range(60):
        if sum(x**hi for x in q) <= 1.0:
            break
        lo, hi = hi, hi * 2.0
    else:
        return _devig_multiplicative(q)

    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        s = sum(x**mid for x in q)
        if abs(s - 1.0) < tol:
            break
        if s > 1.0:
            lo = mid
        else:
            hi = mid
    k = 0.5 * (lo + hi)
    out = [x**k for x in q]
    total = sum(out)
    return [x / total for x in out]


def _devig_shin(q: Sequence[float], *, tol: float = 1e-12, max_iter: int = 200) -> list[float]:
    """
    Shin (1992/1993) — models the overround as the book's protection against a
    proportion `z` of insider money.

        p_i = [ sqrt(z^2 + 4(1-z) * q_i^2 / PI) - z ] / (2(1-z)),  PI = sum(q)

    Solve for z such that sum(p_i) = 1. At z = 0 the sum is sqrt(PI) > 1 and it
    decreases in z, so bisection on [0, 1) is again safe.

    Shin tends to sit between multiplicative and power. Its `z` is interpretable:
    a high z means the book is pricing in a lot of adverse selection, which is
    itself a signal about the market.
    """
    pi = sum(q)
    if pi <= 1.0 + _EPS:
        return _devig_multiplicative(q)

    def probs(z: float) -> list[float]:
        if z <= _EPS:
            return [x / math.sqrt(pi) for x in q]
        denom = 2.0 * (1.0 - z)
        return [(math.sqrt(z * z + 4.0 * (1.0 - z) * x * x / pi) - z) / denom for x in q]

    lo, hi = 0.0, 0.99
    if sum(probs(hi)) > 1.0:
        return _devig_multiplicative(q)

    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        s = sum(probs(mid))
        if abs(s - 1.0) < tol:
            break
        if s > 1.0:
            lo = mid
        else:
            hi = mid
    out = probs(0.5 * (lo + hi))
    total = sum(out)
    return [x / total for x in out]


_DEVIG_FNS = {
    "multiplicative": _devig_multiplicative,
    "proportional": _devig_multiplicative,
    "additive": _devig_additive,
    "power": _devig_power,
    "shin": _devig_shin,
}


def default_method(n_outcomes: int) -> str:
    """Power for two-way, multiplicative for multiway. House rule."""
    return "power" if n_outcomes == 2 else "multiplicative"


def devig(
    prices: Sequence[float],
    method: str | None = None,
    *,
    decimal: bool = False,
) -> list[float]:
    """Fair probabilities for a market. `method=None` picks the house default."""
    q = _as_probs(prices, decimal=decimal)
    m = (method or default_method(len(q))).lower()
    if m not in _DEVIG_FNS:
        raise ValueError(f"unknown devig method {method!r}; pick from {DEVIG_METHODS}")
    return _DEVIG_FNS[m](q)


def devig_all(prices: Sequence[float], *, decimal: bool = False) -> dict[str, list[float]]:
    """Every method at once, so we can see whether they agree."""
    q = _as_probs(prices, decimal=decimal)
    return {m: _DEVIG_FNS[m](q) for m in DEVIG_METHODS}


def devig_spread(prices: Sequence[float], *, decimal: bool = False) -> dict:
    """
    How much the devig methods disagree.

    When `meaningful` is True, quote fair value as a range rather than a point
    estimate and let the width feed into your confidence level. Methods
    disagreeing by 2+ points of probability on a two-way market usually means
    the price is stale, the market is thin, or one side is a real longshot.
    """
    allp = devig_all(prices, decimal=decimal)
    n = len(next(iter(allp.values())))
    per_outcome = []
    for i in range(n):
        vals = {m: allp[m][i] for m in allp}
        lo_m = min(vals, key=vals.get)
        hi_m = max(vals, key=vals.get)
        per_outcome.append(
            {
                "index": i,
                "min": vals[lo_m],
                "min_method": lo_m,
                "max": vals[hi_m],
                "max_method": hi_m,
                "spread": vals[hi_m] - vals[lo_m],
            }
        )
    widest = max(o["spread"] for o in per_outcome)
    return {
        "by_method": allp,
        "per_outcome": per_outcome,
        "widest_spread": widest,
        "meaningful": widest >= DEVIG_DISAGREEMENT_THRESHOLD,
        "threshold": DEVIG_DISAGREEMENT_THRESHOLD,
    }


# ---------------------------------------------------------------------------
# Edge and staking
# ---------------------------------------------------------------------------


def ev(fair_prob: float, offered_decimal: float) -> float:
    """EV per unit staked. 0.035 means +3.5% EV."""
    return fair_prob * float(offered_decimal) - 1.0


def ev_from_american(fair_prob: float, offered_american: float) -> float:
    return ev(fair_prob, american_to_decimal(offered_american))


def kelly(prob: float, offered_decimal: float, *, divisor: float = DEFAULT_KELLY_DIVISOR) -> float:
    """
    Fractional Kelly as a share of bankroll.

        f = (p*b - q) / b,  b = decimal - 1,  q = 1 - p

    Returns 0.0 for a non-positive edge; we do not bet negative Kelly.
    """
    b = float(offered_decimal) - 1.0
    if b <= 0:
        return 0.0
    p = float(prob)
    f = (p * b - (1.0 - p)) / b
    if f <= 0:
        return 0.0
    return f / float(divisor)


def stake_units(
    prob: float,
    offered_american: float,
    *,
    divisor: float = DEFAULT_KELLY_DIVISOR,
    bankroll_units: float = 100.0,
    max_units: float = MAX_STAKE_UNITS,
) -> float:
    """
    Kelly stake expressed in units, capped at the house ceiling.

    One unit = 1% of bankroll by convention, so bankroll_units defaults to 100.
    The cap is applied last and is not negotiable.
    """
    dec = american_to_decimal(offered_american)
    f = kelly(prob, dec, divisor=divisor)
    return round(min(f * bankroll_units, max_units), 2)


@dataclass
class Edge:
    """Everything the desk reports about a single price. Never fewer fields."""

    fair_prob: float
    fair_american: float
    offered_american: float
    offered_decimal: float
    ev: float
    kelly_fraction: float
    stake_units: float
    method: str
    is_bet: bool
    note: str

    def to_dict(self) -> dict:
        return asdict(self)


def price_edge(
    fair_prob: float,
    offered_american: float,
    *,
    method: str = "",
    divisor: float = DEFAULT_KELLY_DIVISOR,
    bankroll_units: float = 100.0,
    min_ev: float = MIN_EV,
) -> Edge:
    """Fair price, offered price, EV% — the three forms, every time."""
    dec = american_to_decimal(offered_american)
    e = ev(fair_prob, dec)
    f = kelly(fair_prob, dec, divisor=divisor)
    units = round(min(f * bankroll_units, MAX_STAKE_UNITS), 2)
    is_bet = e >= min_ev
    if not is_bet:
        note = f"EV {e:+.2%} is under the {min_ev:.0%} threshold. Noise, not a bet."
        units = 0.0
    elif f * bankroll_units > MAX_STAKE_UNITS:
        note = f"Kelly wanted {f * bankroll_units:.2f}u; capped at the {MAX_STAKE_UNITS}u ceiling."
    else:
        note = ""
    return Edge(
        fair_prob=fair_prob,
        fair_american=prob_to_american(fair_prob),
        offered_american=float(offered_american),
        offered_decimal=dec,
        ev=e,
        kelly_fraction=f,
        stake_units=units,
        method=method,
        is_bet=is_bet,
        note=note,
    )


# ---------------------------------------------------------------------------
# Parlays
# ---------------------------------------------------------------------------


def parlay_decimal(prices: Sequence[float]) -> float:
    """Offered parlay payout — books multiply the legs."""
    d = 1.0
    for p in prices:
        d *= american_to_decimal(p)
    return d


#: Typical two-way overround: exactly what a -110/-110 market sums to.
#: Computed rather than written as 1.0476, because the rounded literal drifts
#: the derived probabilities in the 5th decimal — which is precisely the fake
#: precision this desk refuses to trade in.
STANDARD_TWO_WAY_OVERROUND = 2.0 * (1.0 / american_to_decimal(-110))


def parlay_analysis(
    leg_prices: Sequence[float],
    leg_fair_probs: Sequence[float] | None = None,
    *,
    correlation_uplift: float = 0.0,
    offered_american: float | None = None,
    assumed_overround: float = STANDARD_TWO_WAY_OVERROUND,
) -> dict:
    """
    Price a parlay honestly.

    `leg_fair_probs` are the devigged probabilities and are what you should pass.

    If they're omitted we do NOT fall back to raw implied probabilities — doing
    that silently prices the vig as if it were true probability and makes every
    parlay look like a coin flip against a fair payout. Instead each leg is
    devigged against an assumed two-way overround (`assumed_overround`, default
    1.0476, i.e. a standard -110/-110 market). That is an approximation and is
    labeled as one in the output, but it is in the right direction and shows the
    hold multiplication that is the entire reason to be suspicious of parlays.

    `correlation_uplift` is a multiplier on the independent joint probability,
    for when legs are genuinely correlated (0.15 = 15% more likely than
    independence implies). Leave at 0.0 for independent legs. This number is a
    judgment call and must be labeled [READ], never [MODEL].

    `offered_american` overrides the multiplied payout for SGPs, where the book
    quotes a single correlated price.
    """
    legs = [float(p) for p in leg_prices]
    if leg_fair_probs is None:
        fair = [implied_prob(p) / assumed_overround for p in legs]
        fair_source = (
            f"approximated — each leg devigged against an assumed "
            f"{assumed_overround:.4f} two-way overround. Pass real devigged "
            f"probabilities for a true number."
        )
    else:
        fair = [float(p) for p in leg_fair_probs]
        fair_source = "devigged"

    if len(fair) != len(legs):
        raise ValueError("leg count and fair-probability count differ")

    independent_p = 1.0
    for p in fair:
        independent_p *= p

    true_p = independent_p * (1.0 + correlation_uplift) if correlation_uplift else independent_p
    true_p = min(true_p, min(fair))  # a parlay can't beat its likeliest leg

    payout_dec = (
        american_to_decimal(offered_american) if offered_american is not None else parlay_decimal(legs)
    )
    implied = 1.0 / payout_dec
    parlay_ev = true_p * payout_dec - 1.0

    # The comparison that matters: what the book holds if you bet these same
    # legs straight instead of stapling them together.
    leg_evs = [ev(f, american_to_decimal(l)) for f, l in zip(fair, legs)]
    straight_hold = -sum(leg_evs) / len(leg_evs)

    return {
        "legs": legs,
        "leg_fair_probs": fair,
        "leg_fair_prob_source": fair_source,
        "independent_true_prob": independent_p,
        "correlation_uplift": correlation_uplift,
        "true_prob": true_p,
        "offered_decimal": payout_dec,
        "offered_american": decimal_to_american(payout_dec),
        "implied_prob": implied,
        "ev": parlay_ev,
        "book_hold": 1.0 - true_p / implied if implied > 0 else float("nan"),
        "is_bet": parlay_ev >= MIN_EV,
        "n_legs": len(legs),
        "leg_evs": leg_evs,
        "hold_if_bet_straight": straight_hold,
        "hold_multiple": (
            (1.0 - true_p / implied) / straight_hold
            if straight_hold > _EPS and implied > 0
            else float("nan")
        ),
    }


def round_robin(
    leg_prices: Sequence[float],
    leg_fair_probs: Sequence[float],
    size: int,
    *,
    stake_per_combo: float = 1.0,
) -> dict:
    """
    Round-robin: every `size`-leg combination of the legs, bet separately.

    Reduces variance versus one big parlay because one dead leg doesn't kill the
    whole ticket. It does *not* improve EV — if the legs are -EV, every combo is
    -EV and you have simply bought more of them. Say that when you present one.
    """
    n = len(leg_prices)
    if not (1 <= size <= n):
        raise ValueError(f"round-robin size {size} invalid for {n} legs")

    combos = []
    total_ev = 0.0
    for idx in itertools.combinations(range(n), size):
        pr = [leg_prices[i] for i in idx]
        fp = [leg_fair_probs[i] for i in idx]
        a = parlay_analysis(pr, fp)
        a["leg_indexes"] = list(idx)
        combos.append(a)
        total_ev += a["ev"] * stake_per_combo

    n_combos = len(combos)
    return {
        "size": size,
        "n_combos": n_combos,
        "total_risk": n_combos * stake_per_combo,
        "stake_per_combo": stake_per_combo,
        "total_ev": total_ev,
        "ev_per_unit_risked": total_ev / (n_combos * stake_per_combo) if n_combos else 0.0,
        "combos": combos,
        "note": (
            "Round-robins cut variance, not hold. If the straight parlay is -EV, "
            "so is every combination in here."
        ),
    }


# ---------------------------------------------------------------------------
# Book selection and CLV
# ---------------------------------------------------------------------------


def sharp_anchor(book_prices: dict[str, float]) -> dict:
    """
    Pick the price to estimate *from*.

    Priority: Pinnacle, then Circa, then BetOnline/Bookmaker tier, then the
    median across all books. Soft books never anchor — they're what we bet into.

    `book_prices` maps a book key to that book's American price for one outcome.
    """
    if not book_prices:
        return {"anchor": None, "price": None, "tier": "none", "note": "no prices supplied"}

    norm = {k.lower().replace(" ", "").replace("_", ""): (k, v) for k, v in book_prices.items()}
    for want in SHARP_BOOK_PRIORITY:
        key = want.replace("_", "")
        if key in norm:
            orig, price = norm[key]
            return {
                "anchor": orig,
                "price": price,
                "tier": "sharp",
                "note": f"anchored on {orig}",
            }

    values = sorted(float(v) for v in book_prices.values())
    mid = len(values) // 2
    median = values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2.0
    return {
        "anchor": "market_median",
        "price": median,
        "tier": "median",
        "note": (
            "No sharp book in this market — anchored on the median of "
            f"{len(values)} books. Lower confidence accordingly."
        ),
    }


def clv(taken_american: float, closing_american: float) -> dict:
    """
    Closing line value on a single bet.

    `pct` is the honest measure: how much more the bet was worth at the price we
    took than at the close, in probability terms. `cents` is the American-odds
    move, which is what people say out loud but distorts across the +100 line.
    """
    p_taken = implied_prob(taken_american)
    p_close = implied_prob(closing_american)
    beat = p_taken < p_close  # we got a longer price than the close
    return {
        "taken_american": float(taken_american),
        "closing_american": float(closing_american),
        "taken_implied": p_taken,
        "closing_implied": p_close,
        "pct": (p_close - p_taken) / p_taken,
        "cents": float(taken_american) - float(closing_american),
        "beat_close": beat,
        "ev_at_close": ev(p_close, american_to_decimal(taken_american)),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _fmt_am(a: float) -> str:
    return f"{a:+.0f}" if float(a).is_integer() else f"{a:+.1f}"


def _cmd_devig(args) -> int:
    prices = args.prices
    spread = devig_spread(prices)
    method = args.method or default_method(len(prices))
    fair = devig(prices, method)

    print(f"market      : {len(prices)}-way — {' / '.join(_fmt_am(p) for p in prices)}")
    print(f"overround   : {overround(prices):.4f}   hold: {hold(prices):.2%}")
    print(f"method      : {method} (house default for {len(prices)}-way)")
    print()
    print(f"{'outcome':<9}{'raw':>9}{'fair':>9}{'fair line':>12}")
    for i, (px, fp) in enumerate(zip(prices, fair)):
        print(f"{i:<9}{implied_prob(px):>9.4f}{fp:>9.4f}{_fmt_am(prob_to_american(fp)):>12}")
    print()
    print("all methods:")
    for m, probs in spread["by_method"].items():
        flag = "  <- used" if m == method else ""
        print(f"  {m:<16}" + "  ".join(f"{p:.4f}" for p in probs) + flag)
    w = spread["widest_spread"]
    if spread["meaningful"]:
        print(
            f"\n  methods disagree by {w:.4f} ({w * 100:.2f} pts of probability) — "
            "quote a RANGE, not a point estimate."
        )
    else:
        print(f"\n  methods agree within {w:.4f} — point estimate is fine.")

    if args.offered is not None:
        print()
        edge = price_edge(fair[args.outcome], args.offered, method=method)
        print(f"offered     : {_fmt_am(args.offered)} on outcome {args.outcome}")
        print(f"fair        : {_fmt_am(edge.fair_american)}  (p={edge.fair_prob:.4f})")
        print(f"EV          : {edge.ev:+.2%}")
        print(f"stake       : {edge.stake_units}u  (1/{args.divisor:g} Kelly)")
        if edge.note:
            print(f"note        : {edge.note}")
    if args.json:
        print()
        print(json.dumps({"fair": fair, "spread": spread}, indent=2, default=float))
    return 0


def _cmd_ev(args) -> int:
    p = implied_prob(args.fair) if args.fair is not None else args.prob
    if p is None:
        raise SystemExit("give --fair (an American fair price) or --prob")
    edge = price_edge(p, args.offered, divisor=args.divisor, bankroll_units=args.bankroll)
    print(f"fair prob   : {edge.fair_prob:.4f}   ({_fmt_am(edge.fair_american)})")
    print(f"offered     : {_fmt_am(edge.offered_american)}   (decimal {edge.offered_decimal:.4f})")
    print(f"EV          : {edge.ev:+.2%}")
    print(f"kelly       : {edge.kelly_fraction:.4%} of bankroll  (1/{args.divisor:g})")
    print(f"stake       : {edge.stake_units}u")
    print(f"verdict     : {'BET' if edge.is_bet else 'NO BET'}")
    if edge.note:
        print(f"note        : {edge.note}")
    return 0


def _cmd_kelly(args) -> int:
    dec = american_to_decimal(args.odds)
    f = kelly(args.prob, dec, divisor=args.divisor)
    units = round(min(f * args.bankroll, MAX_STAKE_UNITS), 2)
    print(f"prob        : {args.prob:.4f}")
    print(f"odds        : {_fmt_am(args.odds)}  (decimal {dec:.4f})")
    print(f"full kelly  : {kelly(args.prob, dec, divisor=1.0):.4%}")
    print(f"1/{args.divisor:g} kelly : {f:.4%}")
    print(f"stake       : {units}u  (ceiling {MAX_STAKE_UNITS}u)")
    print(f"EV          : {ev(args.prob, dec):+.2%}")
    return 0


def _cmd_parlay(args) -> int:
    fair = args.fair if args.fair else None
    a = parlay_analysis(
        args.prices,
        fair,
        correlation_uplift=args.correlation,
        offered_american=args.offered,
    )
    print(f"legs        : {' / '.join(_fmt_am(p) for p in a['legs'])}")
    print(f"leg fair p  : {' / '.join(f'{p:.4f}' for p in a['leg_fair_probs'])}")
    print(f"             ({a['leg_fair_prob_source']})")
    print(f"independent : {a['independent_true_prob']:.4f}")
    if args.correlation:
        print(f"correlated  : {a['true_prob']:.4f}  (uplift {args.correlation:+.2%} — this is a [READ])")
    print(f"payout      : {_fmt_am(a['offered_american'])}  (decimal {a['offered_decimal']:.4f})")
    print(f"implied     : {a['implied_prob']:.4f}")
    print(f"book hold   : {a['book_hold']:.2%}")
    print(f"EV          : {a['ev']:+.2%}")
    print(f"verdict     : {'BET' if a['is_bet'] else 'NO BET'}")
    print(f"straight    : same legs bet straight hold {a['hold_if_bet_straight']:.2%}")
    if a["hold_multiple"] == a["hold_multiple"]:  # not NaN
        print(f"             parlaying multiplies that by {a['hold_multiple']:.1f}x")
    if not args.correlation and len(args.prices) > 2:
        print(
            "\nnote        : independent legs multiply the hold. "
            f"{len(args.prices)} legs at these prices hands the book {a['book_hold']:.1%} "
            f"instead of {a['hold_if_bet_straight']:.1%}."
        )
    if args.fair is None:
        print(f"\ncaveat      : {a['leg_fair_prob_source']}")
    if args.rr:
        print()
        rr = round_robin(args.prices, a["leg_fair_probs"], args.rr)
        print(f"round robin : by-{args.rr}s — {rr['n_combos']} combos, {rr['total_risk']:.2f}u risked")
        print(f"              EV per unit risked: {rr['ev_per_unit_risked']:+.2%}")
        print(f"              {rr['note']}")
    return 0


def _cmd_hold(args) -> int:
    print(f"overround   : {overround(args.prices):.6f}")
    print(f"hold        : {hold(args.prices):.3%}")
    for i, p in enumerate(args.prices):
        print(f"  outcome {i}: {_fmt_am(p)}  raw p={implied_prob(p):.4f}")
    return 0


def _cmd_clv(args) -> int:
    c = clv(args.taken, args.closed)
    print(f"taken       : {_fmt_am(c['taken_american'])}  (p={c['taken_implied']:.4f})")
    print(f"closed      : {_fmt_am(c['closing_american'])}  (p={c['closing_implied']:.4f})")
    print(f"CLV         : {c['pct']:+.2%}  ({c['cents']:+.0f} cents)")
    print(f"EV at close : {c['ev_at_close']:+.2%}")
    print(f"verdict     : {'BEAT THE CLOSE' if c['beat_close'] else 'lost to the close'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lib.odds", description="The Desk — price math.")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("devig", help="devig a market and optionally price an offer against it")
    d.add_argument("prices", nargs="+", type=float, help="American prices for every outcome")
    d.add_argument("--method", choices=list(_DEVIG_FNS), default=None)
    d.add_argument("--offered", type=float, default=None, help="price you can actually get")
    d.add_argument("--outcome", type=int, default=0, help="which outcome the offer is on")
    d.add_argument("--divisor", type=float, default=DEFAULT_KELLY_DIVISOR)
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=_cmd_devig)

    e = sub.add_parser("ev", help="EV and stake for a fair price vs. an offered price")
    e.add_argument("--fair", type=float, default=None, help="fair price, American")
    e.add_argument("--prob", type=float, default=None, help="fair probability, 0-1")
    e.add_argument("--offered", type=float, required=True)
    e.add_argument("--divisor", type=float, default=DEFAULT_KELLY_DIVISOR)
    e.add_argument("--bankroll", type=float, default=100.0)
    e.set_defaults(func=_cmd_ev)

    k = sub.add_parser("kelly", help="Kelly stake")
    k.add_argument("--prob", type=float, required=True)
    k.add_argument("--odds", type=float, required=True)
    k.add_argument("--divisor", type=float, default=DEFAULT_KELLY_DIVISOR)
    k.add_argument("--bankroll", type=float, default=100.0)
    k.set_defaults(func=_cmd_kelly)

    pl = sub.add_parser("parlay", help="price a parlay honestly")
    pl.add_argument("prices", nargs="+", type=float)
    pl.add_argument("--fair", nargs="+", type=float, default=None, help="devigged leg probs")
    pl.add_argument("--correlation", type=float, default=0.0, help="uplift, e.g. 0.15")
    pl.add_argument("--offered", type=float, default=None, help="SGP quoted price")
    pl.add_argument("--rr", type=int, default=None, help="also show round-robin by-N")
    pl.set_defaults(func=_cmd_parlay)

    h = sub.add_parser("hold", help="book hold on a market")
    h.add_argument("prices", nargs="+", type=float)
    h.set_defaults(func=_cmd_hold)

    c = sub.add_parser("clv", help="closing line value on one bet")
    c.add_argument("--taken", type=float, required=True)
    c.add_argument("--closed", type=float, required=True)
    c.set_defaults(func=_cmd_clv)

    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
