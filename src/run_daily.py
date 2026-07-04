"""Daily orchestrator (spec §1, §7): ingest -> model -> scan -> stake -> report.

    python -m src.run_daily                       # live run (needs ODDS_API_KEY)
    python -m src.run_daily --props               # include player-prop pulls
    python -m src.run_daily --demo                # fixture-driven dry run, no network
    python -m src.run_daily --date YYYY-MM-DD
"""

from __future__ import annotations

import argparse
import json
from datetime import date as date_cls
from pathlib import Path

from src import config, db
from src.engine import value_scanner
from src.ingest import mlb, odds
from src.models import mlb_model
from src.report import daily_rundown


def match_odds_event(conn, home_team: str, away_team: str) -> str | None:
    row = conn.execute(
        "SELECT event_id FROM events WHERE home_team = ? AND away_team = ?",
        (home_team, away_team)).fetchone()
    return row["event_id"] if row else None


def mlb_candidates(conn, day: str) -> list[dict]:
    """K-prop candidates: every projected starter x every K line side."""
    season = int(day[:4])
    candidates = []
    seen: set[tuple] = set()   # doubleheaders map two games to one odds event
    for game in mlb.todays_games(conn, day):
        event_id = match_odds_event(conn, game["home_team"], game["away_team"])
        if not event_id:
            continue
        for proj in mlb_model.project_game_strikeouts(conn, game, season):
            if (event_id, proj.player_name) in seen:
                continue
            seen.add((event_id, proj.player_name))
            lines = conn.execute(
                """SELECT DISTINCT line FROM line_snapshots
                   WHERE event_id = ? AND market = 'pitcher_strikeouts' AND player = ?""",
                (event_id, proj.player_name)).fetchall()
            for row in lines:
                line = row["line"]
                if line is None:
                    continue
                for side, prob in (("over", proj.prob_over(line)),
                                   ("under", proj.prob_under(line))):
                    candidates.append({
                        "sport": "baseball_mlb", "event_id": event_id,
                        "market": "pitcher_strikeouts", "player": proj.player_name,
                        "side": side, "model_prob": prob,
                        "sample_games": proj.sample_games,
                        "_inputs": proj.inputs,
                    })
    return candidates


def write_picks(conn, edges: list, staked: dict[int, tuple[float, bool]] | None = None) -> int:
    """Persist surfaced edges as pending picks; below-threshold as no_play rows."""
    n = 0
    for i, e in enumerate(edges):
        stake, is_paper = (staked or {}).get(i, (0.0, True))
        why = "; ".join(e.tier_notes) if e.tier_notes else None
        inputs = e.inputs.get("_inputs") if isinstance(e.inputs, dict) else None
        if inputs:
            why = (why + " | " if why else "") + f"model inputs: {json.dumps(inputs)}"
        conn.execute(
            """INSERT INTO picks (created_at, sport, event_id, market, player, side,
                 line, book, odds_american, odds_decimal, model_prob, market_fair_prob,
                 ev_pct, tier, stake_units, is_paper, needs_research, status, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (db.utcnow(), e.sport, e.event_id, e.market, e.player, e.side, e.line,
             e.book, e.odds_american, e.odds_decimal, e.model_prob, e.fair_prob,
             e.ev, e.tier if e.surface else None, stake, int(is_paper),
             int(e.needs_research), "pending" if e.surface else "no_play", why))
        n += 1
    conn.commit()
    return n


def run(day: str, live: bool, include_props: bool, demo: bool) -> None:
    conn = db.connect()
    print(f"EDGE ENGINE daily run — {day}")

    # 1. market: odds + prop lines
    if demo:
        fixture = Path("tests/fixtures/odds_api_sample.json")
        n = odds.ingest_payload(conn, json.loads(fixture.read_text()), raw_file=str(fixture))
        print(f"[demo] odds: {n} line snapshots from fixture")
    elif live:
        try:
            for sport, n in odds.pull_all(conn, include_props=include_props).items():
                print(f"odds {sport}: {n} snapshots")
        except RuntimeError as exc:
            print(f"odds pull skipped: {exc}")

    # 2. truth: MLB stats
    if demo:
        fx = Path("tests/fixtures")
        mlb.store_games(conn, mlb.parse_schedule(json.loads((fx / "mlb_schedule.json").read_text())))
        mlb.store_pitcher_logs(conn, mlb.parse_pitcher_gamelog(
            json.loads((fx / "mlb_gamelog_cole.json").read_text()), 543037))
        mlb.store_team_batting(conn, mlb.parse_team_splits(
            json.loads((fx / "mlb_team_splits_bos.json").read_text()), 111, 2026))
        print("[demo] mlb: fixtures ingested")
    elif live:
        stats = mlb.pull_day(conn, day)
        print(f"mlb: {stats}")

    # 3+4. model -> value scan (scan attaches _inputs and dedupes)
    candidates = mlb_candidates(conn, day)
    edges = value_scanner.scan(conn, candidates)
    surfaced = [e for e in edges if e.surface]
    print(f"model: {len(candidates)} candidates -> {len(surfaced)} surfaced edges")

    # 5. staking (Phase 3) then ledger
    staked = None
    try:
        from src.engine import staking
        staked = staking.apply(conn, edges)
    except (ImportError, NotImplementedError):
        print("staking: Phase 3 module not built — picks logged track-only")
    write_picks(conn, edges, staked)

    # 5b. injuries + lineup gate, research briefs for flagged edges
    from src.ingest import injuries
    from src.research import deep_dive
    if live and not demo:
        injuries.pull_all(conn)
    injuries.hold_ungated_picks(conn)
    research = deep_dive.run_research(conn, day)
    if research["briefs"]:
        print(f"research: {research}")

    # 6. DFS slips (Phase 4) + rundown
    from src.engine import correlation
    slips = correlation.build_slips(surfaced)
    no_plays = [{"player": e.player, "side": e.side, "line": e.line,
                 "market": e.market, "ev": e.ev,
                 "reason": f"EV below {config.settings()['edges']['min_ev_props']:.0%} threshold"}
                for e in edges if not e.surface and e.ev > 0.015]
    path = daily_rundown.write_report(conn, day, no_plays, slips)
    print(f"rundown: {path}")
    print()
    print(Path(path).read_text())
    conn.close()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--props", action="store_true")
    ap.add_argument("--demo", action="store_true", help="fixture dry run, no network")
    ap.add_argument("--date", default=date_cls.today().isoformat())
    args = ap.parse_args(argv)
    run(args.date, live=not args.demo, include_props=args.props, demo=args.demo)


if __name__ == "__main__":
    main()
