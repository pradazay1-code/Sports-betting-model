"""
Bet log and CLV tracking.

An untracked bet is an unlearned lesson. Everything the desk recommends and the
user takes goes in here, and `/clv` and `/review` read straight out of it.

Storage is a single SQLite file (`bets.db`, gitignored). No ORM, no migrations
framework — the schema is small enough to keep in one place and `init_db()` is
idempotent, so it can be called on every entry point.

CLI:
    python3 -m lib.db init
    python3 -m lib.db log --sport NFL --event "KC @ BUF" --market spread \
        --side "BUF -2.5" --price -108 --book draftkings --stake 1.0 --fair-prob 0.545
    python3 -m lib.db close --id 3 --closing -115
    python3 -m lib.db grade --id 3 --result win
    python3 -m lib.db report
    python3 -m lib.db calibration
    python3 -m lib.db open
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from lib.odds import (
    american_to_decimal,
    clv as clv_calc,
    ev_from_american,
    implied_prob,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("DESK_DB_PATH", REPO_ROOT / "bets.db"))

VALID_RESULTS = ("pending", "win", "loss", "push", "void", "half-win", "half-loss")

SCHEMA = """
CREATE TABLE IF NOT EXISTS bets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    logged_at       TEXT    NOT NULL,          -- ISO8601 UTC, when we wrote the row
    event_date      TEXT    NOT NULL,          -- YYYY-MM-DD, the day the event runs
    sport           TEXT    NOT NULL,
    event           TEXT    NOT NULL,          -- "KC @ BUF", "Gaethje vs Oliveira"
    market          TEXT    NOT NULL,          -- spread / total / ml / prop / parlay
    side            TEXT    NOT NULL,          -- "BUF -2.5", "over 47.5", "Oliveira ML"
    line            REAL,                      -- numeric line where one exists
    price_taken     REAL    NOT NULL,          -- American
    decimal_taken   REAL    NOT NULL,
    book            TEXT    NOT NULL,
    stake_units     REAL    NOT NULL,

    fair_prob       REAL,                      -- our devigged number at bet time
    devig_method    TEXT,
    ev_at_bet       REAL,                      -- EV% we thought we had
    confidence      TEXT,                      -- low / medium / high

    closing_price   REAL,                      -- American at close
    closing_prob    REAL,                      -- raw implied at close
    clv_pct         REAL,                      -- signed, probability terms
    clv_cents       REAL,

    result          TEXT    NOT NULL DEFAULT 'pending',
    profit_units    REAL,
    graded_at       TEXT,

    notes           TEXT,
    tags            TEXT,                      -- comma separated, free-form

    CHECK (result IN ('pending','win','loss','push','void','half-win','half-loss'))
);

CREATE INDEX IF NOT EXISTS idx_bets_date   ON bets(event_date);
CREATE INDEX IF NOT EXISTS idx_bets_sport  ON bets(sport);
CREATE INDEX IF NOT EXISTS idx_bets_result ON bets(result);

-- Parlay legs live here so a parlay is one row in `bets` with N rows here.
CREATE TABLE IF NOT EXISTS parlay_legs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    bet_id      INTEGER NOT NULL REFERENCES bets(id) ON DELETE CASCADE,
    leg_index   INTEGER NOT NULL,
    event       TEXT    NOT NULL,
    market      TEXT    NOT NULL,
    side        TEXT    NOT NULL,
    price       REAL    NOT NULL,
    fair_prob   REAL,
    result      TEXT    NOT NULL DEFAULT 'pending'
);

CREATE INDEX IF NOT EXISTS idx_legs_bet ON parlay_legs(bet_id);

-- Line history, so we can reconstruct movement and confirm a close after the
-- fact rather than trusting memory.
CREATE TABLE IF NOT EXISTS line_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at TEXT NOT NULL,
    sport       TEXT NOT NULL,
    event       TEXT NOT NULL,
    market      TEXT NOT NULL,
    side        TEXT NOT NULL,
    book        TEXT NOT NULL,
    price       REAL NOT NULL,
    line        REAL
);

CREATE INDEX IF NOT EXISTS idx_snap_event ON line_snapshots(event, market);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open the log. Creates the schema if it isn't there yet."""
    p = Path(path) if path else DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def init_db(path: Path | str | None = None) -> Path:
    conn = connect(path)
    conn.close()
    return Path(path) if path else DB_PATH


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def log_bet(
    conn: sqlite3.Connection,
    *,
    sport: str,
    event: str,
    market: str,
    side: str,
    price_taken: float,
    book: str,
    stake_units: float,
    event_date: str | None = None,
    line: float | None = None,
    fair_prob: float | None = None,
    devig_method: str | None = None,
    confidence: str | None = None,
    notes: str | None = None,
    tags: str | None = None,
    legs: Iterable[dict[str, Any]] | None = None,
) -> int:
    """Insert a bet. Returns its id. EV at bet time is derived, not taken on faith."""
    ev_at_bet = ev_from_american(fair_prob, price_taken) if fair_prob is not None else None
    cur = conn.execute(
        """
        INSERT INTO bets (
            logged_at, event_date, sport, event, market, side, line,
            price_taken, decimal_taken, book, stake_units,
            fair_prob, devig_method, ev_at_bet, confidence, notes, tags
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            _now(),
            event_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            sport.upper(),
            event,
            market.lower(),
            side,
            line,
            float(price_taken),
            american_to_decimal(price_taken),
            book.lower(),
            float(stake_units),
            fair_prob,
            devig_method,
            ev_at_bet,
            confidence,
            notes,
            tags,
        ),
    )
    bet_id = int(cur.lastrowid)

    for i, leg in enumerate(legs or []):
        conn.execute(
            """
            INSERT INTO parlay_legs (bet_id, leg_index, event, market, side, price, fair_prob)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                bet_id,
                i,
                leg["event"],
                leg["market"],
                leg["side"],
                float(leg["price"]),
                leg.get("fair_prob"),
            ),
        )
    conn.commit()
    return bet_id


def set_closing_line(conn: sqlite3.Connection, bet_id: int, closing_american: float) -> dict:
    """Record where the market closed and compute CLV. This is the scoreboard."""
    row = conn.execute("SELECT price_taken FROM bets WHERE id = ?", (bet_id,)).fetchone()
    if row is None:
        raise KeyError(f"no bet with id {bet_id}")
    c = clv_calc(row["price_taken"], closing_american)
    conn.execute(
        """
        UPDATE bets SET closing_price = ?, closing_prob = ?, clv_pct = ?, clv_cents = ?
        WHERE id = ?
        """,
        (float(closing_american), c["closing_implied"], c["pct"], c["cents"], bet_id),
    )
    conn.commit()
    return c


def grade_bet(
    conn: sqlite3.Connection,
    bet_id: int,
    result: str,
    *,
    profit_units: float | None = None,
) -> float:
    """
    Settle a bet. Profit is derived from price and stake unless overridden
    (you'd override for a partially-cashed-out or bought-out position).
    """
    result = result.lower()
    if result not in VALID_RESULTS:
        raise ValueError(f"result must be one of {VALID_RESULTS}")
    row = conn.execute("SELECT decimal_taken, stake_units FROM bets WHERE id = ?", (bet_id,)).fetchone()
    if row is None:
        raise KeyError(f"no bet with id {bet_id}")

    if profit_units is None:
        stake = row["stake_units"]
        b = row["decimal_taken"] - 1.0
        profit_units = {
            "win": stake * b,
            "loss": -stake,
            "push": 0.0,
            "void": 0.0,
            "half-win": stake * b / 2.0,
            "half-loss": -stake / 2.0,
            "pending": 0.0,
        }[result]

    conn.execute(
        "UPDATE bets SET result = ?, profit_units = ?, graded_at = ? WHERE id = ?",
        (result, float(profit_units), _now(), bet_id),
    )
    conn.commit()
    return float(profit_units)


def snapshot_line(
    conn: sqlite3.Connection,
    *,
    sport: str,
    event: str,
    market: str,
    side: str,
    book: str,
    price: float,
    line: float | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO line_snapshots (captured_at, sport, event, market, side, book, price, line)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (_now(), sport.upper(), event, market.lower(), side, book.lower(), float(price), line),
    )
    conn.commit()
    return int(cur.lastrowid)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def open_bets(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM bets WHERE result = 'pending' ORDER BY event_date, id"
    ).fetchall()


def performance(
    conn: sqlite3.Connection,
    *,
    sport: str | None = None,
    since: str | None = None,
) -> dict:
    """
    ROI, record, and — the part that actually matters — CLV.

    Results are reported because people want to see them, but the CLV block is
    the honest scoreboard and the summary says so.
    """
    where, params = ["result != 'pending'"], []
    if sport:
        where.append("sport = ?")
        params.append(sport.upper())
    if since:
        where.append("event_date >= ?")
        params.append(since)
    clause = " WHERE " + " AND ".join(where)

    rows = conn.execute(f"SELECT * FROM bets{clause}", params).fetchall()
    settled = len(rows)
    staked = sum(r["stake_units"] for r in rows)
    profit = sum(r["profit_units"] or 0.0 for r in rows)

    wins = sum(1 for r in rows if r["result"] in ("win", "half-win"))
    losses = sum(1 for r in rows if r["result"] in ("loss", "half-loss"))
    pushes = sum(1 for r in rows if r["result"] in ("push", "void"))

    with_clv = [r for r in rows if r["clv_pct"] is not None]
    beat = sum(1 for r in with_clv if r["clv_pct"] > 0)
    avg_clv = sum(r["clv_pct"] for r in with_clv) / len(with_clv) if with_clv else None

    expected = [r for r in rows if r["ev_at_bet"] is not None]
    exp_units = sum(r["ev_at_bet"] * r["stake_units"] for r in expected)

    return {
        "settled_bets": settled,
        "record": f"{wins}-{losses}-{pushes}",
        "units_staked": round(staked, 2),
        "units_won": round(profit, 2),
        "roi": (profit / staked) if staked else None,
        "clv_sample": len(with_clv),
        "clv_beat_rate": (beat / len(with_clv)) if with_clv else None,
        "avg_clv_pct": avg_clv,
        "expected_units": round(exp_units, 2) if expected else None,
        "expected_sample": len(expected),
        "realized_vs_expected": (round(profit - exp_units, 2) if expected else None),
        "missing_closing_lines": settled - len(with_clv),
    }


def calibration(conn: sqlite3.Connection, *, bins: int = 5) -> list[dict]:
    """
    When we said 60%, did it hit ~60%?

    Buckets settled bets by the fair probability we assigned at bet time and
    compares it to the realized hit rate. Pushes and voids are dropped — they
    didn't resolve, so they can't test a probability. Small samples are the norm
    here; the `n` column is there so nobody over-reads a 3-bet bucket.
    """
    rows = conn.execute(
        """
        SELECT fair_prob, result FROM bets
        WHERE result IN ('win','loss','half-win','half-loss') AND fair_prob IS NOT NULL
        """
    ).fetchall()

    out = []
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        in_bin = [r for r in rows if lo <= r["fair_prob"] < hi or (i == bins - 1 and r["fair_prob"] == 1.0)]
        if not in_bin:
            out.append({"bucket": f"{lo:.0%}-{hi:.0%}", "n": 0, "predicted": None, "actual": None, "gap": None})
            continue
        pred = sum(r["fair_prob"] for r in in_bin) / len(in_bin)
        hit = sum(1 for r in in_bin if r["result"] in ("win", "half-win")) / len(in_bin)
        out.append(
            {
                "bucket": f"{lo:.0%}-{hi:.0%}",
                "n": len(in_bin),
                "predicted": pred,
                "actual": hit,
                "gap": hit - pred,
            }
        )
    return out


def tilt_signals(conn: sqlite3.Connection, *, lookback_days: int = 7) -> dict:
    """
    Mechanical tilt check, so the read isn't purely vibes.

    Flags: bet frequency and average stake in the recent window vs. the prior
    baseline, and whether stake went up right after a losing day. None of these
    prove tilt on their own — they're prompts to look, and the agent should say
    so rather than accusing.
    """
    rows = conn.execute(
        "SELECT event_date, stake_units, profit_units, result FROM bets ORDER BY event_date"
    ).fetchall()
    if len(rows) < 5:
        return {"enough_data": False, "note": "fewer than 5 logged bets — no baseline yet"}

    dates = sorted({r["event_date"] for r in rows})
    recent_dates = set(dates[-lookback_days:])
    recent = [r for r in rows if r["event_date"] in recent_dates]
    baseline = [r for r in rows if r["event_date"] not in recent_dates]
    if not baseline:
        return {"enough_data": False, "note": "no baseline period outside the lookback window"}

    r_stake = sum(x["stake_units"] for x in recent) / len(recent)
    b_stake = sum(x["stake_units"] for x in baseline) / len(baseline)
    r_freq = len(recent) / max(len(recent_dates), 1)
    b_freq = len(baseline) / max(len(set(r["event_date"] for r in baseline)), 1)

    flags = []
    if r_stake > b_stake * 1.5:
        flags.append(f"average stake up {r_stake / b_stake:.1f}x vs. baseline ({b_stake:.2f}u -> {r_stake:.2f}u)")
    if r_freq > b_freq * 1.5:
        flags.append(f"bets per day up {r_freq / b_freq:.1f}x vs. baseline ({b_freq:.1f} -> {r_freq:.1f})")

    # Sizing up the day after a loss is the classic tell.
    by_day: dict[str, float] = {}
    for r in rows:
        by_day[r["event_date"]] = by_day.get(r["event_date"], 0.0) + (r["profit_units"] or 0.0)
    escalations = 0
    for prev, cur in zip(dates, dates[1:]):
        if by_day.get(prev, 0.0) < 0:
            prev_avg = sum(r["stake_units"] for r in rows if r["event_date"] == prev) / max(
                sum(1 for r in rows if r["event_date"] == prev), 1
            )
            cur_avg = sum(r["stake_units"] for r in rows if r["event_date"] == cur) / max(
                sum(1 for r in rows if r["event_date"] == cur), 1
            )
            if cur_avg > prev_avg * 1.25:
                escalations += 1
    if escalations >= 2:
        flags.append(f"sized up the day after a losing day {escalations} times")

    return {
        "enough_data": True,
        "recent_avg_stake": round(r_stake, 2),
        "baseline_avg_stake": round(b_stake, 2),
        "recent_bets_per_day": round(r_freq, 2),
        "baseline_bets_per_day": round(b_freq, 2),
        "post_loss_escalations": escalations,
        "flags": flags,
        "tilting": bool(flags),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _pct(x, digits=2):
    return "—" if x is None else f"{x:+.{digits}%}"


def _cmd_init(args) -> int:
    path = init_db(args.db)
    conn = connect(args.db)
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    conn.close()
    print(f"schema ok: {path}")
    print(f"tables   : {', '.join(sorted(t for t in tables if not t.startswith('sqlite_')))}")
    return 0


def _cmd_log(args) -> int:
    conn = connect(args.db)
    bet_id = log_bet(
        conn,
        sport=args.sport,
        event=args.event,
        market=args.market,
        side=args.side,
        price_taken=args.price,
        book=args.book,
        stake_units=args.stake,
        event_date=args.date,
        line=args.line,
        fair_prob=args.fair_prob,
        devig_method=args.devig_method,
        confidence=args.confidence,
        notes=args.notes,
        tags=args.tags,
    )
    row = conn.execute("SELECT * FROM bets WHERE id = ?", (bet_id,)).fetchone()
    conn.close()
    print(f"logged #{bet_id}: {row['sport']} {row['event']} — {row['side']} "
          f"{row['price_taken']:+.0f} @ {row['book']} for {row['stake_units']}u")
    if row["ev_at_bet"] is not None:
        print(f"  EV at bet: {row['ev_at_bet']:+.2%}  (fair p={row['fair_prob']:.4f})")
    else:
        print("  no fair probability supplied — this bet can't feed the calibration check")
    return 0


def _cmd_close(args) -> int:
    conn = connect(args.db)
    c = set_closing_line(conn, args.id, args.closing)
    conn.close()
    print(f"#{args.id}: took {c['taken_american']:+.0f}, closed {c['closing_american']:+.0f}")
    print(f"  CLV {c['pct']:+.2%} ({c['cents']:+.0f} cents) — "
          f"{'beat the close' if c['beat_close'] else 'lost to the close'}")
    return 0


def _cmd_grade(args) -> int:
    conn = connect(args.db)
    profit = grade_bet(conn, args.id, args.result, profit_units=args.profit)
    conn.close()
    print(f"#{args.id}: {args.result} — {profit:+.2f}u")
    return 0


def _cmd_report(args) -> int:
    conn = connect(args.db)
    perf = performance(conn, sport=args.sport, since=args.since)
    conn.close()
    if not perf["settled_bets"]:
        print("nothing settled yet. Log some bets and grade them.")
        return 0
    print(f"settled     : {perf['settled_bets']}   record {perf['record']}")
    print(f"staked      : {perf['units_staked']}u")
    print(f"won         : {perf['units_won']:+.2f}u")
    print(f"ROI         : {_pct(perf['roi'])}")
    print()
    print("--- the honest scoreboard ---")
    if perf["clv_sample"]:
        print(f"CLV sample  : {perf['clv_sample']} bets ({perf['missing_closing_lines']} missing a close)")
        print(f"beat close  : {perf['clv_beat_rate']:.1%} of the time")
        print(f"avg CLV     : {_pct(perf['avg_clv_pct'])}")
    else:
        print("no closing lines recorded. Without them there is no scoreboard — use `close`.")
    if perf["expected_units"] is not None:
        print(f"expected    : {perf['expected_units']:+.2f}u over {perf['expected_sample']} bets")
        print(f"variance    : {perf['realized_vs_expected']:+.2f}u realized vs. expected")
    return 0


def _cmd_calibration(args) -> int:
    conn = connect(args.db)
    rows = calibration(conn, bins=args.bins)
    conn.close()
    print(f"{'bucket':<12}{'n':>5}{'predicted':>12}{'actual':>10}{'gap':>10}")
    for r in rows:
        if not r["n"]:
            print(f"{r['bucket']:<12}{0:>5}{'—':>12}{'—':>10}{'—':>10}")
            continue
        print(f"{r['bucket']:<12}{r['n']:>5}{r['predicted']:>12.1%}{r['actual']:>10.1%}{r['gap']:>+10.1%}")
    print("\nBuckets under ~20 bets tell you nothing. Don't adjust the model off noise.")
    return 0


def _cmd_open(args) -> int:
    conn = connect(args.db)
    rows = open_bets(conn)
    conn.close()
    if not rows:
        print("no open bets.")
        return 0
    for r in rows:
        print(f"#{r['id']:<4} {r['event_date']}  {r['sport']:<5} {r['event']:<28} "
              f"{r['side']:<22} {r['price_taken']:+.0f} @ {r['book']:<12} {r['stake_units']}u")
    return 0


def _cmd_tilt(args) -> int:
    conn = connect(args.db)
    t = tilt_signals(conn, lookback_days=args.days)
    conn.close()
    if not t["enough_data"]:
        print(t["note"])
        return 0
    print(f"avg stake   : {t['baseline_avg_stake']}u baseline -> {t['recent_avg_stake']}u recent")
    print(f"bets/day    : {t['baseline_bets_per_day']} baseline -> {t['recent_bets_per_day']} recent")
    print(f"post-loss   : sized up after a losing day {t['post_loss_escalations']}x")
    if t["flags"]:
        print("\nflags:")
        for f in t["flags"]:
            print(f"  - {f}")
        print("\nThese are prompts to look, not a verdict. Ask before you accuse.")
    else:
        print("\nno tilt signals in the log.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lib.db", description="The Desk — bet log and CLV.")
    p.add_argument("--db", default=None, help=f"path to the SQLite file (default {DB_PATH})")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create the schema").set_defaults(func=_cmd_init)

    lg = sub.add_parser("log", help="log a bet")
    lg.add_argument("--sport", required=True)
    lg.add_argument("--event", required=True)
    lg.add_argument("--market", required=True)
    lg.add_argument("--side", required=True)
    lg.add_argument("--price", type=float, required=True)
    lg.add_argument("--book", required=True)
    lg.add_argument("--stake", type=float, required=True)
    lg.add_argument("--date", default=None)
    lg.add_argument("--line", type=float, default=None)
    lg.add_argument("--fair-prob", dest="fair_prob", type=float, default=None)
    lg.add_argument("--devig-method", dest="devig_method", default=None)
    lg.add_argument("--confidence", default=None, choices=["low", "medium", "high"])
    lg.add_argument("--notes", default=None)
    lg.add_argument("--tags", default=None)
    lg.set_defaults(func=_cmd_log)

    cl = sub.add_parser("close", help="record the closing line")
    cl.add_argument("--id", type=int, required=True)
    cl.add_argument("--closing", type=float, required=True)
    cl.set_defaults(func=_cmd_close)

    gr = sub.add_parser("grade", help="settle a bet")
    gr.add_argument("--id", type=int, required=True)
    gr.add_argument("--result", required=True, choices=list(VALID_RESULTS))
    gr.add_argument("--profit", type=float, default=None)
    gr.set_defaults(func=_cmd_grade)

    rp = sub.add_parser("report", help="ROI + CLV")
    rp.add_argument("--sport", default=None)
    rp.add_argument("--since", default=None, help="YYYY-MM-DD")
    rp.set_defaults(func=_cmd_report)

    ca = sub.add_parser("calibration", help="predicted vs. actual hit rate")
    ca.add_argument("--bins", type=int, default=5)
    ca.set_defaults(func=_cmd_calibration)

    sub.add_parser("open", help="list ungraded bets").set_defaults(func=_cmd_open)

    tl = sub.add_parser("tilt", help="mechanical tilt check")
    tl.add_argument("--days", type=int, default=7)
    tl.set_defaults(func=_cmd_tilt)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
