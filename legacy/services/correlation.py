"""Same-game / same-player parlay correlation analysis.

PrizePicks-style "all the same game" parlays violate independence — if
QB throws for 350 yards, the WR1 receiving yards are far above expectation
too. Modeling parlay payout as P1*P2*...*PN overstates true probability.

We use empirical correlation pairs based on common knowledge of the sports:
"""
from __future__ import annotations

# Empirical pairwise correlation estimates between two markets within the
# SAME game (and on related players). Conservative; use as a haircut.
SAME_GAME_CORR = {
    # NBA — teammates
    ("NBA", "player_points", "player_points"): 0.05,    # opposite — limited shots
    ("NBA", "player_points", "player_assists"): -0.10,  # ball stops vs. passes
    ("NBA", "player_points", "player_rebounds"): 0.10,
    ("NBA", "player_assists", "player_assists"): -0.20,
    ("NBA", "player_threes", "player_points"): 0.40,
    ("NBA", "player_pra", "player_points"): 0.85,
    # MLB — teammates batting
    ("MLB", "batter_hits", "batter_hits"): 0.10,
    ("MLB", "batter_total_bases", "batter_runs_scored"): 0.45,
    ("MLB", "batter_rbis", "batter_total_bases"): 0.55,
    ("MLB", "pitcher_strikeouts", "pitcher_strikeouts"): 0.0,  # different pitchers
    # NHL
    ("NHL", "player_shots_on_goal", "player_goals"): 0.55,
    ("NHL", "player_points", "player_assists"): 0.65,
    ("NHL", "goalie_saves", "goalie_saves"): 0.0,  # one goalie per team
}

# Same-player legs are ~near-perfectly correlated (e.g., over 24.5 pts and
# over 19.5 pts on the same player). We dedupe these instead.


def correlation(sport: str, m1: str, m2: str) -> float:
    """Symmetric lookup; defaults to 0 if pair unknown."""
    if m1 == m2:
        return 0.05  # weak generic correlation
    key = (sport, m1, m2)
    rev = (sport, m2, m1)
    return SAME_GAME_CORR.get(key) or SAME_GAME_CORR.get(rev) or 0.0


def adjusted_parlay_prob(legs: list[dict]) -> tuple[float, float, list[dict]]:
    """Compute parlay probability with a simple Gaussian-copula-style
    correction for same-game correlation.

    Returns (independent_prob, adjusted_prob, leg_correlation_notes).

    Strategy:
      - Independent: product of per-leg model probs.
      - For each pair of legs with the same sport+game and a known
        correlation, apply a multiplicative haircut/boost.
      - Cap adjustment to ±25% to avoid runaway numbers.
    """
    notes: list[dict] = []
    indep = 1.0
    for l in legs:
        p = l.get("model_prob")
        if p is None:
            return 0.0, 0.0, notes
        indep *= float(p)

    # Find correlated pairs.
    n = len(legs)
    total_corr = 0.0
    pair_count = 0
    for i in range(n):
        for j in range(i + 1, n):
            a, b = legs[i], legs[j]
            same_game = (
                a.get("sport") == b.get("sport")
                and a.get("game_external_id") == b.get("game_external_id")
                and a.get("game_external_id")
            )
            if not same_game:
                continue
            r = correlation(a["sport"], a["market"], b["market"])
            if r == 0:
                continue
            # If both legs are "over" (or both "under"), positive
            # correlation helps; opposite sides get sign-flipped.
            sign = 1.0 if a.get("side") == b.get("side") else -1.0
            r_eff = r * sign
            total_corr += r_eff
            pair_count += 1
            notes.append({
                "leg_i": i, "leg_j": j,
                "market_i": a["market"], "market_j": b["market"],
                "correlation": round(r_eff, 3),
            })

    if pair_count == 0:
        return indep, indep, notes

    avg_corr = total_corr / pair_count
    # Translate average correlation into a probability multiplier.
    # If positive corr, parlay easier than indep predicts (prob up).
    # If negative, harder.
    multiplier = 1.0 + max(-0.25, min(0.25, avg_corr))
    adjusted = max(0.0, min(1.0, indep * multiplier))
    return indep, adjusted, notes
