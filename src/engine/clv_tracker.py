"""Closing Line Value tracker — the true scoreboard (spec §0.2, §5).

Captures the closing line for every pick (sharp book first, else the book
the pick was made at), computes CLV, grades finished picks against actual
results, and settles the (paper) bankroll.

    python -m src.engine.clv_tracker --nightly    # close capture + grading
"""

from __future__ import annotations

import argparse

import requests

from src import config, db
from src.ingest import mlb


def clv_pct(open_decimal: float, close_decimal: float) -> float:
    """Positive = you beat the close (your payout is better than closing)."""
    return open_decimal / close_decimal - 1.0


def _closing_snapshot(conn, pick, commence: str):
    """Last pre-commence snapshot at the pick's line: sharp book preferred."""
    close_book = config.books()["closing_line_book"]
    for book_clause, params in (
        ("AND book = ?", [close_book]),
        ("AND book = ?", [pick["book"]]),
        ("", []),
    ):
        row = conn.execute(
            f"""SELECT * FROM line_snapshots
                WHERE event_id = ? AND market = ? AND side = ?
                  AND (player IS ? OR player = ?) AND line IS ? AND pulled_at <= ?
                  {book_clause}
                ORDER BY pulled_at DESC LIMIT 1""",
            [pick["event_id"], pick["market"], pick["side"], pick["player"],
             pick["player"], pick["line"], commence, *params]).fetchone()
        if row:
            return row
    return None


def capture_closes(conn) -> int:
    """Log closing lines for pending picks whose event has started."""
    picks = conn.execute(
        """SELECT p.* FROM picks p JOIN events e ON e.event_id = p.event_id
           WHERE p.status = 'pending' AND e.commence_time <= ?
             AND p.pick_id NOT IN (SELECT pick_id FROM clv_log)""",
        (db.utcnow(),)).fetchall()
    n = 0
    for p in picks:
        commence = conn.execute("SELECT commence_time FROM events WHERE event_id = ?",
                                (p["event_id"],)).fetchone()[0]
        snap = _closing_snapshot(conn, p, commence)
        conn.execute(
            """INSERT INTO clv_log (pick_id, open_odds_american, open_line,
                 close_odds_american, close_line, close_book, clv_pct, captured_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (p["pick_id"], p["odds_american"], p["line"],
             snap["odds_american"] if snap else None,
             snap["line"] if snap else None,
             snap["book"] if snap else None,
             round(clv_pct(p["odds_decimal"], snap["odds_decimal"]), 5) if snap else None,
             db.utcnow()))
        n += 1
    conn.commit()
    return n


# ------------------------------------------------------------------ grading

def settle_pick(conn, pick_id: int, result_value: float) -> str:
    """Grade a pick against the actual stat and settle the bankroll."""
    p = conn.execute("SELECT * FROM picks WHERE pick_id = ?", (pick_id,)).fetchone()
    if p is None or p["status"] not in ("pending", "hold_lineup"):
        return "skipped"
    line = p["line"]
    if line is None or result_value == line:
        status = "push" if result_value == line else "void"
        profit_units = 0.0
    else:
        hit = result_value > line if p["side"] == "over" else result_value < line
        status = "won" if hit else "lost"
        profit_units = p["stake_units"] * (p["odds_decimal"] - 1.0) if hit else -p["stake_units"]

    conn.execute(
        "UPDATE picks SET status = ?, result_value = ?, settled_at = ? WHERE pick_id = ?",
        (status, result_value, db.utcnow(), pick_id))
    if profit_units:
        bankroll = conn.execute(
            "SELECT bankroll FROM bankroll_history ORDER BY id DESC LIMIT 1").fetchone()[0]
        change = profit_units / 100.0 * bankroll   # 1 unit = 1% of bankroll
        conn.execute(
            "INSERT INTO bankroll_history (recorded_at, bankroll, change, reason) VALUES (?,?,?,?)",
            (db.utcnow(), round(bankroll + change, 2), round(change, 2),
             f"settle pick {pick_id} {status}"))
    conn.commit()
    return status


def parse_boxscore_pitching(payload: dict) -> dict[str, dict]:
    """MLB boxscore -> {pitcher full name: {'strikeouts': int, 'outs': int}}."""
    out = {}
    for team in payload.get("teams", {}).values():
        for player in (team.get("players") or {}).values():
            pitching = (player.get("stats") or {}).get("pitching") or {}
            if pitching.get("battersFaced"):
                name = (player.get("person") or {}).get("fullName")
                out[name] = {"strikeouts": pitching.get("strikeOuts"),
                             "outs": pitching.get("outs")}
    return out


def grade_mlb_strikeouts(conn, results_by_player: dict[str, dict]) -> int:
    """Settle pending K-prop picks given {player: {'strikeouts': n}}."""
    picks = conn.execute(
        "SELECT pick_id, player FROM picks "
        "WHERE market = 'pitcher_strikeouts' AND status = 'pending'").fetchall()
    n = 0
    for p in picks:
        res = results_by_player.get(p["player"])
        if res and res.get("strikeouts") is not None:
            settle_pick(conn, p["pick_id"], float(res["strikeouts"]))
            n += 1
    return n


def fetch_and_grade_mlb(conn, day: str) -> int:
    """Live path: pull boxscores for yesterday's final games and grade."""
    graded = 0
    for g in mlb.todays_games(conn, day):
        try:
            resp = requests.get(
                f"https://statsapi.mlb.com/api/v1/game/{g['game_pk']}/boxscore",
                timeout=config.sources()["http"]["timeout_seconds"])
            if resp.status_code != 200:
                continue
        except requests.RequestException:
            continue
        graded += grade_mlb_strikeouts(conn, parse_boxscore_pitching(resp.json()))
    return graded


def summary(conn) -> list[dict]:
    """Average CLV by sport / market / tier — feeds weekly review (spec §8)."""
    rows = conn.execute(
        """SELECT p.sport, p.market, p.tier, COUNT(*) AS n, AVG(c.clv_pct) AS avg_clv
           FROM clv_log c JOIN picks p ON p.pick_id = c.pick_id
           WHERE c.clv_pct IS NOT NULL
           GROUP BY p.sport, p.market, p.tier ORDER BY avg_clv DESC""").fetchall()
    return [dict(r) for r in rows]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nightly", action="store_true",
                    help="capture closing lines and grade yesterday's picks")
    ap.add_argument("--date", help="grade a specific date (YYYY-MM-DD)")
    args = ap.parse_args(argv)
    conn = db.connect()
    if args.nightly or args.date:
        from datetime import date, timedelta
        day = args.date or (date.today() - timedelta(days=1)).isoformat()
        print(f"closing lines captured: {capture_closes(conn)}")
        print(f"picks graded: {fetch_and_grade_mlb(conn, day)}")
        for row in summary(conn):
            print(f"  {row['sport']} {row['market']} tier {row['tier']}: "
                  f"CLV {row['avg_clv']:+.2%} over {row['n']}")
    conn.close()


if __name__ == "__main__":
    main()
