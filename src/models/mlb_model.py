"""MLB prop models: strikeouts (priority #1 per spec §3) and NRFI.

K props: lambda = regressed pitcher K% x opponent-lineup K% adjustment
x expected batters faced. Probabilities via Poisson. Every projection
returns its inputs so the rundown can trace each number to a source
(honesty layer, spec §0.4).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.ingest import mlb
from src.models import common

# League baselines — update yearly alongside park factors (spec §2.2).
LEAGUE_K_RATE = 0.222          # K per plate appearance
K_REGRESSION_BF = 200          # regression weight in batters faced (spec §3 'k')
OPP_ADJ_POWER = 0.7            # dampen noisy opponent samples
MIN_STARTS = 3                 # below this we refuse to project


@dataclass
class KProjection:
    player_id: int
    player_name: str
    lam: float                  # projected strikeouts
    sample_games: int
    inputs: dict = field(default_factory=dict)

    def prob_over(self, line: float) -> float:
        return common.prob_over_poisson(line, self.lam)

    def prob_under(self, line: float) -> float:
        return 1.0 - self.prob_over(line)


def project_strikeouts(pitcher_games: list[dict], opp_k_rate: float | None,
                       league_k_rate: float = LEAGUE_K_RATE) -> KProjection | None:
    """pitcher_games: most recent first, from mlb.pitcher_recent_games()."""
    games = [g for g in pitcher_games
             if g.get("batters_faced") and g.get("strikeouts") is not None]
    if len(games) < MIN_STARTS:
        return None

    total_bf = sum(g["batters_faced"] for g in games)
    total_k = sum(g["strikeouts"] for g in games)
    raw_k_rate = total_k / total_bf

    # decay-weighted per-game K rate captures current form; season rate is
    # the stabilizer; then regress the blend toward league by sample size
    recent_k_rate = common.weighted_recent_rate(
        [g["strikeouts"] / g["batters_faced"] for g in games])
    blended = 0.6 * recent_k_rate + 0.4 * raw_k_rate
    k_rate = common.regress_to_mean(blended, total_bf, league_k_rate, K_REGRESSION_BF)

    opp_adj = common.opponent_adjustment(opp_k_rate, league_k_rate, OPP_ADJ_POWER) \
        if opp_k_rate else 1.0

    expected_bf = common.weighted_recent_rate(
        [float(g["batters_faced"]) for g in games], window=10)

    lam = k_rate * opp_adj * expected_bf
    return KProjection(
        player_id=games[0]["player_id"],
        player_name=games[0].get("player_name") or str(games[0]["player_id"]),
        lam=round(lam, 3),
        sample_games=len(games),
        inputs={
            "recent_k_rate": round(recent_k_rate, 4),
            "season_k_rate": round(raw_k_rate, 4),
            "regressed_k_rate": round(k_rate, 4),
            "opp_k_rate": opp_k_rate,
            "opp_adjustment": round(opp_adj, 4),
            "expected_batters_faced": round(expected_bf, 2),
            "total_bf_sample": total_bf,
        },
    )


def project_game_strikeouts(conn, game: dict, season: int) -> list[KProjection]:
    """K projections for both probable starters of one mlb_games row."""
    out = []
    matchups = [
        (game.get("home_probable_id"), game.get("away_team_id")),   # home P vs away lineup
        (game.get("away_probable_id"), game.get("home_team_id")),   # away P vs home lineup
    ]
    for pitcher_id, opp_team_id in matchups:
        if not pitcher_id:
            continue
        games = mlb.pitcher_recent_games(conn, pitcher_id)
        if not games:
            continue
        hand = games[0].get("hand") or "R"
        opp_k = mlb.team_k_rate(conn, opp_team_id, hand, season) if opp_team_id else None
        proj = project_strikeouts(games, opp_k)
        if proj:
            out.append(proj)
    return out


# ----------------------------------------------------------------- NRFI

def clean_first_probability(first_inning_runs_allowed: list[int]) -> float:
    """P(pitcher posts a scoreless 1st), regressed toward league (~73%)."""
    if not first_inning_runs_allowed:
        return 0.73
    clean = sum(1 for r in first_inning_runs_allowed if r == 0)
    return common.regress_to_mean(clean / len(first_inning_runs_allowed),
                                  len(first_inning_runs_allowed), 0.73, 12)


def nrfi_probability(p_home_clean: float, p_away_clean: float,
                     venue: str | None = None) -> float:
    """P(no run in the 1st) = P(A clean) x P(B clean), park-adjusted (spec §3)."""
    park = mlb.PARK_FACTORS.get(venue or "", 1.0)
    # park factor scales run environment; approximate its effect on the
    # joint no-run prob by exponentiating with the run factor
    return (p_home_clean * p_away_clean) ** park
