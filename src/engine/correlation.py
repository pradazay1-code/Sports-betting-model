"""Same-game correlation checks + PrizePicks/Underdog slip builder (spec §5).

Rules enforced in code:
- never combine negatively correlated legs (QB pass yds + own RB rush yds)
- positively correlated stacks are allowed for lottos but sized DOWN
- max 2 legs from the same game per slip

Combined slip probability uses a Gaussian copula so correlation actually
moves the number instead of naive independence.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

NEGATIVE_BLOCK = -0.15          # corr at/below this blocks the pairing
POSITIVE_FLAG = 0.20            # corr above this flags a stack (size down)
MAX_LEGS_PER_GAME = 2

# heuristic same-game correlations by market pair (same team unless noted)
_PAIR_CORR = {
    frozenset(["player_pass_yds", "player_reception_yds"]): 0.35,
    frozenset(["player_pass_yds", "player_receptions"]): 0.30,
    frozenset(["player_pass_yds", "player_rush_yds"]): -0.20,
    frozenset(["player_rush_yds", "player_reception_yds"]): -0.10,
    frozenset(["player_points", "player_assists"]): -0.10,
    frozenset(["player_points", "player_rebounds"]): 0.05,
    frozenset(["pitcher_strikeouts"]): -0.25,     # two pitchers, same game
}

# DFS pick'em payout multipliers (all legs must hit)
PAYOUTS = {2: 3.0, 3: 5.0, 4: 10.0}


@dataclass
class Leg:
    event_id: str
    market: str
    player: str | None
    side: str
    line: float | None
    model_prob: float
    team: str | None = None


def leg_correlation(a: Leg, b: Leg) -> float:
    """Estimated outcome correlation for two OVER-side legs; opposite sides
    flip the sign. Different games are treated as independent."""
    if a.event_id != b.event_id:
        return 0.0
    if a.player and a.player == b.player:
        base = 0.55                        # same player, different stats
    else:
        key = frozenset([a.market, b.market])
        base = _PAIR_CORR.get(key, 0.0)
        if a.market == b.market and a.market in key and len(key) == 1:
            base = _PAIR_CORR.get(key, 0.0)
    sign = 1.0 if a.side == b.side else -1.0
    return base * sign


def validate_slip(legs: list[Leg]) -> tuple[bool, list[str]]:
    """(allowed, notes). Blocks negative correlation and >2 legs per game."""
    notes: list[str] = []
    games: dict[str, int] = {}
    for leg in legs:
        games[leg.event_id] = games.get(leg.event_id, 0) + 1
    for event_id, n in games.items():
        if n > MAX_LEGS_PER_GAME:
            return False, [f"{n} legs from game {event_id[:8]} (max {MAX_LEGS_PER_GAME})"]
    for i, a in enumerate(legs):
        for b in legs[i + 1:]:
            rho = leg_correlation(a, b)
            if rho <= NEGATIVE_BLOCK:
                return False, [f"negatively correlated: {a.player or a.market} x "
                               f"{b.player or b.market} (rho {rho:+.2f})"]
            if rho >= POSITIVE_FLAG:
                notes.append(f"positive stack {a.player or a.market} x "
                             f"{b.player or b.market} (rho {rho:+.2f}) — size DOWN")
    return True, notes


def combined_probability(legs: list[Leg], n_sims: int = 20_000, seed: int = 7) -> float:
    """P(all legs hit) via Gaussian copula over pairwise correlations."""
    n = len(legs)
    if n == 1:
        return legs[0].model_prob
    corr = [[leg_correlation(legs[i], legs[j]) if i != j else 1.0
             for j in range(n)] for i in range(n)]
    # thresholds: leg hits when its standard normal draw < Phi^-1(p)
    from statistics import NormalDist
    z_thresholds = [NormalDist().inv_cdf(max(1e-6, min(1 - 1e-6, leg.model_prob)))
                    for leg in legs]
    chol = _cholesky_psd(corr)
    rng = random.Random(seed)
    hits = 0
    for _ in range(n_sims):
        z = [rng.gauss(0, 1) for _ in range(n)]
        correlated = [sum(chol[i][k] * z[k] for k in range(i + 1)) for i in range(n)]
        if all(c < t for c, t in zip(correlated, z_thresholds)):
            hits += 1
    return hits / n_sims


def _cholesky_psd(matrix: list[list[float]]) -> list[list[float]]:
    """Cholesky with a tiny diagonal bump for near-PSD heuristic matrices."""
    n = len(matrix)
    a = [row[:] for row in matrix]
    for i in range(n):
        a[i][i] += 1e-9
    chol = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(chol[i][k] * chol[j][k] for k in range(j))
            if i == j:
                chol[i][j] = math.sqrt(max(1e-12, a[i][i] - s))
            else:
                chol[i][j] = (a[i][j] - s) / chol[j][j]
    return chol


def build_slips(edges: list, max_slips: int = 3) -> list[dict]:
    """Best 2-leg pick'em slips from surfaced prop edges (spec §6 slip of the day).

    Slip EV = combined prob x payout - 1; only slips beating the breakeven
    (1/payout) with margin are returned, best first.
    """
    legs = [Leg(event_id=e.event_id, market=e.market, player=e.player,
                side=e.side, line=e.line, model_prob=e.model_prob)
            for e in edges if e.surface and e.player]
    slips = []
    payout = PAYOUTS[2]
    for i, a in enumerate(legs):
        for b in legs[i + 1:]:
            ok, notes = validate_slip([a, b])
            if not ok:
                continue
            p = combined_probability([a, b])
            ev = p * payout - 1.0
            if ev <= 0.04:
                continue
            slips.append({"legs": [a, b], "combined_prob": round(p, 4),
                          "breakeven": round(1 / payout, 4),
                          "ev": round(ev, 4), "notes": notes,
                          "sized_down": bool(notes)})
    slips.sort(key=lambda s: s["ev"], reverse=True)
    return slips[:max_slips]
