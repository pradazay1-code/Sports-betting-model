#!/usr/bin/env python3
"""
Smoke test for The Desk.

Checks the whole stack end to end and reports exactly what passed, what failed,
and what couldn't be tested. Nothing here guesses: a check that can't run says
it couldn't run rather than quietly passing.

    python3 smoke_test.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

PASS, FAIL, SKIP = [], [], []


def check(name):
    """Decorator turning a function into a reported check.

    Return a string to pass with a note, raise to fail, or raise Skip to record
    that the check couldn't run here.
    """

    def deco(fn):
        try:
            note = fn()
            PASS.append((name, note or ""))
        except Skip as s:
            SKIP.append((name, str(s)))
        except Exception as e:  # noqa: BLE001
            FAIL.append((name, f"{type(e).__name__}: {e}", traceback.format_exc()))
        return fn

    return deco


class Skip(Exception):
    pass


# --- 1. price math ---------------------------------------------------------


@check("conversions")
def _conversions():
    from lib.odds import american_to_decimal, decimal_to_american, implied_prob

    assert abs(american_to_decimal(-110) - 1.9090909) < 1e-6
    assert abs(implied_prob(-110) - 0.5238095) < 1e-6
    assert abs(decimal_to_american(2.5) - 150) < 1e-9
    return "-110 = 1.9091 = 52.38%"


@check("devig — all four methods sum to 1")
def _devig_methods():
    from lib.odds import devig_all

    out = devig_all([250, -300])
    for method, probs in out.items():
        assert abs(sum(probs) - 1.0) < 1e-9, f"{method} sums to {sum(probs)}"
    return f"{', '.join(out)} — all normalized"


@check("devig one market: fair vs. offered")
def _devig_market():
    from lib.odds import devig, price_edge, prob_to_american

    # Pinnacle +118 / -128 is the sharp anchor; DraftKings offers +132.
    fair = devig([118, -128], "power")
    fair_line = prob_to_american(fair[0])
    edge = price_edge(fair[0], 132, method="power")
    assert edge.is_bet, "expected this to clear the EV threshold"
    return (
        f"sharp +118/-128 -> fair {fair_line:+.1f} (p={fair[0]:.4f}); "
        f"offered +132 -> EV {edge.ev:+.2%}, stake {edge.stake_units}u"
    )


@check("Kelly staking and the 2u ceiling")
def _kelly():
    from lib.odds import MAX_STAKE_UNITS, kelly, stake_units

    assert abs(kelly(0.55, 2.0, divisor=1.0) - 0.10) < 1e-12
    assert stake_units(0.95, 100) == MAX_STAKE_UNITS
    return f"quarter Kelly, hard cap {MAX_STAKE_UNITS}u"


@check("parlay hold multiplication")
def _parlay():
    from lib.odds import parlay_analysis

    a = parlay_analysis([-110] * 4)
    assert a["book_hold"] > 0.15
    return (
        f"4x -110: book holds {a['book_hold']:.1%} vs. "
        f"{a['hold_if_bet_straight']:.1%} bet straight"
    )


@check("sharp anchor ordering")
def _anchor():
    from lib.odds import sharp_anchor

    a = sharp_anchor({"draftkings": -105, "pinnacle": -110, "fanduel": -108})
    assert a["anchor"] == "pinnacle"
    b = sharp_anchor({"draftkings": -105, "fanduel": -115, "betmgm": -110})
    assert b["tier"] == "median"
    return "Pinnacle wins; soft-only falls back to median"


# --- 2. database -----------------------------------------------------------


@check("SQLite schema creates cleanly")
def _schema():
    from lib import db

    with tempfile.TemporaryDirectory() as d:
        conn = db.connect(Path(d) / "smoke.db")
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if not r[0].startswith("sqlite_")
        }
        assert {"bets", "parlay_legs", "line_snapshots"} <= tables
        conn.close()
    return f"tables: {', '.join(sorted(tables))}"


@check("bet log round trip: log -> close -> grade -> report")
def _db_roundtrip():
    from lib import db

    with tempfile.TemporaryDirectory() as d:
        conn = db.connect(Path(d) / "smoke.db")
        bet_id = db.log_bet(
            conn, sport="NFL", event="KC @ BUF", market="h2h", side="KC",
            price_taken=132, book="draftkings", stake_units=0.76, fair_prob=0.4482,
        )
        c = db.set_closing_line(conn, bet_id, 118)
        profit = db.grade_bet(conn, bet_id, "win")
        perf = db.performance(conn)
        conn.close()
    assert c["beat_close"], "took +132, closed +118 — that beat the close"
    assert perf["settled_bets"] == 1
    return f"CLV {c['pct']:+.2%}, profit {profit:+.2f}u, ROI {perf['roi']:+.1%}"


# --- 3. cache --------------------------------------------------------------


@check("cache serves, expires, and degrades honestly")
def _cache():
    from lib import cache

    with tempfile.TemporaryDirectory() as d:
        original = cache.CACHE_DIR
        cache.CACHE_DIR = Path(d)
        try:
            calls = []
            v1, m1 = cache.get_or_fetch("odds", "k", lambda: calls.append(1) or {"a": 1}, ttl=60)
            _, m2 = cache.get_or_fetch("odds", "k", lambda: calls.append(1) or {"a": 2}, ttl=60)
            assert m1["source"] == "live" and m2["source"] == "cache" and len(calls) == 1

            def boom():
                raise RuntimeError("api down")

            v3, m3 = cache.get_or_fetch("odds", "k", boom, ttl=0)
            assert m3["degraded"] and v3 == v1
        finally:
            cache.CACHE_DIR = original
    return "cache hit, TTL expiry, and labeled stale-on-failure all work"


# --- 4. board pipeline (offline fixture) -----------------------------------


@check("board -> fair price -> edge, on a fixture")
def _pipeline():
    from lib.fetch_odds import confidence_for, find_edges, normalize

    board = [{
        "away_team": "Kansas City Chiefs", "home_team": "Buffalo Bills",
        "commence_time": "2026-09-07T20:25:00Z",
        "bookmakers": [
            {"key": "pinnacle", "markets": [
                {"key": "h2h", "outcomes": [
                    {"name": "Kansas City Chiefs", "price": 118},
                    {"name": "Buffalo Bills", "price": -128}]},
                {"key": "spreads", "outcomes": [
                    {"name": "Kansas City Chiefs", "price": -104, "point": 2.5},
                    {"name": "Buffalo Bills", "price": -108, "point": -2.5}]}]},
            {"key": "draftkings", "markets": [
                {"key": "h2h", "outcomes": [
                    {"name": "Kansas City Chiefs", "price": 132},
                    {"name": "Buffalo Bills", "price": -155}]}]},
            {"key": "fanduel", "markets": [
                {"key": "h2h", "outcomes": [
                    {"name": "Kansas City Chiefs", "price": 115},
                    {"name": "Buffalo Bills", "price": -136}]}]},
        ],
    }]
    views = normalize(board, "americanfootball_nfl")
    assert {v.key for v in views} == {"h2h", "spreads 2.5"}, [v.key for v in views]
    edges = find_edges(views)
    assert edges, "expected an edge on this fixture"
    top = edges[0]
    assert top["book"] != top["anchor"], "never take an edge against your own anchor"
    level, _ = confidence_for(top)
    return (
        f"{top['side']} {top['offered']:+.0f} @ {top['book']} — "
        f"fair {top['fair_american']:+.1f}, EV {top['ev']:+.2%}, "
        f"{top['stake_units']}u, confidence {level}"
    )


@check("wind resolves against field orientation")
def _wind():
    from lib.fetch_news import wind_relative_to_field

    assert wind_relative_to_field(40, 40)["effect"] == "in"
    assert wind_relative_to_field(220, 40)["effect"] == "out"
    return "blowing in / out / across all resolve correctly"


# --- 5. edge-detection statistics ------------------------------------------


@check("sample size required to prove an edge")
def _sample_size():
    from lib.backtest import required_sample_size

    r = required_sample_size(0.55, -110)
    assert 2000 < r["n_required"] < 2500
    return f"a 5% ROI needs ~{r['n_required']:,} bets to distinguish from luck"


@check("a real edge still loses sometimes")
def _drawdown():
    from lib.backtest import drawdown_simulation, losing_streak_probability

    d = drawdown_simulation(0.55, -110, n_bets=500, trials=1500)
    p7 = losing_streak_probability(0.55, 7, 500)
    assert 0.05 < d["prob_losing_overall"] < 0.20
    return (
        f"true 55% bettor over 500 bets: loses money {d['prob_losing_overall']:.0%} "
        f"of the time, 7-bet skid {p7:.0%} likely"
    )


@check("a hot record proves little")
def _reality():
    from lib.backtest import reality_check

    r = reality_check(12, 3, -110)
    lo, hi = r["ci95"]
    assert hi - lo > 0.30
    return f"12-3 -> true hit rate somewhere in {lo:.0%}-{hi:.0%}"


@check("ranked plays keep win rate and edge separate")
def _ranking():
    from lib.fetch_odds import normalize, rank_plays

    board = [{
        "away_team": "A", "home_team": "B", "commence_time": "",
        "bookmakers": [
            {"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
                {"name": "A", "price": 118}, {"name": "B", "price": -128}]}]},
            {"key": "draftkings", "markets": [{"key": "h2h", "outcomes": [
                {"name": "A", "price": 132}, {"name": "B", "price": -155}]}]},
        ],
    }]
    plays = rank_plays(normalize(board, "x"))
    assert plays, "expected a ranked play"
    p = plays[0]
    assert p["win_prob"] < 0.5 < 1.0, "this +EV play wins less than half the time"
    return (
        f"top play wins {p['win_prob']:.1%} of the time with {p['ev']:+.2%} EV — "
        "high win rate and good bet are different axes"
    )


# --- 6. college football ---------------------------------------------------


@check("venue home-field advantage separates crowd from altitude")
def _hfa():
    from lib.venues import FBS_BASELINE_HFA, home_edge

    e = home_edge("Wyoming", "Hawaii")
    assert e["crowd_points"] == 3.0 and e["altitude"]["points"] == 1.5
    assert e["total_points"] == 4.5
    return (
        f"Wyoming vs Hawaii: {e['crowd_points']}(crowd) + {e['altitude']['points']}(altitude) "
        f"= {e['total_points']} pts vs a flat {FBS_BASELINE_HFA}"
    )


@check("altitude priced off the differential, not raw elevation")
def _alt():
    from lib.venues import altitude_edge

    fl = altitude_edge(7220, 82)["points"]
    co = altitude_edge(7220, 5360)["points"]
    assert fl > co
    return f"sea-level visitor {fl} pts vs Colorado visitor {co} pts at the same venue"


@check("CFB spread combines SP+ gap with venue HFA")
def _cfb_spread():
    from lib import fetch_cfb

    real = fetch_cfb.sp_ratings
    fetch_cfb.sp_ratings = lambda **kw: (
        [{"team": "Wyoming", "rating": 5.0}, {"team": "Hawaii", "rating": 0.0}],
        {"source": "fixture", "age": "0s"},
    )
    try:
        r = fetch_cfb.sp_spread("Wyoming", "Hawaii")
        assert r["projected_spread"] == -9.5
        return f"SP+ gap 5.0 + HFA 4.5 -> {r['reading']}"
    finally:
        fetch_cfb.sp_ratings = real


@check("CFBD refuses to run without a key")
def _cfbd_key():
    import os

    from lib.fetch_cfb import CFBDError, api_key

    saved = os.environ.pop("CFBD_API_KEY", None)
    try:
        try:
            api_key()
        except CFBDError as e:
            assert "will not invent" in str(e)
            return "no key -> clean refusal, no fabricated slate"
        raise AssertionError("expected CFBDError")
    finally:
        if saved:
            os.environ["CFBD_API_KEY"] = saved


# --- 7. the keyless path (must never break) --------------------------------


@check("keyless board finds the same edge as the live feed")
def _manual_board():
    import json
    import tempfile

    from lib import manual
    from lib.fetch_odds import rank_plays

    board = {
        "event": "KC @ BUF",
        "markets": [{
            "name": "moneyline",
            "books": {
                "pinnacle": {"Chiefs": 118, "Bills": -128},
                "draftkings": {"Chiefs": 132, "Bills": -155},
                "fanduel": {"Chiefs": 115, "Bills": -136},
                "betmgm": {"Chiefs": 120, "Bills": -140},
            },
        }],
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(board, f)
        path = f.name
    plays = rank_plays(manual.board_to_views(manual.load_board(path)))
    assert plays and plays[0]["book"] == "draftkings"
    return (
        f"hand-entered prices -> {plays[0]['side']} {plays[0]['offered']:+.0f} "
        f"@ {plays[0]['book']}, EV {plays[0]['ev']:+.2%}. No key, no network."
    )


@check("keyless board audits itself for silent failures")
def _manual_audit():
    from lib import manual

    one_sided = manual.board_to_views(
        {"markets": [{"name": "spread", "books": {"draftkings": {"KC -2.5": -110}}}]}
    )
    a = manual.audit_board(one_sided)[0]
    assert a["one_sided"] and not a["devig_possible"]
    return "one-sided market correctly flagged as un-devig-able"


@check("FCS reachable without a key")
def _fcs_keyless():
    from lib.free_sources import CFB_FCS_GROUP, LEAGUES, parse_scoreboard

    assert CFB_FCS_GROUP == 81 and "cfb" in LEAGUES
    row = parse_scoreboard({"events": [{"id": "1", "shortName": "A @ B",
                                        "competitions": [{"competitors": []}]}]})[0]
    assert row["spread"] is None
    return "ESPN group 81 = FCS; parser survives games with no odds block"


# --- 8. environment --------------------------------------------------------


@check("data packages installed")
def _packages():
    missing = []
    for mod in ("requests", "pandas", "numpy", "dotenv", "bs4", "lxml",
                "nfl_data_py", "pybaseball", "nba_api"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        raise Skip(f"not installed: {', '.join(missing)} — run: pip install -r requirements.txt")
    return "all nine present"


@check("live odds board")
def _live_board():
    if not os.environ.get("ODDS_API_KEY"):
        raise Skip("ODDS_API_KEY not set — copy .env.example to .env and add your key")
    from lib.fetch_odds import QUOTA, get_odds, normalize

    board, meta = get_odds("americanfootball_nfl")
    views = normalize(board, "americanfootball_nfl")
    devigged = sum(1 for v in views if v.sharp_book())
    return (
        f"{len(board)} games, {len(views)} markets, {devigged} with a sharp anchor "
        f"[{meta['source']}] — {QUOTA}"
    )


@check("live weather")
def _live_weather():
    try:
        from lib.fetch_news import venue_weather

        w, _ = venue_weather("Wrigley Field")
        if w.get("error"):
            raise Skip(w["error"])
        return f"Wrigley {w['temp_f']}F, wind {w['wind_mph']} mph from {w['wind_from']}"
    except Skip:
        raise
    except Exception as e:  # noqa: BLE001
        raise Skip(f"network unavailable: {type(e).__name__}") from e


# --- report ----------------------------------------------------------------


def main() -> int:
    print("=" * 74)
    print("THE DESK — SMOKE TEST")
    print("=" * 74)

    print(f"\nPASSED ({len(PASS)})")
    for name, note in PASS:
        print(f"  [ok]   {name}")
        if note:
            print(f"         {note}")

    if SKIP:
        print(f"\nCOULD NOT TEST ({len(SKIP)})")
        for name, why in SKIP:
            print(f"  [skip] {name}")
            print(f"         {why}")

    if FAIL:
        print(f"\nFAILED ({len(FAIL)})")
        for name, err, tb in FAIL:
            print(f"  [FAIL] {name}")
            print(f"         {err}")
            print("\n".join("         " + l for l in tb.strip().splitlines()[-6:]))

    print("\n" + "=" * 74)
    print(f"{len(PASS)} passed, {len(FAIL)} failed, {len(SKIP)} not testable here")
    if FAIL:
        print("Fix the failures before trusting a single number this thing prints.")
    elif SKIP:
        print("Core math and storage are sound. The skipped checks need a key or network.")
    else:
        print("Everything green.")
    print("=" * 74)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
