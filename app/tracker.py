"""Grade yesterday's picks, compute ROI and Brier, and write metrics."""

from __future__ import annotations

import json
import math
from datetime import date, timedelta

from app.store import connection
from app.utils import american_to_decimal, get_logger, today_local

LOG = get_logger("tracker")


def _stat_for(sport: str, market: str, stats: dict) -> float | None:
    # Composite NBA markets:
    if market == "player_pra":
        vals = [stats.get(k) for k in ("player_points", "player_rebounds", "player_assists")]
        if any(v is None for v in vals):
            return None
        return float(sum(vals))
    v = stats.get(market)
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def grade(on_date: str | None = None) -> dict:
    if on_date is None:
        on_date = (today_local() - timedelta(days=1)).isoformat()

    summary = {"on_date": on_date, "graded": 0, "wins": 0, "losses": 0, "push": 0, "roi_units": 0.0}
    with connection() as conn:
        picks = [dict(r) for r in conn.execute(
            "SELECT * FROM picks WHERE on_date=? AND graded=0", (on_date,)
        ).fetchall()]

        for p in picks:
            # Find player's stat by name on this date.
            row = conn.execute(
                """SELECT pgs.stats_json
                   FROM player_game_stats pgs
                   LEFT JOIN players pl ON pl.player_id = pgs.player_id
                   WHERE pgs.sport=? AND pgs.game_date=? AND lower(pl.full_name)=lower(?)
                   ORDER BY pgs.game_id DESC LIMIT 1""",
                (p["sport"], on_date, p["player_name"]),
            ).fetchone()
            if not row:
                continue
            try:
                stats = json.loads(row["stats_json"])
            except Exception:
                continue
            actual = _stat_for(p["sport"], p["market"], stats)
            if actual is None:
                continue
            line = float(p["line"])
            side = p["side"]
            won = None
            if math.isclose(actual, line, abs_tol=1e-9):
                won = None  # push
            elif side == "over":
                won = actual > line
            else:
                won = actual < line

            decimal_odds = american_to_decimal(int(p["price_american"]))
            stake = 1.0  # report in units of 1 risked
            if won is None:
                payout = 0.0
                summary["push"] += 1
            elif won:
                payout = stake * (decimal_odds - 1.0)
                summary["wins"] += 1
            else:
                payout = -stake
                summary["losses"] += 1

            conn.execute(
                """UPDATE picks SET graded=1, actual_value=?, won=?, payout_units=?
                   WHERE id=?""",
                (actual, 1 if won else (0 if won is False else None), payout, p["id"]),
            )
            summary["graded"] += 1
            summary["roi_units"] += payout

        # Per-sport daily metrics.
        for sport in ("NBA", "MLB", "NHL"):
            cur = conn.execute(
                """SELECT
                     COUNT(*)               n_picks,
                     SUM(CASE WHEN won=1 THEN 1 ELSE 0 END) n_wins,
                     SUM(CASE WHEN won=0 THEN 1 ELSE 0 END) n_losses,
                     SUM(CASE WHEN won IS NULL AND graded=1 THEN 1 ELSE 0 END) n_push,
                     COALESCE(SUM(payout_units), 0.0) roi
                   FROM picks
                   WHERE on_date=? AND sport=? AND graded=1""",
                (on_date, sport),
            ).fetchone()
            n_picks = cur["n_picks"] or 0
            if not n_picks:
                continue
            conn.execute(
                """INSERT OR REPLACE INTO metrics_daily
                   (on_date, sport, n_picks, n_wins, n_losses, n_push, roi_units, brier)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (on_date, sport, n_picks, cur["n_wins"] or 0, cur["n_losses"] or 0,
                 cur["n_push"] or 0, float(cur["roi"] or 0.0), None),
            )

    LOG.info("graded %s: %s", on_date, summary)
    return summary


def history(days: int = 30) -> list[dict]:
    end = today_local()
    start = end - timedelta(days=days)
    with connection() as conn:
        rows = [dict(r) for r in conn.execute(
            """SELECT on_date, sport, n_picks, n_wins, n_losses, n_push, roi_units
               FROM metrics_daily
               WHERE on_date BETWEEN ? AND ?
               ORDER BY on_date DESC, sport""",
            (start.isoformat(), end.isoformat()),
        ).fetchall()]
    return rows
