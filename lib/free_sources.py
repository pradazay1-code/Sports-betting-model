"""
Keyless data sources. No API key, no signup, no quota.

Every endpoint here is a public JSON feed that requires nothing but an HTTP
request. They are less complete than the paid feeds, but they are free forever
and they cover the things that matter most: who is playing, what the market
number is, and what the weather will do.

  - **ESPN scoreboard** — schedule, scores, AND betting lines (spread + total),
    for essentially every league. Includes **FCS via group 81**, which is the
    keyless answer to college football's hardest data problem.
  - **MLB StatsAPI** — full schedule, probable pitchers, live state.
  - **Open-Meteo** — forecast by lat/lon (see `lib.fetch_news` for the wind
    vector work).

ESPN's odds block carries a **consensus-style line, not a sharp price.** Treat
it as a median anchor and say so — anchoring a fair probability on it is weaker
than anchoring on Pinnacle, and your confidence should reflect that.

CLI:
    python3 -m lib.free_sources scoreboard --league cfb
    python3 -m lib.free_sources scoreboard --league cfb --fcs
    python3 -m lib.free_sources scoreboard --league nfl --date 20260910
    python3 -m lib.free_sources leagues
"""

from __future__ import annotations

import argparse
from typing import Any

from lib import cache

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

ESPN = "https://site.api.espn.com/apis/site/v2/sports"

#: league key -> ESPN path
LEAGUES: dict[str, str] = {
    "nfl": "football/nfl",
    "cfb": "football/college-football",
    "nba": "basketball/nba",
    "wnba": "basketball/wnba",
    "cbb": "basketball/mens-college-basketball",
    "wcbb": "basketball/womens-college-basketball",
    "mlb": "baseball/mlb",
    "nhl": "hockey/nhl",
    "mma": "mma/ufc",
    "soccer_epl": "soccer/eng.1",
    "soccer_mls": "soccer/usa.1",
}

#: ESPN "groups" filter for college football. 80 = FBS, 81 = FCS.
#: This is the keyless way to pull an FCS slate.
CFB_FBS_GROUP = 80
CFB_FCS_GROUP = 81


class FreeSourceError(RuntimeError):
    """A keyless fetch failed. Say so — never substitute a guess."""


def scoreboard(
    league: str,
    *,
    date: str | None = None,
    fcs: bool = False,
    ttl: float | None = None,
) -> tuple[dict, dict]:
    """
    ESPN scoreboard: schedule, scores, and betting lines. No key required.

    `date` is YYYYMMDD. `fcs=True` switches college football to group 81.
    """
    if requests is None:
        raise FreeSourceError("`requests` isn't installed. pip install -r requirements.txt")
    path = LEAGUES.get(league.lower())
    if not path:
        raise FreeSourceError(f"unknown league {league!r}. Known: {', '.join(sorted(LEAGUES))}")

    params: dict[str, Any] = {}
    if date:
        params["dates"] = date
    if league.lower() == "cfb":
        params["groups"] = CFB_FCS_GROUP if fcs else CFB_FBS_GROUP
        params["limit"] = 300

    def fetch():
        r = requests.get(f"{ESPN}/{path}/scoreboard", params=params, timeout=25)
        if not r.ok:
            raise FreeSourceError(f"{r.status_code} from ESPN {path}: {r.text[:200]}")
        return r.json()

    ck = f"espn:{league}:{date or 'today'}:{'fcs' if fcs else 'fbs'}"
    return cache.get_or_fetch("odds", ck, fetch, ttl=ttl or 600)


def parse_scoreboard(data: dict) -> list[dict]:
    """
    Flatten ESPN's scoreboard into rows a human can read and a board file can use.

    Pulls the odds block where ESPN has one. `spread` is ESPN's `details` string
    (e.g. "BUF -2.5") and `total` is the over/under.
    """
    rows = []
    for ev in data.get("events", []):
        comps = ev.get("competitions") or [{}]
        comp = comps[0]
        teams = {}
        for c in comp.get("competitors", []):
            side = c.get("homeAway", "?")
            t = c.get("team") or {}
            teams[side] = {
                "name": t.get("displayName"),
                "abbr": t.get("abbreviation"),
                "score": c.get("score"),
                "record": next((r.get("summary") for r in (c.get("records") or [])), None),
                "rank": c.get("curatedRank", {}).get("current"),
            }
        odds = (comp.get("odds") or [{}])[0]
        status = (ev.get("status") or {}).get("type", {})
        rows.append({
            "id": ev.get("id"),
            "name": ev.get("shortName"),
            "start": ev.get("date"),
            "state": status.get("state"),
            "detail": status.get("shortDetail"),
            "home": teams.get("home", {}),
            "away": teams.get("away", {}),
            "spread": odds.get("details"),
            "total": odds.get("overUnder"),
            "odds_provider": (odds.get("provider") or {}).get("name"),
            "venue": ((comp.get("venue") or {}).get("fullName")),
            "neutral": comp.get("neutralSite", False),
            "broadcast": next((b.get("names", [None])[0] for b in (comp.get("broadcasts") or [])), None),
        })
    return rows


def to_board_stub(rows: list[dict], event_name: str) -> dict:
    """
    Turn a scoreboard row into a `lib.manual` board skeleton.

    ESPN gives one consensus line. You fill in the per-book prices from
    research — that's what makes the board devig-able and shoppable.
    """
    row = next((r for r in rows if event_name.lower() in (r.get("name") or "").lower()), None)
    if row is None:
        raise FreeSourceError(f"no scoreboard row matching {event_name!r}")
    return {
        "event": f"{row['away'].get('name')} @ {row['home'].get('name')}",
        "sport": "manual",
        "commence": row.get("start"),
        "note": (
            f"ESPN consensus: spread {row.get('spread')}, total {row.get('total')} "
            f"({row.get('odds_provider')}). CONSENSUS IS NOT A SHARP PRICE — add "
            f"per-book prices from research before trusting a devig."
        ),
        "markets": [
            {
                "name": "moneyline",
                "books": {
                    "REPLACE_WITH_BOOK": {
                        row["away"].get("name", "away"): 0,
                        row["home"].get("name", "home"): 0,
                    }
                },
            }
        ],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_scoreboard(args) -> int:
    try:
        data, meta = scoreboard(args.league, date=args.date, fcs=args.fcs)
    except Exception as e:  # noqa: BLE001
        print(f"FETCH FAILED: {type(e).__name__}: {e}")
        return 1
    rows = parse_scoreboard(data)
    div = " (FCS)" if args.fcs else ""
    print(f"[{meta.get('source')}, age {meta.get('age')}]  {len(rows)} {args.league.upper()}{div} games")
    if meta.get("degraded"):
        print(f"!! {meta['warning']}")
    for r in rows[: args.limit]:
        line = f"  {r['name']:<26} {r.get('detail') or '':<18}"
        if r.get("spread"):
            line += f" {r['spread']:<12}"
        if r.get("total"):
            line += f" O/U {r['total']}"
        print(line)
        if args.verbose and r.get("venue"):
            print(f"      {r['venue']}{' (neutral)' if r['neutral'] else ''}"
                  f"{'  ' + r['broadcast'] if r.get('broadcast') else ''}")
    print("\nESPN lines are CONSENSUS, not sharp. Use them to find the slate, then")
    print("gather per-book prices and run `python3 -m lib.manual board`.")
    return 0


def _cmd_leagues(args) -> int:
    for k, v in sorted(LEAGUES.items()):
        print(f"  {k:<12} {v}")
    print(f"\n  college football: --fcs switches to group {CFB_FCS_GROUP} (FCS); "
          f"default is {CFB_FBS_GROUP} (FBS)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lib.free_sources",
                                description="The Desk — keyless public data feeds.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sb = sub.add_parser("scoreboard", help="ESPN scoreboard with consensus lines")
    sb.add_argument("--league", required=True, choices=sorted(LEAGUES))
    sb.add_argument("--date", default=None, help="YYYYMMDD")
    sb.add_argument("--fcs", action="store_true", help="college football: FCS instead of FBS")
    sb.add_argument("--limit", type=int, default=40)
    sb.add_argument("--verbose", action="store_true")
    sb.set_defaults(func=_cmd_scoreboard)

    sub.add_parser("leagues", help="supported leagues").set_defaults(func=_cmd_leagues)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
