"""Weekly review: CLV audit, calibration curves, ROI by segment (spec §8).

Every Monday: suspend any category with negative CLV over 50+ picks,
derive calibration shrinkage per (sport, market) from realized hit rates,
show where the actual edge lives, and print the variance context so a
normal losing week doesn't cause config tilt.

    python -m src.report.weekly_review --run
"""

from __future__ import annotations

import argparse
import math
from statistics import NormalDist

from src import config, db
from src.engine import clv_tracker

SUSPEND_MIN_PICKS = 50
CALIBRATION_MIN_PICKS = 30


# ------------------------------------------------------------------ CLV audit

def clv_audit(conn) -> list[dict]:
    """Suspend negative-CLV categories with sample; promote recovered ones."""
    now = db.utcnow()
    actions = []
    rows = conn.execute(
        """SELECT p.sport, p.market, COUNT(*) AS n, AVG(c.clv_pct) AS avg_clv
           FROM clv_log c JOIN picks p ON p.pick_id = c.pick_id
           WHERE c.clv_pct IS NOT NULL GROUP BY p.sport, p.market""").fetchall()
    for r in rows:
        if r["n"] >= SUSPEND_MIN_PICKS and r["avg_clv"] < 0:
            conn.execute(
                """INSERT OR REPLACE INTO category_status VALUES (?,?,?,?,?)""",
                (r["sport"], r["market"], "suspended",
                 f"CLV {r['avg_clv']:+.2%} over {r['n']} picks", now))
            actions.append({"sport": r["sport"], "market": r["market"],
                            "action": "suspended", "avg_clv": r["avg_clv"], "n": r["n"]})
        else:
            prev = conn.execute(
                "SELECT status FROM category_status WHERE sport=? AND market=?",
                (r["sport"], r["market"])).fetchone()
            if prev and prev["status"] == "suspended" and r["avg_clv"] and r["avg_clv"] > 0:
                conn.execute(
                    "INSERT OR REPLACE INTO category_status VALUES (?,?,?,?,?)",
                    (r["sport"], r["market"], "live",
                     f"recovered: CLV {r['avg_clv']:+.2%}", now))
                actions.append({"sport": r["sport"], "market": r["market"],
                                "action": "reinstated", "avg_clv": r["avg_clv"], "n": r["n"]})
    conn.commit()
    return actions


# -------------------------------------------------------------- calibration

def calibration_buckets(conn, sport: str | None = None) -> list[dict]:
    """Predicted-prob buckets vs actual hit rate over settled picks."""
    where, params = "", []
    if sport:
        where = "AND sport = ?"
        params.append(sport)
    rows = conn.execute(
        f"""SELECT model_prob, status FROM picks
            WHERE status IN ('won', 'lost') {where}""", params).fetchall()
    buckets: dict[int, list[int]] = {}
    for r in rows:
        b = min(int(r["model_prob"] * 10), 9)
        buckets.setdefault(b, []).append(1 if r["status"] == "won" else 0)
    return [{"bucket": f"{b*10}-{b*10+10}%", "predicted_mid": b / 10 + 0.05,
             "actual": sum(v) / len(v), "n": len(v)}
            for b, v in sorted(buckets.items())]


def update_calibration(conn) -> list[dict]:
    """Shrinkage per (sport, market): actual edge over 0.5 vs predicted edge.

    Model says 60% but reality is 52% -> factor ~0.2 pulls future probs in
    (spec §3: an uncalibrated model is a losing model).
    """
    now = db.utcnow()
    updated = []
    rows = conn.execute(
        """SELECT sport, market,
                  AVG(model_prob) AS avg_pred,
                  AVG(CASE WHEN status='won' THEN 1.0 ELSE 0.0 END) AS avg_actual,
                  COUNT(*) AS n
           FROM picks WHERE status IN ('won','lost')
           GROUP BY sport, market HAVING n >= ?""", (CALIBRATION_MIN_PICKS,)).fetchall()
    for r in rows:
        pred_edge = r["avg_pred"] - 0.5
        actual_edge = r["avg_actual"] - 0.5
        factor = 1.0 if abs(pred_edge) < 1e-6 else max(0.0, min(1.0, actual_edge / pred_edge))
        conn.execute("INSERT OR REPLACE INTO calibration VALUES (?,?,?,?,?)",
                     (r["sport"], r["market"], round(factor, 3), r["n"], now))
        updated.append({"sport": r["sport"], "market": r["market"],
                        "factor": round(factor, 3), "n": r["n"]})
    conn.commit()
    return updated


# ------------------------------------------------------------ ROI + variance

def roi_by_segment(conn) -> list[dict]:
    rows = conn.execute(
        """SELECT sport, market, tier, COUNT(*) AS n,
                  SUM(CASE WHEN status='won' THEN stake_units*(odds_decimal-1)
                           WHEN status='lost' THEN -stake_units ELSE 0 END) AS profit_units,
                  SUM(stake_units) AS risked_units
           FROM picks WHERE status IN ('won','lost','push') AND tier IS NOT NULL
           GROUP BY sport, market, tier ORDER BY profit_units DESC""").fetchall()
    return [{**dict(r), "roi": (r["profit_units"] / r["risked_units"])
             if r["risked_units"] else 0.0} for r in rows]


def losing_week_probability(true_win_prob: float = 0.55, picks_per_week: int = 20,
                            avg_decimal: float = 1.91) -> float:
    """P(a genuinely winning bettor has a losing week) — normal approx.

    Shown every week so nobody tilts the config after normal variance
    (spec §8.4): a true 55% bettor at -110 loses ~40% of 20-pick weeks.
    """
    p, b = true_win_prob, avg_decimal - 1.0
    mu = picks_per_week * (p * b - (1 - p))
    var = picks_per_week * (p * (b + 1) ** 2 - (p * b - (1 - p)) ** 2 - 2 * p * (b + 1) + 1)
    sigma = math.sqrt(max(var, 1e-9))
    return NormalDist(mu, sigma).cdf(0.0)


# ------------------------------------------------------------------- report

def run_review(conn) -> str:
    from datetime import date
    day = date.today()
    actions = clv_audit(conn)
    cal = update_calibration(conn)
    md = [f"# EDGE ENGINE WEEKLY REVIEW — {day.isoformat()} (week {day.isocalendar()[1]})", ""]

    md.append("## CLV by segment (the true scoreboard)")
    seg = clv_tracker.summary(conn)
    md += [f"- {s['sport']} / {s['market']} / tier {s['tier']}: "
           f"{s['avg_clv']:+.2%} over {s['n']}" for s in seg] or ["(no CLV data yet)"]
    if actions:
        md.append("")
        md += [f"- **{a['action'].upper()}**: {a['sport']}/{a['market']} "
               f"(CLV {a['avg_clv']:+.2%}, n={a['n']})" for a in actions]

    md += ["", "## Calibration"]
    buckets = calibration_buckets(conn)
    md += [f"- {b['bucket']}: predicted ~{b['predicted_mid']:.0%}, "
           f"actual {b['actual']:.1%} (n={b['n']})" for b in buckets] or ["(no settled picks yet)"]
    if cal:
        md += [f"- shrinkage {c['sport']}/{c['market']}: factor {c['factor']} "
               f"(n={c['n']})" for c in cal]

    md += ["", "## ROI by segment"]
    md += [f"- {r['sport']} / {r['market']} / {r['tier']}: {r['profit_units']:+.2f}u "
           f"on {r['risked_units']:.2f}u risked ({r['roi']:+.1%}) over {r['n']}"
           for r in roi_by_segment(conn)] or ["(nothing settled yet)"]

    plw = losing_week_probability()
    md += ["", "## Variance context",
           f"A TRUE 55% bettor at -110 still has a losing week "
           f"{plw:.0%} of the time (20 picks/week). Judge the process by CLV, "
           "not the weekly P&L.", ""]

    out_dir = config.REPO_ROOT / config.settings()["paths"]["reports"] / "weekly"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{day.isoformat()}.md"
    path.write_text("\n".join(md))
    return str(path)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args(argv)
    if args.run:
        conn = db.connect()
        print(run_review(conn))
        conn.close()


if __name__ == "__main__":
    main()
