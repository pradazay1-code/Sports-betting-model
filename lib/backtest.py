"""
Historical validation and the statistics of edge detection.

This module exists to answer one question honestly: **is this edge real, or is it
luck?** That question has a mathematical answer, and the answer is almost always
"we can't tell yet" — because the sample sizes required to distinguish a real
betting edge from noise are far larger than anyone's actual bet history.

Stdlib only, so it runs anywhere. Sample sizes here are small enough that a
pure-Python Monte Carlo is instant.

CLI:
    python3 -m lib.backtest breakeven --odds -110
    python3 -m lib.backtest sample-size --roi 0.05 --odds -110
    python3 -m lib.backtest drawdown --prob 0.55 --odds -110 --bets 500
    python3 -m lib.backtest streak --prob 0.55 --bets 500
    python3 -m lib.backtest evaluate            # backtests your own bets.db
    python3 -m lib.backtest reality-check --record 12-3
"""

from __future__ import annotations

import argparse
import math
import random
import statistics
from dataclasses import dataclass
from typing import Sequence

from lib.odds import american_to_decimal, implied_prob

# Standard normal quantiles, so we don't need scipy.
Z = {0.80: 0.8416, 0.90: 1.2816, 0.95: 1.6449, 0.975: 1.9600, 0.99: 2.3263}


def _z(p: float) -> float:
    """Inverse normal CDF, Acklam's rational approximation. Good to ~1e-9."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0,1)")
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# ---------------------------------------------------------------------------
# Breakeven and required edge
# ---------------------------------------------------------------------------


def breakeven_rate(american: float) -> float:
    """The hit rate that makes a price break even. -110 needs 52.38%."""
    return implied_prob(american)


def profit_per_bet(prob: float, american: float) -> tuple[float, float]:
    """
    Mean and standard deviation of profit per 1u bet.

    Win pays `b` units, a loss costs 1. This variance is the reason betting
    takes so long to evaluate: at -110 the per-bet standard deviation is ~0.95u
    while a *good* edge is worth 0.05u. The noise is nineteen times the signal.
    """
    b = american_to_decimal(american) - 1.0
    mean = prob * b - (1.0 - prob)
    second = prob * b * b + (1.0 - prob)
    var = second - mean * mean
    return mean, math.sqrt(max(var, 0.0))


def required_sample_size(
    true_prob: float,
    american: float = -110,
    *,
    alpha: float = 0.05,
    power: float = 0.80,
) -> dict:
    """
    How many bets to prove an edge is real rather than luck.

    One-sided test of "ROI > 0" at the given significance and power:

        n = (z_alpha + z_beta)^2 * sigma^2 / mu^2

    The answer is the single most clarifying number in sports betting. A 5% ROI
    bettor — which is genuinely excellent, better than most professionals —
    needs on the order of **two thousand bets** before the record itself proves
    anything. Anyone claiming a verified edge off 40 picks is describing noise.
    """
    mu, sigma = profit_per_bet(true_prob, american)
    if mu <= 0:
        return {
            "true_prob": true_prob,
            "roi": mu,
            "n_required": None,
            "note": "No edge to detect — this price is break-even or worse at that hit rate.",
        }
    za, zb = _z(1 - alpha), _z(power)
    n = ((za + zb) ** 2) * (sigma**2) / (mu**2)
    return {
        "true_prob": true_prob,
        "breakeven_prob": breakeven_rate(american),
        "edge_pct_points": (true_prob - breakeven_rate(american)) * 100,
        "roi": mu,
        "sd_per_bet": sigma,
        "signal_to_noise": mu / sigma,
        "n_required": math.ceil(n),
        "alpha": alpha,
        "power": power,
    }


def roi_significance(profit_units: float, staked_units: float, n_bets: int, sd_per_bet: float | None = None) -> dict:
    """
    Is this ROI distinguishable from zero?

    Uses the observed record. `p_value` is one-sided: the probability of a
    result this good or better from a true zero-edge bettor. Above 0.05 means
    the record is consistent with having no edge at all.
    """
    if n_bets < 2 or staked_units <= 0:
        return {"n_bets": n_bets, "conclusive": False,
                "note": "Not enough bets to say anything."}
    roi = profit_units / staked_units
    sd = sd_per_bet if sd_per_bet is not None else 0.95  # typical at -110
    se = sd / math.sqrt(n_bets)
    mean_per_bet = profit_units / n_bets
    t = mean_per_bet / se if se > 0 else 0.0
    p = 1.0 - _normal_cdf(t)
    return {
        "n_bets": n_bets,
        "roi": roi,
        "mean_per_bet": mean_per_bet,
        "std_error": se,
        "t_stat": t,
        "p_value": p,
        "significant_at_05": p < 0.05,
        "conclusive": p < 0.05 or p > 0.95,
        "ci95_roi": (
            (mean_per_bet - 1.96 * se) * n_bets / staked_units,
            (mean_per_bet + 1.96 * se) * n_bets / staked_units,
        ),
    }


def bootstrap_roi_ci(
    results: Sequence[float],
    *,
    iterations: int = 10000,
    confidence: float = 0.95,
    seed: int | None = 42,
) -> dict:
    """
    Bootstrap confidence interval on ROI from actual per-bet results.

    Resamples the observed bets with replacement. Makes no normality
    assumption, which matters because betting returns are badly skewed —
    especially with plus-money bets in the sample.

    If the interval spans zero, the record does not demonstrate an edge. That is
    the usual outcome and it is not a bug.
    """
    if len(results) < 2:
        return {"n": len(results), "note": "need at least 2 bets"}
    rng = random.Random(seed)
    n = len(results)
    means = []
    for _ in range(iterations):
        means.append(sum(rng.choice(results) for _ in range(n)) / n)
    means.sort()
    lo_i = int((1 - confidence) / 2 * iterations)
    hi_i = int((1 + confidence) / 2 * iterations) - 1
    lo, hi = means[lo_i], means[hi_i]
    return {
        "n": n,
        "observed_mean": statistics.fmean(results),
        "ci_low": lo,
        "ci_high": hi,
        "confidence": confidence,
        "spans_zero": lo <= 0.0 <= hi,
        "iterations": iterations,
    }


# ---------------------------------------------------------------------------
# What a real edge actually feels like
# ---------------------------------------------------------------------------


def drawdown_simulation(
    prob: float,
    american: float = -110,
    *,
    n_bets: int = 500,
    stake: float = 1.0,
    trials: int = 5000,
    seed: int | None = 42,
) -> dict:
    """
    Monte Carlo the experience of betting a real edge.

    This is the antidote to "guaranteed." A genuinely winning bettor still
    spends long stretches underwater, and this quantifies how long and how deep.
    `prob_losing_overall` is the punchline: the chance a *profitable* strategy
    still shows a loss after this many bets.
    """
    rng = random.Random(seed)
    b = american_to_decimal(american) - 1.0
    finals, max_dds, worst_streaks = [], [], []

    for _ in range(trials):
        bankroll = 0.0
        peak = 0.0
        max_dd = 0.0
        streak = 0
        worst = 0
        for _ in range(n_bets):
            if rng.random() < prob:
                bankroll += stake * b
                streak = 0
            else:
                bankroll -= stake
                streak += 1
                worst = max(worst, streak)
            peak = max(peak, bankroll)
            max_dd = max(max_dd, peak - bankroll)
        finals.append(bankroll)
        max_dds.append(max_dd)
        worst_streaks.append(worst)

    finals.sort()
    max_dds.sort()

    def pct(sorted_vals, q):
        return sorted_vals[min(int(q * len(sorted_vals)), len(sorted_vals) - 1)]

    return {
        "prob": prob,
        "odds": american,
        "n_bets": n_bets,
        "trials": trials,
        "expected_units": statistics.fmean(finals),
        "median_units": statistics.median(finals),
        "p05_units": pct(finals, 0.05),
        "p95_units": pct(finals, 0.95),
        "prob_losing_overall": sum(1 for f in finals if f < 0) / trials,
        "median_max_drawdown": statistics.median(max_dds),
        "p95_max_drawdown": pct(max_dds, 0.95),
        "median_worst_losing_streak": statistics.median(worst_streaks),
        "max_worst_losing_streak": max(worst_streaks),
    }


def losing_streak_probability(prob: float, streak: int, n_bets: int) -> float:
    """
    Probability of hitting a losing streak of at least `streak` in `n_bets`.

    Exact via a small dynamic program over "current run length", not a
    simulation. Useful for showing that a 7-game skid is *expected*, not a sign
    the model broke.
    """
    q = 1.0 - prob
    # state[i] = P(current consecutive-loss run == i), plus an absorbing "hit it" state.
    state = [0.0] * streak
    state[0] = 1.0
    absorbed = 0.0
    for _ in range(n_bets):
        nxt = [0.0] * streak
        for i, pi in enumerate(state):
            if pi == 0.0:
                continue
            nxt[0] += pi * prob                      # win resets the run
            if i + 1 >= streak:
                absorbed += pi * q                   # reached the streak
            else:
                nxt[i + 1] += pi * q
        state = nxt
    return absorbed


def hit_rate_ci(wins: int, n: int, *, confidence: float = 0.95) -> tuple[float, float]:
    """
    Wilson score interval on a hit rate. Correct for small samples where the
    naive normal interval is badly wrong — which is exactly the regime a bettor
    with 40 picks is in.
    """
    if n == 0:
        return (0.0, 1.0)
    z = _z(1 - (1 - confidence) / 2)
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def reality_check(wins: int, losses: int, american: float = -110) -> dict:
    """
    What a hot record actually proves. Usually: nothing.

    Takes a W-L and reports the confidence interval on the true hit rate, and
    whether the record is even distinguishable from a break-even bettor. A 12-3
    run looks spectacular and is entirely consistent with having no edge.
    """
    n = wins + losses
    if n == 0:
        return {"note": "no bets"}
    p_hat = wins / n
    lo, hi = hit_rate_ci(wins, n)
    be = breakeven_rate(american)
    # One-sided binomial: P(>= wins | true prob = breakeven)
    p_value = sum(
        math.comb(n, k) * be**k * (1 - be) ** (n - k) for k in range(wins, n + 1)
    )
    return {
        "record": f"{wins}-{losses}",
        "n": n,
        "hit_rate": p_hat,
        "ci95": (lo, hi),
        "breakeven_rate": be,
        "p_value_vs_breakeven": p_value,
        "proves_an_edge": p_value < 0.05,
        "ci_includes_breakeven": lo <= be <= hi,
    }


# ---------------------------------------------------------------------------
# Backtesting an actual bet log
# ---------------------------------------------------------------------------


@dataclass
class BacktestResult:
    n_bets: int
    settled: int
    units_staked: float
    units_won: float
    roi: float | None
    clv_sample: int
    avg_clv: float | None
    clv_beat_rate: float | None
    significance: dict
    bootstrap: dict
    verdict: str


def backtest_log(conn, *, sport: str | None = None, since: str | None = None) -> BacktestResult:
    """
    Backtest the actual bet history in `bets.db`.

    **CLV is weighted above results here on purpose.** Results over any
    realistic sample are dominated by variance; beating the closing line is
    detectable in a fraction of the sample size because the closing line is a
    far less noisy benchmark than the outcome.
    """
    where, params = ["result NOT IN ('pending','void')"], []
    if sport:
        where.append("sport = ?")
        params.append(sport.upper())
    if since:
        where.append("event_date >= ?")
        params.append(since)
    rows = conn.execute(f"SELECT * FROM bets WHERE {' AND '.join(where)}", params).fetchall()

    settled = len(rows)
    staked = sum(r["stake_units"] for r in rows)
    won = sum(r["profit_units"] or 0.0 for r in rows)
    per_bet = [
        (r["profit_units"] or 0.0) / r["stake_units"] for r in rows if r["stake_units"]
    ]

    with_clv = [r for r in rows if r["clv_pct"] is not None]
    avg_clv = statistics.fmean(r["clv_pct"] for r in with_clv) if with_clv else None
    beat = sum(1 for r in with_clv if r["clv_pct"] > 0) / len(with_clv) if with_clv else None

    sig = roi_significance(won, staked, settled) if settled >= 2 else {"conclusive": False}
    boot = bootstrap_roi_ci(per_bet) if len(per_bet) >= 2 else {"n": len(per_bet)}

    verdict = _verdict(settled, sig, boot, avg_clv, beat, len(with_clv))
    return BacktestResult(
        n_bets=settled,
        settled=settled,
        units_staked=round(staked, 2),
        units_won=round(won, 2),
        roi=(won / staked) if staked else None,
        clv_sample=len(with_clv),
        avg_clv=avg_clv,
        clv_beat_rate=beat,
        significance=sig,
        bootstrap=boot,
        verdict=verdict,
    )


def _verdict(settled, sig, boot, avg_clv, beat_rate, clv_n) -> str:
    """Say what the numbers support, and nothing more."""
    if settled < 30:
        base = (
            f"{settled} settled bets is far too small to conclude anything about "
            "results. Judge the process, not the record."
        )
    elif boot.get("spans_zero", True):
        base = (
            "The confidence interval on ROI spans zero — this record does not "
            "demonstrate an edge. That is the normal outcome at this sample size, "
            "not a verdict that the process is bad."
        )
    elif sig.get("significant_at_05"):
        base = (
            "ROI is statistically distinguishable from zero at this sample. "
            "Encouraging, but a single significant result is not proof — keep betting "
            "the process and watch whether it holds."
        )
    else:
        base = "Positive but not statistically significant. Insufficient evidence either way."

    if clv_n >= 20 and avg_clv is not None:
        if avg_clv > 0.01 and (beat_rate or 0) > 0.55:
            return base + (
                f" CLV is the stronger signal here: averaging {avg_clv:+.2%} and beating "
                f"the close {beat_rate:.0%} of the time over {clv_n} bets. That is the "
                "evidence worth trusting."
            )
        if avg_clv < 0:
            return base + (
                f" More importantly, CLV is negative ({avg_clv:+.2%} over {clv_n} bets). "
                "Whatever the record says, the market is beating these numbers."
            )
    elif clv_n < 20:
        return base + (
            f" Only {clv_n} bets have a recorded closing line. CLV is the honest "
            "scoreboard and it is mostly missing — record closing lines with "
            "`db close` and the picture gets clear much faster than results alone."
        )
    return base


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_breakeven(args) -> int:
    be = breakeven_rate(args.odds)
    mu, sd = profit_per_bet(be, args.odds)
    print(f"odds            : {args.odds:+.0f}")
    print(f"breakeven rate  : {be:.4f}  ({be:.2%})")
    print(f"sd per 1u bet   : {sd:.4f}u")
    print()
    for p in (be + 0.01, be + 0.02, be + 0.03, be + 0.05):
        m, _ = profit_per_bet(p, args.odds)
        print(f"  at {p:.1%} you win {m:+.2%} per bet ({(p - be) * 100:+.1f} pts of edge)")
    print("\nAn extra point of hit rate is worth ~2% ROI. That's the whole game.")
    return 0


def _cmd_sample_size(args) -> int:
    be = breakeven_rate(args.odds)
    # Convert a target ROI into the hit rate that produces it.
    b = american_to_decimal(args.odds) - 1.0
    prob = (args.roi + 1.0) / (b + 1.0)
    r = required_sample_size(prob, args.odds, alpha=args.alpha, power=args.power)
    if r["n_required"] is None:
        print(r["note"])
        return 0
    print(f"target ROI      : {args.roi:+.1%}")
    print(f"implies hit rate: {prob:.4f} vs. breakeven {be:.4f} ({r['edge_pct_points']:+.2f} pts)")
    print(f"sd per bet      : {r['sd_per_bet']:.4f}u")
    print(f"signal / noise  : {r['signal_to_noise']:.4f}")
    print()
    print(f"BETS REQUIRED   : {r['n_required']:,}")
    print(f"                  (to detect this at {args.alpha:.0%} significance, {args.power:.0%} power)")
    print()
    print("This is why nobody can show you a 'proven' system off a season of picks.")
    print("At 3 bets a day that is", f"{r['n_required'] / 3 / 365:.1f}", "years of betting.")
    return 0


def _cmd_drawdown(args) -> int:
    d = drawdown_simulation(args.prob, args.odds, n_bets=args.bets, trials=args.trials)
    print(f"A bettor who truly wins {args.prob:.1%} at {args.odds:+.0f}, over {args.bets} bets:")
    print(f"  expected profit      : {d['expected_units']:+.1f}u")
    print(f"  median profit        : {d['median_units']:+.1f}u")
    print(f"  5th-95th pct outcome : {d['p05_units']:+.1f}u to {d['p95_units']:+.1f}u")
    print()
    print(f"  chance of LOSING money anyway : {d['prob_losing_overall']:.1%}")
    print(f"  median worst drawdown         : {d['median_max_drawdown']:.1f}u")
    print(f"  95th pct worst drawdown       : {d['p95_max_drawdown']:.1f}u")
    print(f"  median longest losing streak  : {d['median_worst_losing_streak']:.0f} bets")
    print(f"  worst streak seen in {d['trials']} runs : {d['max_worst_losing_streak']:.0f} bets")
    print()
    print("That is what a REAL edge looks like from the inside. Anyone promising")
    print("you a smooth ride is describing something that does not exist.")
    return 0


def _cmd_streak(args) -> int:
    print(f"A {args.prob:.0%} bettor over {args.bets} bets will hit a losing streak of:")
    for s in (3, 4, 5, 6, 7, 8, 10, 12):
        p = losing_streak_probability(args.prob, s, args.bets)
        bar = "#" * int(p * 40)
        print(f"  {s:>2}+ in a row : {p:6.1%}  {bar}")
    print("\nA cold streak is not evidence the model broke. It is the cost of admission.")
    return 0


def _cmd_reality(args) -> int:
    try:
        w, l = (int(x) for x in args.record.split("-")[:2])
    except ValueError:
        print("give a record like 12-3")
        return 2
    r = reality_check(w, l, args.odds)
    print(f"record          : {r['record']}  ({r['hit_rate']:.1%})")
    print(f"95% CI on true  : {r['ci95'][0]:.1%} to {r['ci95'][1]:.1%}")
    print(f"breakeven       : {r['breakeven_rate']:.1%}")
    print(f"p-value         : {r['p_value_vs_breakeven']:.4f}")
    print()
    if r["proves_an_edge"]:
        print("This record IS statistically distinguishable from break-even.")
        print("It still isn't proof of a repeatable edge — one significant result")
        print("out of many looks is exactly what noise produces.")
    else:
        print("This record does NOT demonstrate an edge.")
        print(f"A break-even bettor produces a run this good {r['p_value_vs_breakeven']:.1%} of the time.")
    if r["ci_includes_breakeven"]:
        print("The confidence interval still includes break-even — consistent with no edge at all.")
    return 0


def _cmd_evaluate(args) -> int:
    from lib import db

    conn = db.connect(args.db)
    r = backtest_log(conn, sport=args.sport, since=args.since)
    conn.close()
    if not r.settled:
        print("No settled bets in the log yet. Nothing to backtest.")
        print("Log bets with `db log`, record closes with `db close`, grade with `db grade`.")
        return 0
    print(f"settled         : {r.settled}")
    print(f"staked          : {r.units_staked}u")
    print(f"won             : {r.units_won:+.2f}u")
    print(f"ROI             : {r.roi:+.2%}" if r.roi is not None else "ROI: —")
    if r.bootstrap.get("ci_low") is not None:
        print(f"95% CI on ROI   : {r.bootstrap['ci_low']:+.2%} to {r.bootstrap['ci_high']:+.2%}  (bootstrap)")
    if r.significance.get("p_value") is not None:
        print(f"p-value         : {r.significance['p_value']:.4f}")
    if r.clv_sample:
        print(f"CLV             : {r.avg_clv:+.2%} avg, beat close {r.clv_beat_rate:.0%} "
              f"({r.clv_sample} bets)")
    print()
    print(r.verdict)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lib.backtest",
        description="The Desk — historical validation and the statistics of edge detection.",
    )
    p.add_argument("--db", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("breakeven", help="hit rate needed to break even")
    b.add_argument("--odds", type=float, default=-110)
    b.set_defaults(func=_cmd_breakeven)

    s = sub.add_parser("sample-size", help="bets needed to prove an edge is real")
    s.add_argument("--roi", type=float, default=0.05)
    s.add_argument("--odds", type=float, default=-110)
    s.add_argument("--alpha", type=float, default=0.05)
    s.add_argument("--power", type=float, default=0.80)
    s.set_defaults(func=_cmd_sample_size)

    d = sub.add_parser("drawdown", help="what a real edge feels like from the inside")
    d.add_argument("--prob", type=float, default=0.55)
    d.add_argument("--odds", type=float, default=-110)
    d.add_argument("--bets", type=int, default=500)
    d.add_argument("--trials", type=int, default=5000)
    d.set_defaults(func=_cmd_drawdown)

    st = sub.add_parser("streak", help="probability of losing streaks")
    st.add_argument("--prob", type=float, default=0.55)
    st.add_argument("--bets", type=int, default=500)
    st.set_defaults(func=_cmd_streak)

    rc = sub.add_parser("reality-check", help="what a hot record actually proves")
    rc.add_argument("--record", required=True, help="e.g. 12-3")
    rc.add_argument("--odds", type=float, default=-110)
    rc.set_defaults(func=_cmd_reality)

    e = sub.add_parser("evaluate", help="backtest your own bets.db")
    e.add_argument("--sport", default=None)
    e.add_argument("--since", default=None)
    e.set_defaults(func=_cmd_evaluate)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
