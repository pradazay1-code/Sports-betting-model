"""
Price anything, from anywhere, with no API key.

This is the keyless path and it is the one that always works. The agent gathers
prices however it can — WebSearch, a screenshot the user pasted, reading them
off a book's page, a friend texting a number — and pipes them through here to
get the same devig / anchor / EV / Kelly treatment that the API path gets.

Nothing in this module touches the network. It cannot fail because a key is
missing or an endpoint is down, which is precisely the point: the math is the
part that must never be unavailable.

Two input shapes:

  1. **Inline**, for one market:
       python3 -m lib.manual devig --labels "Rams,49ers" --prices -198 +164
       python3 -m lib.manual edge --fair -182 --offered -190

  2. **A board file**, for a slate the agent assembled from research:
       python3 -m lib.manual board slate.json
       python3 -m lib.manual template > slate.json    # writes a starter file

The board file reuses the exact same edge-finding code as the live odds feed —
sharp-book anchoring, power/multiplicative devig, soft-book shopping, confidence
tiering. A manually-entered board is a first-class board.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lib.fetch_odds import MarketView, Outcome, rank_plays, summarize_board
from lib.odds import (
    MIN_EV,
    SOFT_BOOKS,
    default_method,
    devig,
    devig_spread,
    implied_prob,
    price_edge,
    prob_to_american,
    sharp_anchor,
)

TEMPLATE = {
    "event": "Los Angeles Rams @ San Francisco 49ers",
    "sport": "americanfootball_nfl",
    "commence": "2026-09-10T00:35:00Z",
    "note": "Prices gathered by web research. Record WHERE and WHEN you read each one.",
    "markets": [
        {
            "name": "moneyline",
            "books": {
                "pinnacle": {"Rams": -182, "49ers": 155},
                "draftkings": {"Rams": -198, "49ers": 164},
                "fanduel": {"Rams": -190, "49ers": 160},
            },
        },
        {
            "name": "total 48.5",
            "books": {
                "pinnacle": {"Over 48.5": -105, "Under 48.5": -105},
                "draftkings": {"Over 48.5": -110, "Under 48.5": -110},
            },
        },
    ],
}


class BoardError(ValueError):
    """The board file is malformed. Say what's wrong rather than guessing."""


def _normalize_book(name: str) -> str:
    return name.lower().replace(" ", "").replace("_", "")


def load_board(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        raise BoardError(f"no such board file: {p}")
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        raise BoardError(f"{p} is not valid JSON: {e}") from e
    if "markets" not in data:
        raise BoardError(f"{p} has no 'markets' key. Run `python3 -m lib.manual template`.")
    return data


def board_to_views(board: dict) -> list[MarketView]:
    """
    Convert a hand-built board into the same MarketView objects the live feed
    produces, so every downstream analysis path works unchanged.
    """
    event = board.get("event", "unknown event")
    sport = board.get("sport", "manual")
    commence = board.get("commence", "")
    views: list[MarketView] = []

    for i, mkt in enumerate(board.get("markets", [])):
        name = mkt.get("name") or f"market {i}"
        books = mkt.get("books") or {}
        if not books:
            raise BoardError(f"market {name!r} has no books")

        mv = MarketView(key=name, event=event, sport=sport, commence=commence)
        for book, prices in books.items():
            if not isinstance(prices, dict):
                raise BoardError(f"market {name!r}, book {book!r}: expected a mapping of outcome -> price")
            for outcome, price in prices.items():
                try:
                    px = float(price)
                except (TypeError, ValueError) as e:
                    raise BoardError(
                        f"market {name!r}, book {book!r}, outcome {outcome!r}: "
                        f"{price!r} is not a number"
                    ) from e
                mv.quotes.setdefault(outcome, []).append(
                    Outcome(name=outcome, price=px, point=None, book=_normalize_book(book))
                )
        views.append(mv)
    return views


def audit_board(views: list[MarketView]) -> list[dict]:
    """
    What can this board actually support? Reported before any recommendation.

    The two failure modes a manual board invites are an incomplete market (you
    wrote down one side and not the other, so it cannot be devigged) and a
    soft-book-only market (nothing to anchor on). Both are silent unless you
    look for them.
    """
    out = []
    for mv in views:
        books = mv.books()
        sharp = mv.sharp_book()
        incomplete = [n for n, outs in mv.quotes.items() if not outs]
        one_sided = len(mv.quotes) < 2
        out.append({
            "market": mv.key,
            "n_books": len(books),
            "books": sorted(books),
            "sharp_anchor": sharp,
            "has_sharp": sharp is not None,
            "one_sided": one_sided,
            "incomplete_outcomes": incomplete,
            "devig_possible": not one_sided and any(mv._complete_at(b) for b in books),
            "soft_books_available": sorted(b for b in books if b in SOFT_BOOKS),
        })
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_template(args) -> int:
    print(json.dumps(TEMPLATE, indent=2))
    return 0


def _cmd_devig(args) -> int:
    labels = [s.strip() for s in args.labels.split(",")] if args.labels else None
    prices = args.prices
    if labels and len(labels) != len(prices):
        print(f"got {len(labels)} labels and {len(prices)} prices — they must match")
        return 2
    labels = labels or [f"outcome {i}" for i in range(len(prices))]

    method = args.method or default_method(len(prices))
    fair = devig(prices, method)
    spread = devig_spread(prices)

    print(f"method   : {method}   ({len(prices)}-way)")
    print(f"{'outcome':<24}{'posted':>9}{'raw':>9}{'fair':>9}{'fair line':>12}")
    for lab, px, fp in zip(labels, prices, fair):
        print(f"{lab:<24}{px:>+9.0f}{implied_prob(px):>9.4f}{fp:>9.4f}"
              f"{prob_to_american(fp):>+12.1f}")
    w = spread["widest_spread"]
    if spread["meaningful"]:
        print(f"\n  methods disagree by {w * 100:.2f} pts — quote a RANGE, not a point estimate")
    else:
        print(f"\n  methods agree within {w * 100:.2f} pts")
    return 0


def _cmd_edge(args) -> int:
    fair_prob = implied_prob(args.fair) if args.fair is not None else args.prob
    if fair_prob is None:
        print("give --fair (a devigged American price) or --prob")
        return 2
    e = price_edge(fair_prob, args.offered, bankroll_units=args.bankroll)
    print(f"fair      : {e.fair_american:+.1f}  (p={e.fair_prob:.4f})")
    print(f"offered   : {e.offered_american:+.0f}")
    print(f"EV        : {e.ev:+.2%}")
    print(f"stake     : {e.stake_units}u   (1/4 Kelly, 2u ceiling)")
    print(f"verdict   : {'BET' if e.is_bet else 'NO BET'}")
    if e.note:
        print(f"note      : {e.note}")
    return 0


def _cmd_shop(args) -> int:
    """Line shopping across whatever prices you found."""
    entries = []
    for chunk in args.prices.split(","):
        if ":" not in chunk:
            print(f"bad entry {chunk!r} — use book:price, e.g. pinnacle:-182")
            return 2
        book, px = chunk.rsplit(":", 1)
        entries.append((_normalize_book(book), float(px)))

    anchor = sharp_anchor({b: p for b, p in entries})
    best = max(entries, key=lambda bp: bp[1] if bp[1] > 0 else 1 / abs(bp[1]))

    print(f"{'book':<18}{'price':>9}{'implied':>10}")
    for b, p in sorted(entries, key=lambda x: -(x[1] if x[1] > 0 else 1 / abs(x[1]))):
        tag = ""
        if b == anchor["anchor"]:
            tag = "  <- anchor"
        elif b in SOFT_BOOKS:
            tag = "  (soft)"
        print(f"{b:<18}{p:>+9.0f}{implied_prob(p):>10.4f}{tag}")
    print(f"\nbest available : {best[0]} at {best[1]:+.0f}")
    print(f"anchor         : {anchor['note']}")
    if anchor["tier"] != "sharp":
        print("  No sharp book here. Lower your confidence — you are anchoring on noise.")
    return 0


def _cmd_board(args) -> int:
    try:
        board = load_board(args.path)
        views = board_to_views(board)
    except BoardError as e:
        print(f"BOARD ERROR: {e}")
        return 1

    print(f"{board.get('event', '?')}   [{len(views)} market(s), hand-entered]")
    if board.get("note"):
        print(f"  {board['note']}")

    print("\n--- what this board can support ---")
    for a in audit_board(views):
        flags = []
        if a["one_sided"]:
            flags.append("ONE-SIDED — cannot devig")
        if not a["has_sharp"]:
            flags.append("no sharp anchor")
        if not a["soft_books_available"]:
            flags.append("no soft book to bet into")
        status = "; ".join(flags) if flags else "ok"
        print(f"  {a['market']:<22} {a['n_books']} books, anchor={a['sharp_anchor'] or 'none'}  [{status}]")

    plays = rank_plays(views, min_ev=args.min_ev)
    print("\n--- edges ---")
    print(summarize_board(plays, min_ev=args.min_ev))
    for i, p in enumerate(plays[: args.top], 1):
        print(f"\n{i}. {p['market']} — {p['side']}")
        print(f"   WINS       : {p['win_prob']:.1%}")
        print(f"   EDGE       : {p['ev']:+.2%} EV  "
              f"(fair {p['fair_american']:+.1f}, offered {p['offered']:+.0f} @ {p['book']})")
        print(f"   stake      : {p['stake_units']}u")
        print(f"   confidence : {p['confidence']} — {p['confidence_reason']}")
    if plays:
        print("\nThese numbers predate the news layer. Check availability and weather "
              "before betting any of them.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lib.manual",
        description="The Desk — price anything from anywhere, no API key required.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("devig", help="devig a market you read off a page")
    d.add_argument("--prices", nargs="+", type=float, required=True)
    d.add_argument("--labels", default=None, help="comma-separated outcome names")
    d.add_argument("--method", default=None)
    d.set_defaults(func=_cmd_devig)

    e = sub.add_parser("edge", help="EV and stake for a fair price vs an offer")
    e.add_argument("--fair", type=float, default=None)
    e.add_argument("--prob", type=float, default=None)
    e.add_argument("--offered", type=float, required=True)
    e.add_argument("--bankroll", type=float, default=100.0)
    e.set_defaults(func=_cmd_edge)

    s = sub.add_parser("shop", help="compare prices across books")
    s.add_argument("--prices", required=True, help="book:price,book:price,...")
    s.set_defaults(func=_cmd_shop)

    b = sub.add_parser("board", help="full analysis of a hand-built board file")
    b.add_argument("path")
    b.add_argument("--min-ev", dest="min_ev", type=float, default=MIN_EV)
    b.add_argument("--top", type=int, default=5)
    b.set_defaults(func=_cmd_board)

    sub.add_parser("template", help="print a starter board file").set_defaults(func=_cmd_template)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
