"""
The Odds API client, plus the line-shopping and edge-finding built on top of it.

Everything is cached through `lib.cache` because the free tier is 500 requests a
month. Quota remaining is read off the response headers and surfaced on every
call — if you're about to burn a third of the month's budget on a props sweep,
you should know before you do it.

The core idea, and the reason this module exists rather than a thin API wrapper:
we devig the *sharp* book to get a fair probability, then shop that fair number
against every *soft* book's price. Anchoring and shopping are two different jobs
and must never use the same price.

CLI:
    python3 -m lib.fetch_odds sports
    python3 -m lib.fetch_odds board --sport nfl
    python3 -m lib.fetch_odds edges --sport nfl --min-ev 0.02
    python3 -m lib.fetch_odds quota
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from lib import cache
from lib.odds import (
    MIN_EV,
    SHARP_BOOK_PRIORITY,
    SOFT_BOOKS,
    american_to_decimal,
    default_method,
    devig,
    devig_spread,
    implied_prob,
    price_edge,
    prob_to_american,
)

try:  # optional; the module works without it if the env is already exported
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

BASE_URL = "https://api.the-odds-api.com/v4"

#: Friendly name -> The Odds API sport key.
SPORT_KEYS = {
    "nfl": "americanfootball_nfl",
    "ncaaf": "americanfootball_ncaaf",
    "cfb": "americanfootball_ncaaf",
    "nba": "basketball_nba",
    "ncaab": "basketball_ncaab",
    "cbb": "basketball_ncaab",
    "wnba": "basketball_wnba",
    "mlb": "baseball_mlb",
    "nhl": "icehockey_nhl",
    "ufc": "mma_mixed_martial_arts",
    "mma": "mma_mixed_martial_arts",
    "bkfc": "mma_mixed_martial_arts",  # rarely listed; see skills/sport-bkfc.md
    "boxing": "boxing_boxing",
    "epl": "soccer_epl",
    "mls": "soccer_usa_mls",
    "ucl": "soccer_uefa_champs_league",
    "tennis": "tennis_atp_aus_open_singles",
}

#: Markets we can pull off the main odds endpoint.
CORE_MARKETS = ("h2h", "spreads", "totals")

#: Player-prop market keys, per sport. These need the per-event endpoint and
#: each costs quota, so we don't sweep them by default.
PROP_MARKETS = {
    "americanfootball_nfl": [
        "player_pass_yds", "player_pass_tds", "player_rush_yds",
        "player_reception_yds", "player_receptions", "player_anytime_td",
    ],
    "basketball_nba": [
        "player_points", "player_rebounds", "player_assists",
        "player_threes", "player_points_rebounds_assists",
    ],
    "baseball_mlb": [
        "batter_hits", "batter_home_runs", "batter_total_bases",
        "pitcher_strikeouts", "batter_rbis",
    ],
    "icehockey_nhl": ["player_points", "player_shots_on_goal", "player_goals"],
    "mma_mixed_martial_arts": [],
}


class OddsAPIError(RuntimeError):
    """A fetch failed. We raise instead of returning a plausible-looking board."""


@dataclass
class Quota:
    remaining: int | None = None
    used: int | None = None
    last_cost: int | None = None

    def __str__(self) -> str:
        if self.remaining is None:
            return "quota unknown"
        return f"{self.remaining} requests remaining ({self.used} used this period)"


QUOTA = Quota()
_QUOTA_FILE = cache.CACHE_DIR / "quota.json"


def _save_quota() -> None:
    try:
        _QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
        _QUOTA_FILE.write_text(
            json.dumps(
                {
                    "remaining": QUOTA.remaining,
                    "used": QUOTA.used,
                    "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
            )
        )
    except OSError:
        pass


def load_quota() -> dict | None:
    if _QUOTA_FILE.exists():
        try:
            return json.loads(_QUOTA_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return None
    return None


def api_key() -> str:
    key = os.environ.get("ODDS_API_KEY", "").strip()
    if not key:
        raise OddsAPIError(
            "ODDS_API_KEY is not set. Copy .env.example to .env and add your key from "
            "https://the-odds-api.com/ . I can't pull a board without it, and I'm not "
            "going to invent one."
        )
    return key


def _request(path: str, params: dict[str, Any]) -> Any:
    """Raw GET. Never called directly — always through the cache."""
    if requests is None:
        raise OddsAPIError("`requests` isn't installed. pip install -r requirements.txt")
    url = f"{BASE_URL}{path}"
    p = dict(params)
    p["apiKey"] = api_key()
    resp = requests.get(url, params=p, timeout=25)

    # Quota lives in the headers, not the body.
    QUOTA.remaining = _int_or_none(resp.headers.get("x-requests-remaining"))
    QUOTA.used = _int_or_none(resp.headers.get("x-requests-used"))
    QUOTA.last_cost = _int_or_none(resp.headers.get("x-requests-last"))
    _save_quota()

    if resp.status_code == 401:
        raise OddsAPIError("401 from The Odds API — the key in .env is wrong or expired.")
    if resp.status_code == 422:
        raise OddsAPIError(f"422 from The Odds API — bad parameters: {resp.text[:300]}")
    if resp.status_code == 429:
        raise OddsAPIError(f"429 — out of quota. {QUOTA}")
    if not resp.ok:
        raise OddsAPIError(f"{resp.status_code} from The Odds API: {resp.text[:300]}")
    return resp.json()


def _int_or_none(v: str | None) -> int | None:
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def resolve_sport(sport: str) -> str:
    """'nfl' -> 'americanfootball_nfl'. Passes through full keys unchanged."""
    s = sport.lower().strip()
    return SPORT_KEYS.get(s, s)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def get_sports(*, ttl: float | None = None) -> tuple[list[dict], dict]:
    """In-season sports. This endpoint is free — it doesn't cost quota."""
    return cache.get_or_fetch(
        "static", "sports", lambda: _request("/sports", {}), ttl=ttl or 3600
    )


def get_odds(
    sport: str,
    *,
    markets: Iterable[str] = CORE_MARKETS,
    regions: str = "us,us2,eu",
    ttl: float | None = None,
) -> tuple[list[dict], dict]:
    """
    Full board for a sport.

    `regions` includes `eu` on purpose — that's where Pinnacle lives, and
    Pinnacle is the anchor. A US-only pull leaves you devigging DraftKings
    against FanDuel, which is devigging noise against noise.
    """
    key = resolve_sport(sport)
    mkts = ",".join(markets)
    ck = f"odds:{key}:{mkts}:{regions}"
    return cache.get_or_fetch(
        "odds",
        ck,
        lambda: _request(
            f"/sports/{key}/odds",
            {"regions": regions, "markets": mkts, "oddsFormat": "american", "dateFormat": "iso"},
        ),
        ttl=ttl,
    )


def get_events(sport: str, *, ttl: float | None = None) -> tuple[list[dict], dict]:
    """Event list with ids — needed before pulling per-event props. Free."""
    key = resolve_sport(sport)
    return cache.get_or_fetch(
        "odds", f"events:{key}", lambda: _request(f"/sports/{key}/events", {}), ttl=ttl or 600
    )


def get_event_odds(
    sport: str,
    event_id: str,
    *,
    markets: Iterable[str] | None = None,
    regions: str = "us,us2,eu",
    ttl: float | None = None,
) -> tuple[dict, dict]:
    """
    Props for a single event. Costs quota per market group — this is the
    expensive endpoint, so it's never swept across a whole slate automatically.
    """
    key = resolve_sport(sport)
    mkts = ",".join(markets or PROP_MARKETS.get(key, []) or ["h2h"])
    ck = f"eventodds:{key}:{event_id}:{mkts}:{regions}"
    return cache.get_or_fetch(
        "odds",
        ck,
        lambda: _request(
            f"/sports/{key}/events/{event_id}/odds",
            {"regions": regions, "markets": mkts, "oddsFormat": "american", "dateFormat": "iso"},
        ),
        ttl=ttl,
    )


def get_scores(sport: str, *, days_from: int = 1, ttl: float | None = None) -> tuple[list[dict], dict]:
    """Scores for grading. `days_from` > 0 costs quota."""
    key = resolve_sport(sport)
    return cache.get_or_fetch(
        "odds",
        f"scores:{key}:{days_from}",
        lambda: _request(f"/sports/{key}/scores", {"daysFrom": days_from, "dateFormat": "iso"}),
        ttl=ttl or 300,
    )


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


@dataclass
class Outcome:
    """One priced side of one market at one book."""

    name: str
    price: float
    point: float | None = None
    book: str = ""


@dataclass
class MarketView:
    """Every book's price on one market for one event, keyed by outcome."""

    key: str                      # h2h / spreads / totals / player_pass_yds
    event: str
    sport: str
    commence: str
    # outcome name -> list of (book, price, point)
    quotes: dict[str, list[Outcome]] = field(default_factory=dict)

    def books(self) -> set[str]:
        return {o.book for outs in self.quotes.values() for o in outs}

    def sharp_book(self) -> str | None:
        """The sharpest book that has priced *both* sides. Both matters — you
        can't devig a market off one leg."""
        available = self.books()
        for want in SHARP_BOOK_PRIORITY:
            if want in available and self._complete_at(want):
                return want
        return None

    def _complete_at(self, book: str) -> bool:
        return all(any(o.book == book for o in outs) for outs in self.quotes.values())

    def at_book(self, book: str) -> dict[str, Outcome]:
        out = {}
        for name, outs in self.quotes.items():
            for o in outs:
                if o.book == book:
                    out[name] = o
        return out

    def best_price(self, outcome: str) -> Outcome | None:
        """Line shopping: the longest price available on an outcome."""
        outs = self.quotes.get(outcome, [])
        if not outs:
            return None
        return max(outs, key=lambda o: american_to_decimal(o.price))

    def median_price(self, outcome: str) -> float | None:
        outs = self.quotes.get(outcome, [])
        if not outs:
            return None
        return statistics.median(o.price for o in outs)


def normalize(board: list[dict], sport: str) -> list[MarketView]:
    """Flatten The Odds API's nested payload into one MarketView per market."""
    views: list[MarketView] = []
    for game in board:
        event = f"{game.get('away_team')} @ {game.get('home_team')}"
        by_market: dict[tuple[str, float | None], MarketView] = {}
        for bm in game.get("bookmakers", []):
            book = bm.get("key", "")
            for mkt in bm.get("markets", []):
                mkey = mkt.get("key", "")
                for oc in mkt.get("outcomes", []):
                    point = oc.get("point")
                    # A market is only comparable at one number, so the line is
                    # part of its identity. For spreads the two sides carry
                    # opposite points (+2.5 / -2.5) but are the SAME market, so
                    # we key on the absolute value — keying on the signed point
                    # splits every spread into two one-sided markets that can
                    # never be devigged. Alternate numbers (2.5 vs 3) stay
                    # separate, which is correct: you can't devig -2.5 against
                    # -3, and pretending otherwise is how you buy a key number
                    # by accident.
                    if mkey == "spreads":
                        ident = (mkey, abs(point) if point is not None else None)
                    elif mkey == "totals":
                        ident = (mkey, point)
                    else:
                        ident = (mkey, None)

                    if ident not in by_market:
                        # :g so 3.0 renders as "spreads 3", not "spreads 3.0".
                        label = mkey if ident[1] is None else f"{mkey} {ident[1]:g}"
                        by_market[ident] = MarketView(
                            key=label,
                            event=event,
                            sport=sport,
                            commence=game.get("commence_time", ""),
                        )
                    mv = by_market[ident]
                    # Carry the number in the outcome name so a side is never
                    # ambiguous once it's out of context.
                    name = oc.get("name", "")
                    if point is not None and mkey in ("spreads", "totals"):
                        name = f"{name} {point:+g}" if mkey == "spreads" else f"{name} {point:g}"
                    mv.quotes.setdefault(name, []).append(
                        Outcome(name=name, price=float(oc["price"]), point=point, book=book)
                    )
        views.extend(by_market.values())
    return views


# ---------------------------------------------------------------------------
# The actual job: fair price from sharp, shop it against soft
# ---------------------------------------------------------------------------


def fair_probabilities(mv: MarketView) -> dict | None:
    """
    Devig this market off the sharpest complete book.

    Returns None when no book has priced every outcome — you cannot devig half a
    market, and estimating the missing side is exactly the fabrication we refuse
    to do. Falls back to the market median only when no sharp book is present,
    and says so in `anchor_tier` so the caller can drop confidence.
    """
    outcomes = list(mv.quotes.keys())
    if len(outcomes) < 2:
        return None

    sharp = mv.sharp_book()
    if sharp:
        prices = [mv.at_book(sharp)[n].price for n in outcomes]
        anchor, tier = sharp, "sharp"
    else:
        med = [mv.median_price(n) for n in outcomes]
        if any(m is None for m in med):
            return None
        prices = [float(m) for m in med]  # type: ignore[arg-type]
        anchor, tier = "market_median", "median"

    method = default_method(len(prices))
    fair = devig(prices, method)
    spread = devig_spread(prices)
    return {
        "outcomes": outcomes,
        "anchor": anchor,
        "anchor_tier": tier,
        "anchor_prices": prices,
        "method": method,
        "fair": dict(zip(outcomes, fair)),
        "fair_american": {n: prob_to_american(p) for n, p in zip(outcomes, fair)},
        "spread": spread,
        "n_books": len(mv.books()),
    }


def find_edges(
    views: Iterable[MarketView],
    *,
    min_ev: float = MIN_EV,
    soft_only: bool = True,
    bankroll_units: float = 100.0,
) -> list[dict]:
    """
    Every priced edge on the board, sorted by EV.

    `soft_only` keeps us from "finding" an edge by comparing Pinnacle to itself.
    An edge against the book you anchored on is an arithmetic artifact, not a
    bet, so the anchor book is always excluded regardless.
    """
    found: list[dict] = []
    for mv in views:
        fp = fair_probabilities(mv)
        if fp is None:
            continue
        for name, prob in fp["fair"].items():
            for o in mv.quotes.get(name, []):
                if o.book == fp["anchor"]:
                    continue
                if soft_only and o.book not in SOFT_BOOKS:
                    continue
                edge = price_edge(
                    prob, o.price, method=fp["method"], bankroll_units=bankroll_units, min_ev=min_ev
                )
                if edge.ev < min_ev:
                    continue
                found.append(
                    {
                        "event": mv.event,
                        "sport": mv.sport,
                        "commence": mv.commence,
                        "market": mv.key,
                        "side": name,
                        "book": o.book,
                        "offered": o.price,
                        "fair_american": edge.fair_american,
                        "fair_prob": prob,
                        "ev": edge.ev,
                        "stake_units": edge.stake_units,
                        "anchor": fp["anchor"],
                        "anchor_tier": fp["anchor_tier"],
                        "method": fp["method"],
                        "devig_disagreement": fp["spread"]["widest_spread"],
                        "devig_meaningful": fp["spread"]["meaningful"],
                        "n_books": fp["n_books"],
                        "note": edge.note,
                    }
                )
    found.sort(key=lambda e: e["ev"], reverse=True)
    return found


def confidence_for(edge: dict) -> tuple[str, str]:
    """
    Translate the mechanical facts about an edge into a confidence level.

    Deliberately conservative. A big EV number off a median anchor with three
    books quoting is not a high-confidence bet — it's most likely a stale line
    or a market the sharp books haven't bothered to price, and both of those
    resolve against you.
    """
    reasons = []
    level = "medium"
    if edge["anchor_tier"] != "sharp":
        level = "low"
        reasons.append("no sharp book priced this market — anchored on the median")
    if edge["devig_meaningful"]:
        level = "low"
        reasons.append(
            f"devig methods disagree by {edge['devig_disagreement'] * 100:.1f} pts of probability"
        )
    if edge["n_books"] < 4:
        level = "low"
        reasons.append(f"only {edge['n_books']} books quoting — thin market")
    if edge["ev"] > 0.10:
        level = "low"
        reasons.append(
            f"EV of {edge['ev']:.1%} is implausibly large; assume a stale line or a "
            "mis-mapped outcome before assuming free money"
        )
    if level == "medium" and edge["anchor_tier"] == "sharp" and edge["n_books"] >= 6 and edge["ev"] >= 0.03:
        level = "high"
        reasons.append("sharp anchor, deep market, methods agree")
    if not reasons:
        reasons.append("sharp anchor, methods agree")
    return level, "; ".join(reasons)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _meta_line(meta: dict) -> str:
    if meta.get("degraded"):
        return f"  !! {meta['warning']}"
    return f"  [{meta['source']}, age {meta['age']}]"


def _cmd_sports(args) -> int:
    data, meta = get_sports()
    print(_meta_line(meta))
    active = [s for s in data if s.get("active")]
    for s in sorted(active, key=lambda x: x["key"]):
        print(f"  {s['key']:<40} {s.get('title', '')}")
    print(f"\n{len(active)} active. {QUOTA}")
    return 0


def _cmd_board(args) -> int:
    try:
        board, meta = get_odds(args.sport, markets=args.markets.split(","))
    except OddsAPIError as e:
        print(f"FETCH FAILED: {e}")
        return 1
    print(_meta_line(meta))
    views = normalize(board, resolve_sport(args.sport))
    if not views:
        print("no games on the board for this sport right now.")
        return 0

    by_event: dict[str, list[MarketView]] = {}
    for mv in views:
        by_event.setdefault(mv.event, []).append(mv)

    for event, mvs in by_event.items():
        print(f"\n{event}   ({mvs[0].commence})")
        for mv in sorted(mvs, key=lambda m: m.key):
            fp = fair_probabilities(mv)
            if fp is None:
                print(f"  {mv.key:<18} incomplete market — not devigged")
                continue
            tag = fp["anchor"] if fp["anchor_tier"] == "sharp" else f"{fp['anchor']} (NO SHARP BOOK)"
            print(f"  {mv.key:<18} anchor {tag}, {fp['n_books']} books, {fp['method']}")
            for name in fp["outcomes"]:
                best = mv.best_price(name)
                fair_am = fp["fair_american"][name]
                bstr = f"{best.price:+.0f} @ {best.book}" if best else "—"
                print(f"      {name:<26} fair {fair_am:+7.1f}   best {bstr}")
    print(f"\n{QUOTA}")
    return 0


def _cmd_edges(args) -> int:
    try:
        board, meta = get_odds(args.sport, markets=args.markets.split(","))
    except OddsAPIError as e:
        print(f"FETCH FAILED: {e}")
        return 1
    print(_meta_line(meta))
    views = normalize(board, resolve_sport(args.sport))
    edges = find_edges(views, min_ev=args.min_ev, soft_only=not args.all_books)

    if not edges:
        print(f"\nNo plays. Nothing on this board clears {args.min_ev:.1%} EV after devig.")
        print("That is a complete answer — don't go manufacturing one.")
        print(f"\n{QUOTA}")
        return 0

    print(f"\n{len(edges)} priced edge(s) over {args.min_ev:.1%} EV. Top {args.top}:\n")
    for e in edges[: args.top]:
        level, why = confidence_for(e)
        print(f"{e['event']}  —  {e['market']}")
        print(f"  side      : {e['side']}")
        print(f"  fair      : {e['fair_american']:+.1f}  (p={e['fair_prob']:.4f}, {e['method']} off {e['anchor']})")
        print(f"  offered   : {e['offered']:+.0f} @ {e['book']}")
        print(f"  EV        : {e['ev']:+.2%}")
        print(f"  stake     : {e['stake_units']}u")
        print(f"  confidence: {level} — {why}")
        if e["note"]:
            print(f"  note      : {e['note']}")
        print()
    print(
        "Injuries, lineups, and weather are NOT in these numbers. Check the real-time\n"
        "layer before betting any of them, and re-run if anything material moved."
    )
    print(f"\n{QUOTA}")
    return 0


def _cmd_quota(args) -> int:
    q = load_quota()
    if not q:
        print("no quota recorded yet — make a request first.")
        return 0
    print(f"remaining : {q['remaining']}")
    print(f"used      : {q['used']}")
    print(f"checked   : {q['checked_at']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lib.fetch_odds", description="The Desk — odds feed.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sports", help="list in-season sports").set_defaults(func=_cmd_sports)

    b = sub.add_parser("board", help="full board with fair prices")
    b.add_argument("--sport", required=True)
    b.add_argument("--markets", default="h2h,spreads,totals")
    b.set_defaults(func=_cmd_board)

    e = sub.add_parser("edges", help="priced edges, sorted by EV")
    e.add_argument("--sport", required=True)
    e.add_argument("--markets", default="h2h,spreads,totals")
    e.add_argument("--min-ev", dest="min_ev", type=float, default=MIN_EV)
    e.add_argument("--top", type=int, default=5)
    e.add_argument("--all-books", action="store_true", help="include non-soft books as bettable")
    e.set_defaults(func=_cmd_edges)

    sub.add_parser("quota", help="API requests remaining").set_defaults(func=_cmd_quota)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
