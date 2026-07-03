"""Daily orchestrator (spec §1, §7).

Phase 1: odds ingestion + line-movement logging.
Later phases plug into RUN_STEPS as they are built.

    python -m src.run_daily              # live pull (needs ODDS_API_KEY)
    python -m src.run_daily --props      # include player props
    python -m src.run_daily --sample F   # run pipeline on a cached payload
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src import config, db
from src.ingest import odds


def summarize(conn) -> None:
    total = conn.execute("SELECT COUNT(*) FROM line_snapshots").fetchone()[0]
    today = conn.execute(
        "SELECT COUNT(*) FROM line_snapshots WHERE pulled_at >= strftime('%Y-%m-%dT00:00:00Z','now')"
    ).fetchone()[0]
    events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    books = conn.execute("SELECT COUNT(DISTINCT book) FROM line_snapshots").fetchone()[0]
    bankroll = conn.execute(
        "SELECT bankroll FROM bankroll_history ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    quota = conn.execute(
        "SELECT requests_remaining FROM api_usage WHERE requests_remaining IS NOT NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    print(f"\nledger: {total} line snapshots ({today} today) | "
          f"{events} events | {books} books | bankroll ${bankroll:,.2f}"
          + (f" | API quota left: {quota[0]}" if quota else ""))
    moves = odds.line_movement(conn, hours=24)
    print(f"line movement (24h): {len(moves)} markets moved")
    for m in moves[:10]:
        who = m["player"] or m["matchup"]
        print(f"  [{m['sport']}] {who} {m['market']}/{m['side']} @{m['book']}: "
              f"line {m['open_line']} -> {m['last_line']}, odds {m['open_odds']:+d} -> {m['last_odds']:+d}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--props", action="store_true")
    ap.add_argument("--sample", metavar="FILE")
    args = ap.parse_args(argv)

    conn = db.connect()
    print("EDGE ENGINE daily run — Phase 1 (odds ingestion + line movement)")
    if args.sample:
        n = odds.ingest_payload(conn, json.loads(Path(args.sample).read_text()), raw_file=args.sample)
        print(f"sample ingest: {n} line snapshots")
    else:
        try:
            for sport, n in odds.pull_all(conn, include_props=args.props).items():
                print(f"pulled {sport}: {n} line snapshots")
        except RuntimeError as exc:
            print(f"SKIPPED live pull: {exc}")

    # Phase 2+: stats ingest -> models -> value scanner -> research -> rundown
    for name in ("stats ingest", "prop models", "value scanner", "staking", "daily rundown"):
        print(f"  [not built yet] {name} — see CLAUDE.md build phases")

    summarize(conn)
    conn.close()


if __name__ == "__main__":
    main()
