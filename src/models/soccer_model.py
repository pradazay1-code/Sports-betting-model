"""Soccer prop models: shots, SOT, anytime scorer, cards (spec §3).

All props modeled on 90 minutes only — books grade 90', not 120'.
Game state matters: chasing teams shoot more, tied to match odds.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.models import common

LEAGUE_CARDS_PER_GAME = 4.4       # both teams, top leagues baseline
CARD_PER_FOUL = 0.18              # league-average booking rate per foul


def game_state_factor(win_prob: float | None) -> float:
    """Underdogs chase -> more shots; heavy favorites control -> slight boost
    too (territory). Mild U-shape centered below 0.5."""
    if win_prob is None:
        return 1.0
    return 1.0 + 0.12 * (0.5 - win_prob)


@dataclass
class SoccerProjection:
    player: str
    market: str
    mean: float
    minutes: float
    inputs: dict = field(default_factory=dict)

    def prob_over(self, line: float) -> float:
        return common.prob_over_negbin(line, self.mean, dispersion=6.0)

    def prob_under(self, line: float) -> float:
        return 1.0 - self.prob_over(line)


def project_shots(blended: dict, expected_minutes: float = 90.0,
                  opp_suppression: float = 1.0, win_prob: float | None = None,
                  stat: str = "shots_p90") -> SoccerProjection | None:
    """per-90 rate x minutes x opponent shot suppression x game state."""
    rate = blended.get(stat)
    if rate is None:
        return None
    minutes = min(expected_minutes, 90.0)          # 90' only
    mean = rate * (minutes / 90.0) * opp_suppression * game_state_factor(win_prob)
    market = "player_shots" if stat == "shots_p90" else "player_shots_on_target"
    return SoccerProjection(
        player=blended["player"], market=market, mean=round(mean, 3), minutes=minutes,
        inputs={"rate_p90": rate, "opp_suppression": opp_suppression,
                "game_state": round(game_state_factor(win_prob), 3),
                "contexts": blended.get("contexts_used")})


def prob_anytime_scorer(blended: dict, expected_minutes: float = 90.0,
                        finishing_ratio: float = 1.0,
                        opp_suppression: float = 1.0) -> float | None:
    """xG per 90 x minutes x finishing regression -> Poisson P(>=1) (spec §3).

    finishing_ratio regresses hot/cold finishing toward 1.0 upstream; pass
    the regressed value, not raw goals/xG.
    """
    xg = blended.get("xg_p90")
    if xg is None:
        return None
    lam = xg * (min(expected_minutes, 90.0) / 90.0) * finishing_ratio * opp_suppression
    if blended.get("penalty_duty"):
        lam += 0.05                                # pen takers: ~0.05 xG/90 bonus
    return 1.0 - common.poisson_pmf(0, lam)


def prob_card(blended: dict, referee_cards_per_game: float | None = None,
              tension: float = 1.0, expected_minutes: float = 90.0) -> float | None:
    """player foul rate x referee tendency x match tension index (spec §3).

    tension: 1.0 normal, up to ~1.3 for rivalry/elimination stakes.
    """
    fouls = blended.get("fouls_p90")
    if fouls is None:
        return None
    ref_factor = (referee_cards_per_game / LEAGUE_CARDS_PER_GAME) \
        if referee_cards_per_game else 1.0
    lam = fouls * (min(expected_minutes, 90.0) / 90.0) * CARD_PER_FOUL \
        * ref_factor * tension
    return 1.0 - common.poisson_pmf(0, lam)
