"""
Drive-level Monte Carlo for football game outcomes.

Two design choices that matter, both required to price a game honestly:

1. **Scores are built from drives, not drawn from a continuous distribution.**
   Points arrive in 3s and 7s, so simulating drive outcomes reproduces the
   real margin distribution — the lumps on 3, 7, 10 and 14 that make key
   numbers worth paying for. A normal draw on margin smooths those away and
   will misprice every half point you buy.

2. **The two teams are correlated, not independent.** A game-level pace factor
   drives both teams' possession counts, and a shared game-script factor pushes
   scoring the same direction. Simulating teams independently understates the
   variance of the TOTAL badly, because real shootouts and real slogs are
   joint events.

Stdlib only.
"""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass, field


@dataclass
class TeamModel:
    """One team's scoring profile, in points per drive."""

    name: str
    points_per_drive: float
    #: Share of scoring drives that end in a TD rather than a FG. League ~0.60.
    td_share: float = 0.60
    #: Per-drive turnover rate. Informational; already inside points_per_drive.
    turnover_rate: float = 0.11

    def drive_probs(self) -> tuple[float, float]:
        """Solve for (P(TD), P(FG)) that produce the target points per drive."""
        # p_td*6.95 + p_fg*3 = ppd, with p_td/(p_td+p_fg) = td_share
        # => p_td = s*k, p_fg = (1-s)*k  for scoring rate k
        s = self.td_share
        pts_per_score = s * 6.95 + (1 - s) * 3.0
        k = self.points_per_drive / pts_per_score
        k = min(k, 0.95)
        return s * k, (1 - s) * k


@dataclass
class GameSim:
    home: TeamModel
    away: TeamModel
    #: Mean offensive possessions per team. NFL ~11.
    base_drives: float = 11.0
    #: SD of the game-level pace factor (multiplies both teams' drives).
    pace_sd: float = 0.09
    #: SD of a shared scoring-environment factor. Creates score correlation.
    env_sd: float = 0.16
    #: SD of each team's own performance factor.
    team_sd: float = 0.22
    #: Floor on simulated drives. None => scaled off base_drives, so a
    #: half-game sim is not silently given a full game's possessions.
    min_drives: int | None = None
    seed: int | None = 20260917
    results: list[tuple[int, int]] = field(default_factory=list)

    def run(self, n: int = 50000) -> "GameSim":
        rng = random.Random(self.seed)
        floor = self.min_drives if self.min_drives is not None else max(
            2, int(round(self.base_drives * 0.64)))
        h_td, h_fg = self.home.drive_probs()
        a_td, a_fg = self.away.drive_probs()
        out = []
        for _ in range(n):
            pace = max(0.6, rng.gauss(1.0, self.pace_sd))
            env = max(0.4, rng.gauss(1.0, self.env_sd))
            drives = max(floor, int(round(self.base_drives * pace)))

            def score(p_td, p_fg):
                mult = env * max(0.3, rng.gauss(1.0, self.team_sd))
                td = min(p_td * mult, 0.75)
                fg = min(p_fg * mult, 0.75 - td)
                pts = 0
                for _ in range(drives):
                    r = rng.random()
                    if r < td:
                        pts += 7 if rng.random() < 0.94 else 6   # XP occasionally missed / 2pt
                    elif r < td + fg:
                        pts += 3
                return pts

            out.append((score(h_td, h_fg), score(a_td, a_fg)))
        self.results = out
        return self

    # --- readouts ----------------------------------------------------------

    def _margins(self):   return [h - a for h, a in self.results]
    def _totals(self):    return [h + a for h, a in self.results]

    def summary(self) -> dict:
        h = [x[0] for x in self.results]; a = [x[1] for x in self.results]
        m = self._margins(); t = self._totals()
        home_win = sum(1 for x in m if x > 0) + 0.5 * sum(1 for x in m if x == 0)
        return {
            "n": len(self.results),
            "home_mean": statistics.fmean(h), "home_median": statistics.median(h),
            "away_mean": statistics.fmean(a), "away_median": statistics.median(a),
            "margin_mean": statistics.fmean(m), "margin_median": statistics.median(m),
            "total_mean": statistics.fmean(t), "total_median": statistics.median(t),
            "total_sd": statistics.pstdev(t), "margin_sd": statistics.pstdev(m),
            "home_win_prob": home_win / len(m),
            "fair_spread": -statistics.fmean(m),   # negative = home favored
        }

    def p_cover(self, home_spread: float) -> dict:
        """home_spread negative = home laying points."""
        m = self._margins()
        need = -home_spread
        w = sum(1 for x in m if x > need); l = sum(1 for x in m if x < need)
        p = sum(1 for x in m if x == need)
        return {"home_cover": w / (w + l) if w + l else 0.0,
                "push": p / len(m), "raw_home": w / len(m)}

    def p_over(self, line: float) -> dict:
        t = self._totals()
        o = sum(1 for x in t if x > line); u = sum(1 for x in t if x < line)
        p = sum(1 for x in t if x == line)
        return {"over": o / (o + u) if o + u else 0.0,
                "push": p / len(t), "raw_over": o / len(t)}

    def key_numbers(self, values) -> dict:
        m = [abs(x) for x in self._margins()]
        return {v: sum(1 for x in m if x == v) / len(m) for v in values}

    def total_mass(self, values) -> dict:
        t = self._totals()
        return {v: sum(1 for x in t if x == v) / len(t) for v in values}

    def team_total(self, side: str, line: float) -> float:
        idx = 0 if side == "home" else 1
        s = [x[idx] for x in self.results]
        o = sum(1 for x in s if x > line); u = sum(1 for x in s if x < line)
        return o / (o + u) if o + u else 0.0


def first_half(game: "GameSim", share: float = 0.49) -> "GameSim":
    """Build a first-half version of a full-game sim.

    NFL scoring is not evenly split across halves — the second half carries
    slightly more, because Q4 is the highest-scoring quarter and Q1 the
    lowest. `share` is the fraction of full-game points that land in the
    first half; drives are split evenly, so the per-drive rate is scaled by
    ``2 * share`` to hit the target.
    """
    k = 2.0 * share
    return GameSim(
        home=TeamModel(game.home.name, game.home.points_per_drive * k,
                       game.home.td_share, game.home.turnover_rate),
        away=TeamModel(game.away.name, game.away.points_per_drive * k,
                       game.away.td_share, game.away.turnover_rate),
        base_drives=game.base_drives * 0.5,
        pace_sd=game.pace_sd,
        # Half-game samples are noisier per drive but share the same game-level
        # environment, so the environment SD stays put and the team SD widens.
        env_sd=game.env_sd,
        team_sd=game.team_sd * 1.15,
        seed=None if game.seed is None else game.seed + 1,
    )


# --- CLI -------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    import argparse

    from lib.odds import prob_to_american

    ap = argparse.ArgumentParser(
        prog="lib.simulate",
        description="Drive-level Monte Carlo for a football game. Feed it each team's "
                    "projected points, it gives back the margin and total distributions.",
    )
    ap.add_argument("--home", required=True, help="home team name")
    ap.add_argument("--away", required=True, help="away team name")
    ap.add_argument("--home-points", type=float, required=True, help="projected home points")
    ap.add_argument("--away-points", type=float, required=True, help="projected away points")
    ap.add_argument("--drives", type=float, default=11.0, help="drives per team (default 11)")
    ap.add_argument("--home-td-share", type=float, default=0.60)
    ap.add_argument("--away-td-share", type=float, default=0.60)
    ap.add_argument("--spread", type=float, help="home spread to price, e.g. -4.5")
    ap.add_argument("--total", type=float, help="total to price")
    ap.add_argument("-n", type=int, default=50000, help="iterations (default 50000)")
    ap.add_argument("--seed", type=int, default=20260101)
    ap.add_argument("--half", action="store_true", help="also price the first half")
    a = ap.parse_args(argv)

    g = GameSim(
        home=TeamModel(a.home, a.home_points / a.drives, td_share=a.home_td_share),
        away=TeamModel(a.away, a.away_points / a.drives, td_share=a.away_td_share),
        base_drives=a.drives, env_sd=0.12, team_sd=0.16, pace_sd=0.07, seed=a.seed,
    ).run(a.n)
    s = g.summary()

    print(f"n = {s['n']:,}   drives/team = {a.drives}")
    print(f"  {a.home:<12}{s['home_mean']:>7.2f}")
    print(f"  {a.away:<12}{s['away_mean']:>7.2f}")
    print(f"  total       {s['total_mean']:>7.2f}   (sd {s['total_sd']:.1f})")
    print(f"  fair spread {s['fair_spread']:>+7.2f}   (margin sd {s['margin_sd']:.1f})")
    print(f"  {a.home} win {s['home_win_prob']:.4f}  -> fair ML "
          f"{prob_to_american(s['home_win_prob']):+.0f} / "
          f"{prob_to_american(1 - s['home_win_prob']):+.0f}")

    if a.spread is not None:
        c = g.p_cover(a.spread)
        print(f"\n  {a.home} {a.spread:+.1f}: {c['home_cover']:.4f} "
              f"(fair {prob_to_american(c['home_cover']):+.0f})   "
              f"{a.away} {-a.spread:+.1f}: {1 - c['home_cover']:.4f} "
              f"(fair {prob_to_american(1 - c['home_cover']):+.0f})   push {c['push']:.4f}")
    if a.total is not None:
        o = g.p_over(a.total)
        print(f"  over {a.total}: {o['over']:.4f} (fair {prob_to_american(o['over']):+.0f})   "
              f"under: {1 - o['over']:.4f} (fair {prob_to_american(1 - o['over']):+.0f})   "
              f"push {o['push']:.4f}")

    print("\n  key-number mass |margin|: " +
          "  ".join(f"{k}:{v:.4f}" for k, v in g.key_numbers([3, 4, 6, 7, 10]).items()))

    if a.half:
        h = first_half(g).run(a.n)
        hs = h.summary()
        print(f"\n  1H: {a.home} {hs['home_mean']:.2f}  {a.away} {hs['away_mean']:.2f}  "
              f"total {hs['total_mean']:.2f}  fair spread {hs['fair_spread']:+.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
