"""NBA prop models: pts / reb / ast / 3PM / PRA (spec §3).

Chain: minutes model -> per-minute rates -> opponent/pace adjust ->
distribution. Minutes projection is 70% of NBA props, so it comes first
and every projection exposes its minutes assumption for the research pass.

PRA uses Monte Carlo with correlated components (pts-reb correlation sign
differs for guards vs bigs).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from src.models import common

BLOWOUT_SPREAD = 12.0        # |spread| above this trims rotation minutes
BLOWOUT_TRIM = 0.92
B2B_TRIM = 0.97
MARKETS = {                  # market -> (stat column, distribution)
    "player_points": ("pts", "normal"),
    "player_rebounds": ("reb", "negbin"),
    "player_assists": ("ast", "negbin"),
    "player_threes": ("fg3m", "poisson"),
}


def project_minutes(games: list[dict], spread: float | None = None,
                    back_to_back: bool = False, usage_bump: float = 1.0) -> float:
    """Decay-weighted recent minutes with blowout / b2b / injury-bump context."""
    minutes = [g["minutes"] for g in games if g.get("minutes")]
    if not minutes:
        raise ValueError("no minutes history")
    mu = common.weighted_recent_rate(minutes, window=12)
    if spread is not None and abs(spread) > BLOWOUT_SPREAD:
        mu *= BLOWOUT_TRIM
    if back_to_back:
        mu *= B2B_TRIM
    return mu * usage_bump


@dataclass
class NBAProjection:
    player_id: int
    player_name: str
    market: str
    mean: float
    minutes: float
    sample_games: int
    inputs: dict = field(default_factory=dict)

    def prob_over(self, line: float) -> float:
        stat, dist = None, MARKETS.get(self.market, (None, "normal"))[1]
        if dist == "poisson":
            return common.prob_over_poisson(line, self.mean)
        if dist == "negbin":
            return common.prob_over_negbin(line, self.mean, dispersion=8.0)
        sigma = max(3.0, 0.55 * self.mean ** 0.85)   # empirical NBA scoring spread
        return common.prob_over_normal(line, self.mean, sigma)

    def prob_under(self, line: float) -> float:
        return 1.0 - self.prob_over(line)


def project_stat(games: list[dict], market: str, minutes: float,
                 defense_factor: float = 1.0, pace_factor: float = 1.0) -> NBAProjection | None:
    """games: most recent first from nba.player_recent_games()."""
    stat_col = MARKETS[market][0]
    usable = [g for g in games if g.get("minutes") and g.get(stat_col) is not None]
    if len(usable) < 5:
        return None
    per_min = [g[stat_col] / g["minutes"] for g in usable]
    rate = common.weighted_recent_rate(per_min, window=15)
    mean = rate * minutes * defense_factor * pace_factor
    return NBAProjection(
        player_id=usable[0]["player_id"],
        player_name=usable[0].get("player_name") or str(usable[0]["player_id"]),
        market=market, mean=round(mean, 3), minutes=round(minutes, 2),
        sample_games=len(usable),
        inputs={"per_min_rate": round(rate, 4), "projected_minutes": round(minutes, 2),
                "defense_factor": round(defense_factor, 3),
                "pace_factor": round(pace_factor, 3)},
    )


def pts_reb_correlation(games: list[dict]) -> float:
    """Empirical pts-reb correlation from the player's own history (spec §3)."""
    pairs = [(g["pts"], g["reb"]) for g in games
             if g.get("pts") is not None and g.get("reb") is not None]
    if len(pairs) < 8:
        return 0.0
    n = len(pairs)
    mx = sum(p for p, _ in pairs) / n
    my = sum(r for _, r in pairs) / n
    cov = sum((p - mx) * (r - my) for p, r in pairs) / n
    sx = (sum((p - mx) ** 2 for p, _ in pairs) / n) ** 0.5
    sy = (sum((r - my) ** 2 for _, r in pairs) / n) ** 0.5
    if sx == 0 or sy == 0:
        return 0.0
    return max(-0.9, min(0.9, cov / (sx * sy)))


def prob_over_pra(games: list[dict], line: float, minutes: float,
                  defense_factor: float = 1.0, n_sims: int = 10_000,
                  seed: int = 7) -> float | None:
    """PRA via Monte Carlo with correlated pts/reb (ast drawn independently)."""
    projs = {}
    for market in ("player_points", "player_rebounds", "player_assists"):
        p = project_stat(games, market, minutes, defense_factor)
        if p is None:
            return None
        projs[market] = p
    rho = pts_reb_correlation(games)
    mu_p, mu_r, mu_a = (projs[m].mean for m in
                        ("player_points", "player_rebounds", "player_assists"))
    sd_p = max(3.0, 0.55 * mu_p ** 0.85)
    sd_r, sd_a = max(1.5, mu_r * 0.45), max(1.2, mu_a * 0.45)
    rng = random.Random(seed)
    hits = 0
    for _ in range(n_sims):
        z1, z2 = rng.gauss(0, 1), rng.gauss(0, 1)
        z2 = rho * z1 + (1 - rho ** 2) ** 0.5 * z2   # correlate reb with pts
        pts = max(0.0, mu_p + sd_p * z1)
        reb = max(0.0, mu_r + sd_r * z2)
        ast = max(0.0, rng.gauss(mu_a, sd_a))
        if pts + reb + ast > line:
            hits += 1
    return hits / n_sims
