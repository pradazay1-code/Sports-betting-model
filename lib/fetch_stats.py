"""
Per-sport stat pulls.

Heavy dependencies (`nfl_data_py`, `pybaseball`, `nba_api`) are imported lazily
inside each function, so this module loads and its CLI runs even when they
aren't installed. If one is missing you get a clear message naming the package —
not an ImportError traceback and not a fabricated number.

What this module is for: the *model layer*. It computes the rate stats the skill
files ask for, at the team and player level. It deliberately does not project
scores or spit out a "pick" — the market does the projecting and this supplies
the evidence for disagreeing with it.

CLI:
    python3 -m lib.fetch_stats nfl-team --season 2025
    python3 -m lib.fetch_stats nfl-epa --season 2025 --team KC
    python3 -m lib.fetch_stats mlb-pitcher --name "Tarik Skubal"
    python3 -m lib.fetch_stats nba-team --season 2025-26
    python3 -m lib.fetch_stats ufc-fighter --name "Islam Makhachev"
    python3 -m lib.fetch_stats check
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any

from lib import cache

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore


class MissingDependency(RuntimeError):
    """A data package isn't installed. Say so; never substitute a guess."""


def _need(module: str, package: str):
    try:
        return __import__(module)
    except ImportError as e:
        raise MissingDependency(
            f"`{module}` isn't installed, so I can't pull this data. "
            f"Install it with: pip install {package}"
        ) from e


def current_nfl_season() -> int:
    """NFL seasons are labeled by the year they start; the new one flips in March."""
    now = datetime.now(timezone.utc)
    return now.year if now.month >= 3 else now.year - 1


# ---------------------------------------------------------------------------
# NFL — nflverse via nfl_data_py
# ---------------------------------------------------------------------------


def nfl_team_epa(season: int | None = None, *, weeks: int | None = None) -> dict:
    """
    Team EPA/play, success rate, and early-down pass rate — offense and defense.

    Splitting EPA by early-down pass rate is the point: teams that pass early and
    often generate more EPA per play than their talent implies, and a raw EPA
    ranking quietly encodes play-calling tendency as if it were quality. Late-down
    and garbage-time plays are filtered out for the same reason.

    Returns a dict keyed by team abbreviation. Everything here is [MODEL] output
    computed off [FACT] play-by-play — label it that way downstream.
    """
    nfl = _need("nfl_data_py", "nfl_data_py")
    pd = _need("pandas", "pandas")
    season = season or current_nfl_season()

    key = f"nfl_epa:{season}:{weeks}"
    cached = cache.read("stats", key)
    if cached and not cached.stale:
        return cached.value

    pbp = nfl.import_pbp_data([season], downcast=True, cache=False)
    # Real scrimmage plays only. wp filters strip garbage time, where EPA is
    # generated against defenses that have stopped caring.
    df = pbp[
        (pbp["play_type"].isin(["run", "pass"]))
        & (pbp["epa"].notna())
        & (pbp["wp"].between(0.05, 0.95))
    ]
    if weeks:
        df = df[df["week"] > df["week"].max() - weeks]

    early = df[df["down"].isin([1, 2])]

    def agg(frame, team_col: str, label: str):
        g = frame.groupby(team_col)
        return pd.DataFrame(
            {
                f"{label}_epa_play": g["epa"].mean(),
                f"{label}_success": g["success"].mean(),
                f"{label}_plays": g["epa"].size(),
            }
        )

    off = agg(df, "posteam", "off")
    dfn = agg(df, "defteam", "def")
    off_early = agg(early, "posteam", "off_early")
    def_early = agg(early, "defteam", "def_early")

    edpr = early.groupby("posteam")["pass"].mean().rename("early_down_pass_rate")
    explosive = (
        df.assign(expl=(df["yards_gained"] >= 20).astype(float))
        .groupby("posteam")["expl"]
        .mean()
        .rename("explosive_rate")
    )
    pass_df = df[df["play_type"] == "pass"]
    sack_rate = (
        pass_df.assign(s=pass_df["sack"].fillna(0))
        .groupby("posteam")["s"]
        .mean()
        .rename("sack_rate_allowed")
    )
    sack_rate_def = (
        pass_df.assign(s=pass_df["sack"].fillna(0))
        .groupby("defteam")["s"]
        .mean()
        .rename("sack_rate_generated")
    )

    out = off.join([dfn, off_early, def_early, edpr, explosive, sack_rate, sack_rate_def], how="outer")
    out["net_epa"] = out["off_epa_play"] - out["def_epa_play"]
    out = out.sort_values("net_epa", ascending=False)

    result = {
        "season": season,
        "weeks_filter": weeks,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_plays": int(len(df)),
        "filters": "run/pass only, win prob 5-95% (garbage time stripped)",
        "teams": json.loads(out.round(4).to_json(orient="index")),
    }
    cache.write("stats", key, result)
    return result


def nfl_schedule(season: int | None = None) -> Any:
    """Schedule with results and, where nflverse has them, closing spreads/totals."""
    nfl = _need("nfl_data_py", "nfl_data_py")
    season = season or current_nfl_season()
    return nfl.import_schedules([season])


def nfl_snap_counts(season: int | None = None) -> Any:
    """Snap share drives every NFL player prop. Usage first, talent second."""
    nfl = _need("nfl_data_py", "nfl_data_py")
    return nfl.import_snap_counts([season or current_nfl_season()])


def nfl_injuries(season: int | None = None) -> Any:
    nfl = _need("nfl_data_py", "nfl_data_py")
    return nfl.import_injuries([season or current_nfl_season()])


# ---------------------------------------------------------------------------
# MLB — statsapi (free) + pybaseball for Statcast
# ---------------------------------------------------------------------------


def mlb_schedule(date: str | None = None) -> tuple[list[dict], dict]:
    """Today's slate off the free MLB StatsAPI. No key, no dependency."""
    if requests is None:
        raise MissingDependency("`requests` isn't installed. pip install requests")
    d = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def fetch():
        r = requests.get(
            "https://statsapi.mlb.com/api/v1/schedule",
            params={"sportId": 1, "date": d, "hydrate": "team,probablePitcher,venue"},
            timeout=20,
        )
        r.raise_for_status()
        return r.json()

    data, meta = cache.get_or_fetch("stats", f"mlb_sched:{d}", fetch, ttl=1800)
    games = []
    for day in data.get("dates", []):
        for g in day.get("games", []):
            t = g.get("teams", {})
            games.append(
                {
                    "game_pk": g.get("gamePk"),
                    "start": g.get("gameDate"),
                    "venue": (g.get("venue") or {}).get("name"),
                    "away": (t.get("away", {}).get("team") or {}).get("name"),
                    "home": (t.get("home", {}).get("team") or {}).get("name"),
                    "away_pitcher": (t.get("away", {}).get("probablePitcher") or {}).get("fullName", "TBD"),
                    "home_pitcher": (t.get("home", {}).get("probablePitcher") or {}).get("fullName", "TBD"),
                }
            )
    return games, meta


def mlb_pitcher_statcast(name: str, *, season: int | None = None) -> dict:
    """
    Statcast profile for a pitcher: CSW%, whiff, barrel and hard-hit allowed,
    plus the ERA/xFIP/SIERA gap.

    The ERA-to-xFIP gap is the regression flag. A starter with a 2.40 ERA and a
    4.10 xFIP is not a 2.40 pitcher, and the market usually knows that before the
    box-score crowd does.
    """
    pb = _need("pybaseball", "pybaseball")
    season = season or datetime.now(timezone.utc).year
    key = f"mlb_pitcher:{name.lower()}:{season}"
    cached = cache.read("stats", key)
    if cached and not cached.stale:
        return cached.value

    parts = name.split()
    if len(parts) < 2:
        raise ValueError("give a full name, e.g. 'Tarik Skubal'")
    lookup = pb.playerid_lookup(parts[-1], " ".join(parts[:-1]))
    if lookup.empty:
        raise LookupError(f"no player found named {name!r}. Check the spelling.")
    row = lookup.iloc[0]
    mlbam = int(row["key_mlbam"])

    sc = pb.statcast_pitcher(f"{season}-03-01", f"{season}-11-15", mlbam)
    if sc.empty:
        raise LookupError(f"no Statcast pitches for {name} in {season}.")

    called_or_swstr = sc["description"].isin(
        ["called_strike", "swinging_strike", "swinging_strike_blocked"]
    )
    swings = sc["description"].isin(
        ["swinging_strike", "swinging_strike_blocked", "foul", "foul_tip", "hit_into_play"]
    )
    whiffs = sc["description"].isin(["swinging_strike", "swinging_strike_blocked"])
    bip = sc[sc["launch_speed"].notna()]

    result = {
        "name": name,
        "mlbam_id": mlbam,
        "season": season,
        "pitches": int(len(sc)),
        "csw_pct": float(called_or_swstr.mean()),
        "whiff_pct": float(whiffs.sum() / swings.sum()) if swings.sum() else None,
        "hard_hit_pct_allowed": float((bip["launch_speed"] >= 95).mean()) if len(bip) else None,
        "avg_exit_velo_allowed": float(bip["launch_speed"].mean()) if len(bip) else None,
        "barrel_pct_allowed": (
            float((sc["launch_speed_angle"] == 6).mean()) if "launch_speed_angle" in sc else None
        ),
        "avg_velo": float(sc["release_speed"].mean()) if "release_speed" in sc else None,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": (
            "CSW% above ~30 is strong, below ~27 is weak. Hard-hit allowed above ~40% "
            "means the results are living on defense and will regress."
        ),
    }
    cache.write("stats", key, result)
    return result


SAVANT_PARK_FACTORS = "https://baseballsavant.mlb.com/leaderboard/statcast-park-factors"


def mlb_park_factors(*, season: int | None = None, ttl: float | None = None) -> tuple[list[dict], dict]:
    """
    Park factors from Baseball Savant's leaderboard (CSV export).

    Cached for a week — these barely move within a season. An index of 100 is
    neutral; 112 means the park inflates that stat 12%.

    They are NOT a substitute for the day's weather. Coors plays like Coors
    every day; Wrigley plays like two different parks depending on the wind, and
    a park factor averages those two into a number that describes neither.
    """
    if requests is None:
        raise MissingDependency("`requests` isn't installed. pip install requests")
    season = season or datetime.now(timezone.utc).year

    def fetch():
        r = requests.get(
            SAVANT_PARK_FACTORS,
            params={
                "type": "year",
                "year": season,
                "batSide": "",
                "stat": "index_wOBA",
                "condition": "All",
                "rolling": "",
                "sort": "1",
                "sortDir": "desc",
                "csv": "true",
            },
            timeout=25,
            headers={"User-Agent": "Mozilla/5.0 (compatible; the-desk/0.1)"},
        )
        r.raise_for_status()
        text = r.text.strip()
        if not text or text.lstrip().startswith("<"):
            raise RuntimeError(
                "Savant returned HTML rather than CSV — the export parameters have "
                "changed. Pull the leaderboard by hand and cite the year."
            )
        import csv as _csv
        import io as _io

        return list(_csv.DictReader(_io.StringIO(text)))

    return cache.get_or_fetch("static", f"mlb_parks:{season}", fetch, ttl=ttl)


# ---------------------------------------------------------------------------
# NBA — nba_api
# ---------------------------------------------------------------------------


def nba_team_ratings(season: str | None = None) -> dict:
    """
    Team offensive/defensive/net rating per 100, pace, and the four factors.

    Note `season` is the NBA's own format: "2025-26".
    """
    _need("nba_api", "nba_api")
    from nba_api.stats.endpoints import leaguedashteamstats  # noqa: PLC0415

    season = season or _current_nba_season()
    key = f"nba_ratings:{season}"
    cached = cache.read("stats", key)
    if cached and not cached.stale:
        return cached.value

    adv = leaguedashteamstats.LeagueDashTeamStats(
        season=season, measure_type_detailed_defense="Advanced", per_mode_detailed="Per100Possessions"
    ).get_data_frames()[0]
    four = leaguedashteamstats.LeagueDashTeamStats(
        season=season, measure_type_detailed_defense="Four Factors", per_mode_detailed="Per100Possessions"
    ).get_data_frames()[0]

    merged = adv.merge(four, on="TEAM_ID", suffixes=("", "_ff"))
    result = {
        "season": season,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "teams": json.loads(merged.to_json(orient="records")),
        "note": "Season-long ratings. For a game number you want the injury-adjusted "
                "lineup projection, not this — check who's actually playing.",
    }
    cache.write("stats", key, result)
    return result


def _current_nba_season() -> str:
    now = datetime.now(timezone.utc)
    start = now.year if now.month >= 10 else now.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def nba_injuries_note() -> str:
    return (
        "nba_api has no clean injury endpoint. Use lib.fetch_news.get_injuries('nba') "
        "for the ESPN feed, then confirm with beat writers — NBA statuses flip inside "
        "the last hour more than any other sport, and the market moves with them."
    )


# ---------------------------------------------------------------------------
# UFC / BKFC — scraped, because there is no API
# ---------------------------------------------------------------------------


UFCSTATS_SEARCH = "http://ufcstats.com/statistics/fighters/search"


def ufc_fighter(name: str, *, ttl: float | None = None) -> tuple[dict, dict]:
    """
    Career striking and grappling rates from UFCStats.

    These are *career* rates and that is a real limitation: they blend a
    fighter's prime with their decline, and a 38-year-old's career SApM flatters
    them badly. Weight recent fights heavily and say when you're doing it.
    """
    if requests is None:
        raise MissingDependency("`requests` isn't installed.")
    _need("bs4", "beautifulsoup4")
    from bs4 import BeautifulSoup  # noqa: PLC0415

    last = name.split()[-1].lower()

    def fetch():
        r = requests.get(
            UFCSTATS_SEARCH,
            params={"query": last, "page": "all"},
            timeout=25,
            headers={"User-Agent": "Mozilla/5.0 (compatible; the-desk/0.1)"},
        )
        r.raise_for_status()
        return r.text

    html, meta = cache.get_or_fetch("stats", f"ufc:{last}", fetch, ttl=ttl or 86400)
    soup = BeautifulSoup(html, "lxml")

    rows = soup.select("tr.b-statistics__table-row")
    hits = []
    for tr in rows:
        cells = [td.get_text(strip=True) for td in tr.select("td")]
        if len(cells) < 3 or not cells[0]:
            continue
        full = f"{cells[0]} {cells[1]}".strip()
        if name.split()[0].lower() in full.lower() or last in full.lower():
            link = tr.select_one("a")
            hits.append({"name": full, "nickname": cells[2] if len(cells) > 2 else "",
                         "url": link["href"] if link else None, "row": cells})

    if not hits:
        return (
            {
                "query": name,
                "found": False,
                "note": (
                    f"No UFCStats result for {name!r}. Don't proceed on memory — either "
                    "the spelling is off or the fighter isn't in the UFC database "
                    "(common for BKFC and regional fighters)."
                ),
            },
            meta,
        )

    return (
        {
            "query": name,
            "found": True,
            "matches": hits[:5],
            "note": (
                "This is the search row only. Fetch the fighter's own page for "
                "SLpM/SApM, accuracy, defense, TD rates and control time — and "
                "check the last 3 fights separately, because career rates hide decline."
            ),
        },
        meta,
    )


BKFC_NOTE = """
BKFC has no structured data source worth the name. There is no equivalent of
UFCStats: no strike-accuracy tables, no control-time logs, no reliable
round-by-round anything.

What that means in practice:
  - Every BKFC number you see should come from a named source you actually
    fetched (BKFC's own site, Tapology) or it doesn't get used.
  - Fight-film reads are [READ], not [FACT], and must be labeled as such.
  - Confidence on any BKFC play starts at low and has to earn its way up.
See skills/sport-bkfc.md for what actually predicts in this sport.
""".strip()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_check(args) -> int:
    """Which data packages are actually available here."""
    checks = [
        ("requests", "requests", "odds, weather, MLB StatsAPI, scraping"),
        ("pandas", "pandas", "all tabular work"),
        ("numpy", "numpy", "math"),
        ("dotenv", "python-dotenv", "reading .env"),
        ("bs4", "beautifulsoup4", "UFC/BKFC scraping"),
        ("lxml", "lxml", "HTML parsing"),
        ("nfl_data_py", "nfl_data_py", "NFL play-by-play, snaps, injuries"),
        ("pybaseball", "pybaseball", "MLB Statcast + FanGraphs"),
        ("nba_api", "nba_api", "NBA stats.nba.com"),
    ]
    ok = True
    for mod, pkg, why in checks:
        try:
            __import__(mod)
            print(f"  ok      {pkg:<18} {why}")
        except ImportError:
            ok = False
            print(f"  MISSING {pkg:<18} {why}")
    print()
    print(f"  {'ok     ' if os.environ.get('ODDS_API_KEY') else 'MISSING'} ODDS_API_KEY"
          f"       {'set' if os.environ.get('ODDS_API_KEY') else 'not set — /slate and /analyze will fail'}")
    return 0 if ok else 1


def _cmd_nfl_team(args) -> int:
    try:
        data = nfl_team_epa(args.season, weeks=args.weeks)
    except Exception as e:  # noqa: BLE001
        print(f"FETCH FAILED: {type(e).__name__}: {e}")
        return 1
    print(f"NFL {data['season']} — {data['n_plays']} plays  ({data['filters']})")
    print(f"{'team':<6}{'net EPA':>9}{'off EPA':>9}{'def EPA':>9}{'off SR':>8}{'ED pass%':>10}{'expl%':>8}")
    for team, row in list(data["teams"].items())[: args.top]:
        print(f"{team:<6}{row.get('net_epa', 0):>9.4f}{row.get('off_epa_play', 0):>9.4f}"
              f"{row.get('def_epa_play', 0):>9.4f}{row.get('off_success', 0):>8.3f}"
              f"{row.get('early_down_pass_rate', 0):>10.3f}{row.get('explosive_rate', 0):>8.3f}")
    print("\n[MODEL] output off [FACT] play-by-play. Opponent adjustment NOT applied — "
          "a soft schedule flatters these.")
    return 0


def _cmd_mlb_sched(args) -> int:
    try:
        games, meta = mlb_schedule(args.date)
    except Exception as e:  # noqa: BLE001
        print(f"FETCH FAILED: {type(e).__name__}: {e}")
        return 1
    print(f"[{meta.get('source')}, age {meta.get('age')}]")
    for g in games:
        print(f"  {g['away']} ({g['away_pitcher']}) @ {g['home']} ({g['home_pitcher']})  — {g['venue']}")
    if not games:
        print("  no games.")
    return 0


def _cmd_mlb_pitcher(args) -> int:
    try:
        d = mlb_pitcher_statcast(args.name, season=args.season)
    except Exception as e:  # noqa: BLE001
        print(f"FETCH FAILED: {type(e).__name__}: {e}")
        return 1
    print(f"{d['name']}  ({d['season']}, {d['pitches']} pitches)")
    for k in ("csw_pct", "whiff_pct", "hard_hit_pct_allowed", "barrel_pct_allowed"):
        v = d.get(k)
        print(f"  {k:<22} {'—' if v is None else f'{v:.3f}'}")
    print(f"  {'avg_velo':<22} {d.get('avg_velo') and round(d['avg_velo'], 1)}")
    print(f"\n{d['note']}")
    return 0


def _cmd_nba_team(args) -> int:
    try:
        d = nba_team_ratings(args.season)
    except Exception as e:  # noqa: BLE001
        print(f"FETCH FAILED: {type(e).__name__}: {e}")
        return 1
    teams = sorted(d["teams"], key=lambda t: t.get("NET_RATING", 0), reverse=True)
    print(f"NBA {d['season']}")
    print(f"{'team':<28}{'NET':>8}{'OFF':>8}{'DEF':>8}{'PACE':>8}")
    for t in teams[: args.top]:
        print(f"{t.get('TEAM_NAME', ''):<28}{t.get('NET_RATING', 0):>8.1f}"
              f"{t.get('OFF_RATING', 0):>8.1f}{t.get('DEF_RATING', 0):>8.1f}{t.get('PACE', 0):>8.1f}")
    print(f"\n{d['note']}")
    return 0


def _cmd_ufc(args) -> int:
    try:
        d, meta = ufc_fighter(args.name)
    except Exception as e:  # noqa: BLE001
        print(f"FETCH FAILED: {type(e).__name__}: {e}")
        return 1
    if not d["found"]:
        print(d["note"])
        return 1
    for m in d["matches"]:
        print(f"  {m['name']:<28} {m['nickname']:<18} {m['url'] or ''}")
    print(f"\n{d['note']}")
    return 0


def _cmd_mlb_parks(args) -> int:
    try:
        rows, meta = mlb_park_factors(season=args.season)
    except Exception as e:  # noqa: BLE001
        print(f"FETCH FAILED: {type(e).__name__}: {e}")
        return 1
    print(f"[{meta.get('source')}, age {meta.get('age')}]  {len(rows)} parks")
    for r in rows[:40]:
        name = r.get("name") or r.get("Venue") or "?"
        idx = r.get("index_wOBA") or r.get("park_factor") or "?"
        print(f"  {name:<34} {idx}")
    print("\n100 = neutral. Park factor is a season average — it does not know "
          "today's wind. Check the weather separately.")
    return 0


def _cmd_bkfc(args) -> int:
    print(BKFC_NOTE)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lib.fetch_stats", description="The Desk — stat pulls.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="which data packages and keys are available").set_defaults(func=_cmd_check)

    n = sub.add_parser("nfl-team", help="team EPA / success rate / tendencies")
    n.add_argument("--season", type=int, default=None)
    n.add_argument("--weeks", type=int, default=None, help="only the last N weeks")
    n.add_argument("--top", type=int, default=32)
    n.set_defaults(func=_cmd_nfl_team)

    ms = sub.add_parser("mlb-schedule", help="today's MLB slate with probables")
    ms.add_argument("--date", default=None)
    ms.set_defaults(func=_cmd_mlb_sched)

    mp = sub.add_parser("mlb-pitcher", help="Statcast profile for a pitcher")
    mp.add_argument("--name", required=True)
    mp.add_argument("--season", type=int, default=None)
    mp.set_defaults(func=_cmd_mlb_pitcher)

    nb = sub.add_parser("nba-team", help="team ratings and pace")
    nb.add_argument("--season", default=None, help='NBA format, e.g. "2025-26"')
    nb.add_argument("--top", type=int, default=30)
    nb.set_defaults(func=_cmd_nba_team)

    uf = sub.add_parser("ufc-fighter", help="look up a fighter on UFCStats")
    uf.add_argument("--name", required=True)
    uf.set_defaults(func=_cmd_ufc)

    pf = sub.add_parser("mlb-parks", help="Baseball Savant park factors")
    pf.add_argument("--season", type=int, default=None)
    pf.set_defaults(func=_cmd_mlb_parks)

    sub.add_parser("bkfc", help="what data actually exists for BKFC").set_defaults(func=_cmd_bkfc)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
