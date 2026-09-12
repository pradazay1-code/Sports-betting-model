"""
College football data — CollegeFootballData.com (CFBD) client, FBS and FCS.

CFBD is the single best free data source in college football and it covers
**both divisions**, which matters: FCS games are nearly unmodellable from
mainstream sources, and `division=fcs` here is the difference between having
numbers and guessing.

Get a free key at https://collegefootballdata.com/key and put it in `.env` as
`CFBD_API_KEY`. Without it this module refuses to run rather than guessing.

What matters most for betting, in order:

  1. **SP+** — opponent-adjusted efficiency. In a sport where nobody plays a
     comparable schedule, raw stats are noise. SP+ is the spine of any honest
     CFB number.
  2. **Betting lines** (`/lines`) — CFBD carries consensus and per-book history,
     which is how you see line movement without a paid feed.
  3. **Talent composite** — recruiting-rating aggregate. Predicts blowouts
     better than efficiency does, because depth shows up in the fourth quarter.
  4. **Returning production** — the best single predictor of year-over-year
     change, and in the portal era it is badly mispriced by the public.
  5. **Advanced season stats** — success rate, explosiveness, havoc rate,
     finishing drives, with garbage time stripped.

CLI:
    python3 -m lib.fetch_cfb games --week 3
    python3 -m lib.fetch_cfb games --week 3 --division fcs
    python3 -m lib.fetch_cfb lines --week 3
    python3 -m lib.fetch_cfb sp --team Alabama
    python3 -m lib.fetch_cfb talent
    python3 -m lib.fetch_cfb returning --team Georgia
    python3 -m lib.fetch_cfb advanced --team Oregon
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib import cache

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

BASE = "https://api.collegefootballdata.com"

#: ESPN public JSON, used as a no-key fallback for schedule/scores only.
ESPN_FBS = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"


class CFBDError(RuntimeError):
    """A CFBD fetch failed. We raise rather than return a plausible-looking slate."""


def api_key() -> str:
    key = os.environ.get("CFBD_API_KEY", "").strip()
    if not key:
        raise CFBDError(
            "CFBD_API_KEY is not set. Get a free key at "
            "https://collegefootballdata.com/key and add it to .env. "
            "I will not invent college football data."
        )
    return key


def current_season() -> int:
    """CFB seasons are labeled by the year they start; flips in the spring."""
    now = datetime.now(timezone.utc)
    return now.year if now.month >= 3 else now.year - 1


def _get(path: str, params: dict[str, Any], *, ttl: float | None = None, ns: str = "stats") -> Any:
    if requests is None:
        raise CFBDError("`requests` isn't installed. pip install -r requirements.txt")

    clean = {k: v for k, v in params.items() if v is not None}
    ck = f"cfbd:{path}:" + ",".join(f"{k}={v}" for k, v in sorted(clean.items()))

    def fetch():
        r = requests.get(
            f"{BASE}{path}",
            params=clean,
            headers={"Authorization": f"Bearer {api_key()}", "Accept": "application/json"},
            timeout=30,
        )
        if r.status_code == 401:
            raise CFBDError("401 from CFBD — the key in .env is wrong or expired.")
        if r.status_code == 429:
            raise CFBDError("429 from CFBD — rate limited. Back off and retry.")
        if not r.ok:
            raise CFBDError(f"{r.status_code} from CFBD {path}: {r.text[:250]}")
        return r.json()

    return cache.get_or_fetch(ns, ck, fetch, ttl=ttl)


# ---------------------------------------------------------------------------
# Schedule and results — FBS and FCS
# ---------------------------------------------------------------------------


def games(
    *,
    year: int | None = None,
    week: int | None = None,
    team: str | None = None,
    division: str = "fbs",
    season_type: str = "regular",
) -> tuple[list[dict], dict]:
    """
    Schedule and results. `division` accepts "fbs" or "fcs".

    FCS coverage is the reason this module exists. Mainstream feeds carry FBS
    only, and an FCS slate priced off vibes is how bankrolls die.
    """
    return _get(
        "/games",
        {
            "year": year or current_season(),
            "week": week,
            "team": team,
            "division": division,
            "seasonType": season_type,
        },
        ttl=1800,
        ns="odds",
    )


def lines(
    *,
    year: int | None = None,
    week: int | None = None,
    team: str | None = None,
    season_type: str = "regular",
) -> tuple[list[dict], dict]:
    """
    Betting lines by game, with per-provider spreads, totals, and moneylines.

    This is how you see **line movement and book disagreement** in CFB without
    a paid feed. Providers typically include Bovada, DraftKings, ESPN Bet and a
    consensus. Treat the consensus as a median anchor, not a sharp price — none
    of these are Pinnacle.
    """
    return _get(
        "/lines",
        {"year": year or current_season(), "week": week, "team": team, "seasonType": season_type},
        ttl=900,
        ns="odds",
    )


# ---------------------------------------------------------------------------
# Ratings — the spine of a CFB number
# ---------------------------------------------------------------------------


def sp_ratings(*, year: int | None = None, team: str | None = None) -> tuple[list[dict], dict]:
    """
    SP+ — Bill Connelly's opponent-adjusted efficiency rating.

    `rating` is points per game above average against an average schedule.
    The difference between two teams' SP+ ratings, plus home field, is a
    defensible first-pass spread. Start there, then adjust.
    """
    return _get("/ratings/sp", {"year": year or current_season(), "team": team}, ttl=21600)


def srs_ratings(*, year: int | None = None, team: str | None = None) -> tuple[list[dict], dict]:
    """Simple Rating System — margin-based, schedule-adjusted. A useful cross-check."""
    return _get("/ratings/srs", {"year": year or current_season(), "team": team}, ttl=21600)


def elo_ratings(*, year: int | None = None, week: int | None = None,
                team: str | None = None) -> tuple[list[dict], dict]:
    return _get("/ratings/elo", {"year": year or current_season(), "week": week, "team": team}, ttl=21600)


def talent(*, year: int | None = None) -> tuple[list[dict], dict]:
    """
    Team talent composite — aggregated recruiting ratings.

    **Talent predicts blowouts better than efficiency does.** Depth shows up
    late, and a talent chasm means the backups are also better. This is the
    metric to reach for on large spreads and on FBS-vs-FCS money games.
    """
    return _get("/talent", {"year": year or current_season()}, ttl=86400)


def returning_production(*, year: int | None = None, team: str | None = None) -> tuple[list[dict], dict]:
    """
    Returning production — share of last year's usage that returns.

    The best single predictor of year-over-year change, and systematically
    mispriced in the portal era because the public anchors on last season's
    record and the recruiting-class headline instead of on who is actually back.
    """
    return _get("/player/returning", {"year": year or current_season(), "team": team}, ttl=86400)


def advanced_stats(*, year: int | None = None, team: str | None = None,
                   exclude_garbage_time: bool = True) -> tuple[list[dict], dict]:
    """
    Advanced season stats: success rate, explosiveness (PPA), havoc, finishing drives.

    **Garbage time is excluded by default and you should keep it that way.**
    College football is full of 40-point blowouts; unfiltered numbers let a bad
    team's fourth-quarter yardage against walk-ons masquerade as competence.
    """
    return _get(
        "/stats/season/advanced",
        {
            "year": year or current_season(),
            "team": team,
            "excludeGarbageTime": str(bool(exclude_garbage_time)).lower(),
        },
        ttl=21600,
    )


def team_records(*, year: int | None = None, team: str | None = None) -> tuple[list[dict], dict]:
    return _get("/records", {"year": year or current_season(), "team": team}, ttl=21600)


# ---------------------------------------------------------------------------
# Derived: a first-pass number
# ---------------------------------------------------------------------------


def sp_spread(home: str, away: str, *, year: int | None = None,
              hfa_points: float | None = None) -> dict:
    """
    First-pass spread from SP+ plus a venue-specific home edge.

    This is a STARTING POINT, not a projection. It knows nothing about injuries,
    weather, motivation, or who is actually taking snaps — and in college
    football those routinely outweigh the rating gap. Anchor on the market, use
    this to decide whether you have a reason to disagree.
    """
    from lib.venues import home_edge

    data, meta = sp_ratings(year=year)
    by_team = {d.get("team", "").lower(): d for d in data}
    h = by_team.get(home.lower())
    a = by_team.get(away.lower())
    if h is None or a is None:
        missing = [t for t, d in ((home, h), (away, a)) if d is None]
        raise CFBDError(f"no SP+ rating found for: {', '.join(missing)}")

    edge = home_edge(home, away)
    hfa = hfa_points if hfa_points is not None else edge["total_points"]
    diff = float(h.get("rating", 0)) - float(a.get("rating", 0))
    spread = -(diff + hfa)  # negative = home favored

    return {
        "home": home,
        "away": away,
        "home_sp": h.get("rating"),
        "away_sp": a.get("rating"),
        "sp_differential": round(diff, 2),
        "home_field_points": hfa,
        "home_field_detail": edge,
        "projected_spread": round(spread, 1),
        "reading": f"{home} {spread:+.1f}",
        "meta": meta,
        "caveat": (
            "SP+ plus home field only. No injuries, weather, motivation, or "
            "QB status. Anchor on the market before trusting this."
        ),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _meta(m: dict) -> str:
    return f"  !! {m['warning']}" if m.get("degraded") else f"  [{m['source']}, age {m['age']}]"


def _cmd_games(args) -> int:
    try:
        data, meta = games(year=args.year, week=args.week, team=args.team, division=args.division)
    except CFBDError as e:
        print(f"FETCH FAILED: {e}")
        return 1
    print(_meta(meta))
    print(f"\n{len(data)} {args.division.upper()} games, week {args.week or 'all'}:\n")
    for g in data[: args.limit]:
        hp, ap = g.get("home_points"), g.get("away_points")
        score = f"  {ap}-{hp}" if hp is not None else ""
        print(f"  {g.get('away_team','?'):<28} @ {g.get('home_team','?'):<28}"
              f" {g.get('start_date','')[:16]}{score}")
    return 0


def _cmd_lines(args) -> int:
    try:
        data, meta = lines(year=args.year, week=args.week, team=args.team)
    except CFBDError as e:
        print(f"FETCH FAILED: {e}")
        return 1
    print(_meta(meta))
    for g in data[: args.limit]:
        print(f"\n{g.get('awayTeam')} @ {g.get('homeTeam')}")
        for ln in g.get("lines", []):
            print(f"    {ln.get('provider',''):<14} spread {str(ln.get('spread','')):>7}"
                  f"  total {str(ln.get('overUnder','')):>6}"
                  f"  ML {ln.get('homeMoneyline','')}/{ln.get('awayMoneyline','')}")
        if not g.get("lines"):
            print("    no lines posted")
    print("\nConsensus is a MEDIAN anchor, not a sharp price. None of these are Pinnacle.")
    return 0


def _cmd_sp(args) -> int:
    try:
        data, meta = sp_ratings(year=args.year, team=args.team)
    except CFBDError as e:
        print(f"FETCH FAILED: {e}")
        return 1
    print(_meta(meta))
    rows = sorted(data, key=lambda d: -(d.get("rating") or -99))
    print(f"\n{'team':<26}{'SP+':>8}{'off':>8}{'def':>8}")
    for d in rows[: args.limit]:
        off = (d.get("offense") or {}).get("rating")
        dfn = (d.get("defense") or {}).get("rating")
        print(f"{d.get('team',''):<26}{d.get('rating') or 0:>8.1f}"
              f"{off or 0:>8.1f}{dfn or 0:>8.1f}")
    return 0


def _cmd_talent(args) -> int:
    try:
        data, meta = talent(year=args.year)
    except CFBDError as e:
        print(f"FETCH FAILED: {e}")
        return 1
    print(_meta(meta))
    rows = sorted(data, key=lambda d: -float(d.get("talent") or 0))
    for d in rows[: args.limit]:
        print(f"  {d.get('team',''):<26}{float(d.get('talent') or 0):>9.1f}")
    print("\nTalent predicts BLOWOUTS better than efficiency does — depth shows up late.")
    return 0


def _cmd_returning(args) -> int:
    try:
        data, meta = returning_production(year=args.year, team=args.team)
    except CFBDError as e:
        print(f"FETCH FAILED: {e}")
        return 1
    print(_meta(meta))
    for d in data[: args.limit]:
        print(f"  {d.get('team',''):<24} total {d.get('totalPPA') or 0:>6}"
              f"  pass {d.get('percentPassingPPA') or 0:>6}"
              f"  rush {d.get('percentRushingPPA') or 0:>6}")
    return 0


def _cmd_advanced(args) -> int:
    try:
        data, meta = advanced_stats(year=args.year, team=args.team)
    except CFBDError as e:
        print(f"FETCH FAILED: {e}")
        return 1
    print(_meta(meta))
    for d in data[: args.limit]:
        o = d.get("offense") or {}
        dd = d.get("defense") or {}
        print(f"\n  {d.get('team','')}")
        print(f"    off: success {o.get('successRate')}  explosive {o.get('explosiveness')}"
              f"  PPA {o.get('ppa')}")
        print(f"    def: success {dd.get('successRate')}  explosive {dd.get('explosiveness')}"
              f"  havoc {(dd.get('havoc') or {}).get('total')}")
    print("\nGarbage time excluded. Keep it that way.")
    return 0


def _cmd_spread(args) -> int:
    try:
        r = sp_spread(args.home, args.away, year=args.year)
    except CFBDError as e:
        print(f"FETCH FAILED: {e}")
        return 1
    print(f"{args.away} @ {args.home}")
    print(f"  SP+          : {r['home_sp']:.1f} vs {r['away_sp']:.1f}  (diff {r['sp_differential']:+.2f})")
    print(f"  home field   : {r['home_field_points']:+.2f} pts "
          f"({r['home_field_detail'].get('venue') or 'baseline'})")
    print(f"  PROJECTION   : {r['reading']}")
    print(f"\n  {r['caveat']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lib.fetch_cfb", description="The Desk — college football data.")
    p.add_argument("--year", type=int, default=None)
    p.add_argument("--limit", type=int, default=25)
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("games", help="schedule/results (FBS or FCS)")
    g.add_argument("--week", type=int, default=None)
    g.add_argument("--team", default=None)
    g.add_argument("--division", default="fbs", choices=["fbs", "fcs"])
    g.set_defaults(func=_cmd_games)

    ln = sub.add_parser("lines", help="betting lines by game")
    ln.add_argument("--week", type=int, default=None)
    ln.add_argument("--team", default=None)
    ln.set_defaults(func=_cmd_lines)

    sp = sub.add_parser("sp", help="SP+ ratings")
    sp.add_argument("--team", default=None)
    sp.set_defaults(func=_cmd_sp)

    sub.add_parser("talent", help="team talent composite").set_defaults(func=_cmd_talent)

    rp = sub.add_parser("returning", help="returning production")
    rp.add_argument("--team", default=None)
    rp.set_defaults(func=_cmd_returning)

    ad = sub.add_parser("advanced", help="advanced season stats, garbage time excluded")
    ad.add_argument("--team", default=None)
    ad.set_defaults(func=_cmd_advanced)

    spr = sub.add_parser("spread", help="first-pass spread from SP+ and venue HFA")
    spr.add_argument("--home", required=True)
    spr.add_argument("--away", required=True)
    spr.set_defaults(func=_cmd_spread)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
