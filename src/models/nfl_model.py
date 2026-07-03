"""NFL prop models: pass/rush/rec yards, receptions, TDs (spec §3).

Volume first, efficiency second. Game script tilts volume: a team
projected to trail passes more; big favorites run more. Weather kills
passing (wind > 15 mph, spec §2.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.models import common

WIND_PASS_PENALTY = 0.93      # applied when wind > 15 mph
SCRIPT_SLOPE = 0.012          # volume tilt per point of spread


def game_script_factor(spread: float | None, is_pass_stat: bool) -> float:
    """spread < 0 = favored. Trailing teams (positive spread) pass more;
    favorites lean run. ±10% at a 8.5-point spread."""
    if spread is None:
        return 1.0
    tilt = SCRIPT_SLOPE * spread            # positive spread -> underdog
    return 1.0 + (tilt if is_pass_stat else -tilt)


@dataclass
class NFLProjection:
    player_id: str
    player_name: str
    market: str
    mean: float
    sample_games: int
    dist: str                      # 'normal' or 'negbin'
    sigma: float | None = None
    inputs: dict = field(default_factory=dict)

    def prob_over(self, line: float) -> float:
        if self.dist == "negbin":
            return common.prob_over_negbin(line, self.mean, dispersion=10.0)
        return common.prob_over_normal(line, self.mean, self.sigma or 1.0)

    def prob_under(self, line: float) -> float:
        return 1.0 - self.prob_over(line)


def _weekly_values(weeks: list[dict], col: str) -> list[float]:
    return [float(w[col]) for w in weeks if w.get(col) is not None]


def project_receiving_yards(weeks: list[dict], spread: float | None = None,
                            windy: bool = False) -> NFLProjection | None:
    """targets x catch rate x yards/catch, script- and weather-adjusted."""
    targets = _weekly_values(weeks, "targets")
    recs = _weekly_values(weeks, "receptions")
    yards = _weekly_values(weeks, "receiving_yards")
    if len(targets) < 4 or sum(targets) == 0:
        return None
    proj_targets = common.weighted_recent_rate(targets, window=10) \
        * game_script_factor(spread, is_pass_stat=True)
    catch_rate = common.regress_to_mean(sum(recs) / sum(targets), int(sum(targets)), 0.65, 25)
    ypc = common.regress_to_mean(
        (sum(yards) / sum(recs)) if sum(recs) else 11.0, int(sum(recs)), 11.0, 20)
    mean = proj_targets * catch_rate * ypc
    if windy:
        mean *= WIND_PASS_PENALTY
    return NFLProjection(
        player_id=weeks[0]["player_id"], player_name=weeks[0].get("player_name") or "",
        market="player_reception_yds", mean=round(mean, 2), sample_games=len(targets),
        dist="normal", sigma=max(12.0, 0.62 * mean),
        inputs={"proj_targets": round(proj_targets, 2), "catch_rate": round(catch_rate, 3),
                "yards_per_catch": round(ypc, 2), "windy": windy})


def project_receptions(weeks: list[dict], spread: float | None = None) -> NFLProjection | None:
    recs = _weekly_values(weeks, "receptions")
    if len(recs) < 4:
        return None
    mean = common.weighted_recent_rate(recs, window=10) \
        * game_script_factor(spread, is_pass_stat=True)
    return NFLProjection(
        player_id=weeks[0]["player_id"], player_name=weeks[0].get("player_name") or "",
        market="player_receptions", mean=round(mean, 2), sample_games=len(recs),
        dist="negbin", inputs={"recent_receptions": round(mean, 2)})


def project_rushing_yards(weeks: list[dict], spread: float | None = None) -> NFLProjection | None:
    carries = _weekly_values(weeks, "carries")
    yards = _weekly_values(weeks, "rushing_yards")
    if len(carries) < 4 or sum(carries) == 0:
        return None
    proj_carries = common.weighted_recent_rate(carries, window=10) \
        * game_script_factor(spread, is_pass_stat=False)
    ypc = common.regress_to_mean(sum(yards) / sum(carries), int(sum(carries)), 4.2, 60)
    mean = proj_carries * ypc
    return NFLProjection(
        player_id=weeks[0]["player_id"], player_name=weeks[0].get("player_name") or "",
        market="player_rush_yds", mean=round(mean, 2), sample_games=len(carries),
        dist="normal", sigma=max(10.0, 0.58 * mean),
        inputs={"proj_carries": round(proj_carries, 2), "ypc": round(ypc, 2)})


def project_passing_yards(weeks: list[dict], spread: float | None = None,
                          windy: bool = False) -> NFLProjection | None:
    yards = _weekly_values(weeks, "passing_yards")
    if len(yards) < 4:
        return None
    mean = common.weighted_recent_rate(yards, window=10) \
        * game_script_factor(spread, is_pass_stat=True)
    if windy:
        mean *= WIND_PASS_PENALTY
    return NFLProjection(
        player_id=weeks[0]["player_id"], player_name=weeks[0].get("player_name") or "",
        market="player_pass_yds", mean=round(mean, 2), sample_games=len(yards),
        dist="normal", sigma=max(30.0, 0.16 * mean),
        inputs={"windy": windy, "spread": spread})


def prob_anytime_td(weeks: list[dict]) -> float | None:
    """TD props: scoring rate -> Poisson P(>=1) (red-zone share proxy, spec §3)."""
    tds = [(w.get("receiving_tds") or 0) + (w.get("rushing_tds") or 0)
           for w in weeks if w.get("week")]
    if len(tds) < 4:
        return None
    lam = common.regress_to_mean(
        common.weighted_recent_rate([float(t) for t in tds], window=12),
        len(tds), 0.35, 8)
    return 1.0 - common.poisson_pmf(0, lam)
