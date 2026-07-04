"""Value engine: model prob vs de-vigged market prob -> EV ranking (spec §5).

For every prop with a model probability and a market line:
de-vig the two-way market, compute EV at the best available price
(line shopping), assign a confidence tier, and apply the sharp/soft
comparison against the anchor book (Pinnacle).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src import config
from src.ingest import odds


def devig_two_way(dec_a: float, dec_b: float) -> tuple[float, float]:
    """Multiplicative de-vig: fair probs that sum to 1 (spec §5.1)."""
    pa, pb = 1.0 / dec_a, 1.0 / dec_b
    total = pa + pb
    return pa / total, pb / total


def ev_pct(model_prob: float, decimal_odds: float) -> float:
    """EV% = model_prob x payout multiplier - 1 (spec §5.2)."""
    return model_prob * decimal_odds - 1.0


@dataclass
class Edge:
    sport: str
    event_id: str
    market: str
    player: str | None
    side: str                   # over / under / home / away
    line: float | None
    book: str                   # best-price book
    odds_american: int
    odds_decimal: float
    model_prob: float
    fair_prob: float            # de-vigged consensus (sharp-weighted)
    sharp_fair_prob: float | None
    ev: float
    tier: str | None            # A/B/C after adjustments; None = below threshold
    surface: bool               # False -> log-only for calibration
    sample_games: int = 0
    needs_research: bool = False
    tier_notes: list[str] = field(default_factory=list)
    inputs: dict = field(default_factory=dict)
    all_prices: list[dict] = field(default_factory=list)


def _latest_two_way(conn, event_id: str, market: str, player: str | None):
    """Latest over/under pair per book at each book's current line."""
    rows = odds.best_prices(conn, event_id, market, player=player)
    by_book: dict[str, dict[str, dict]] = {}
    for r in rows:
        if r["side"] in ("over", "under"):
            by_book.setdefault(r["book"], {})[r["side"]] = r
    return {b: s for b, s in by_book.items() if {"over", "under"} <= set(s)}


def market_fair_prob(conn, event_id: str, market: str, player: str | None,
                     side: str) -> tuple[float | None, float | None]:
    """(consensus fair prob, sharp-book fair prob) for one side.

    Sharp book (books.yaml role) gets double weight in the consensus.
    """
    book_cfg = config.books()["books"]
    roles = {v["key"]: v["role"] for v in book_cfg.values()}
    pairs = _latest_two_way(conn, event_id, market, player)
    if not pairs:
        return None, None
    total_w = 0.0
    acc = 0.0
    sharp_fair = None
    for book, sides in pairs.items():
        p_over, p_under = devig_two_way(sides["over"]["odds_decimal"],
                                        sides["under"]["odds_decimal"])
        fair = p_over if side == "over" else p_under
        w = 2.0 if roles.get(book) == "sharp" else 1.0
        if roles.get(book) == "sharp":
            sharp_fair = fair
        acc += fair * w
        total_w += w
    return acc / total_w, sharp_fair


def _base_tier(ev: float, tiers: dict) -> str | None:
    if ev >= tiers["A"]["min_ev"]:
        return "A"
    if ev >= tiers["B"]["min_ev"]:
        return "B"
    if ev >= tiers["C"]["min_ev"]:
        return "C"
    return None


def _shift_tier(tier: str, up: bool) -> str:
    order = ["C", "B", "A"]
    i = order.index(tier)
    return order[min(i + 1, 2)] if up else order[max(i - 1, 0)]


def _calibration_factor(conn, sport: str, market: str) -> float:
    row = conn.execute("SELECT factor FROM calibration WHERE sport=? AND market=?",
                       (sport, market)).fetchone()
    return row["factor"] if row else 1.0


def _category_suspended(conn, sport: str, market: str) -> bool:
    row = conn.execute("SELECT status FROM category_status WHERE sport=? AND market=?",
                       (sport, market)).fetchone()
    return bool(row and row["status"] == "suspended")


def evaluate(conn, sport: str, event_id: str, market: str, player: str | None,
             side: str, model_prob: float, sample_games: int = 0,
             is_prop: bool = True) -> Edge | None:
    """Score one model probability against the market. None = no line found."""
    settings = config.settings()
    prices = [p for p in odds.best_prices(conn, event_id, market, player=player, side=side)]
    if not prices:
        return None

    # Phase 6 feedback loop: shrink by realized calibration (spec §3, §8)
    from src.models.common import shrink_probability
    factor = _calibration_factor(conn, sport, market)
    model_prob = shrink_probability(model_prob, factor)
    best = prices[0]  # best decimal first
    fair, sharp_fair = market_fair_prob(conn, event_id, market, player, side)
    if fair is None:
        fair = best["implied_prob"]  # one-sided market: fall back to implied

    ev = ev_pct(model_prob, best["odds_decimal"])
    tiers = settings["tiers"]
    tier = _base_tier(ev, tiers)
    notes: list[str] = []

    min_ev = settings["edges"]["min_ev_props" if is_prop else "min_ev_main_markets"]
    surface = ev >= min_ev and tier is not None

    # negative-CLV categories are suspended pending model review (spec §8.1)
    if surface and _category_suspended(conn, sport, market):
        surface, tier = False, None
        notes.append("category suspended by weekly CLV audit")

    # sharp/soft comparison (spec §5.4)
    if tier and sharp_fair is not None:
        model_edge_vs_sharp = model_prob - sharp_fair
        sharp_edge_vs_book = sharp_fair * best["odds_decimal"] - 1.0
        if model_edge_vs_sharp < -0.02:
            tier = _shift_tier(tier, up=False)
            notes.append(f"model disagrees with sharp fair {sharp_fair:.1%} — tier cut")
        elif sharp_edge_vs_book > 0 and model_edge_vs_sharp >= 0:
            tier = _shift_tier(tier, up=True)
            notes.append(f"sharp consensus also beats {best['book']} — tier boost")

    # sample-size gate for A tier (spec §5.3)
    if tier == "A" and sample_games < tiers["A"]["min_sample_games"]:
        tier = "B"
        notes.append(f"sample {sample_games} < {tiers['A']['min_sample_games']} games — A denied")

    needs_research = surface and ev > settings["edges"]["research_gate_ev"]

    return Edge(
        sport=sport, event_id=event_id, market=market, player=player, side=side,
        line=best["line"], book=best["book"], odds_american=best["odds_american"],
        odds_decimal=best["odds_decimal"], model_prob=round(model_prob, 4),
        fair_prob=round(fair, 4),
        sharp_fair_prob=round(sharp_fair, 4) if sharp_fair is not None else None,
        ev=round(ev, 4), tier=tier if surface else None, surface=surface,
        sample_games=sample_games, needs_research=needs_research,
        tier_notes=notes, all_prices=prices,
    )


def scan(conn, candidates: list[dict]) -> list[Edge]:
    """Evaluate candidates (dicts with evaluate() kwargs); best EV first.

    Keys starting with '_' are carried onto the Edge as metadata (e.g.
    '_inputs' for the honesty layer) — attached HERE, per candidate, so
    re-sorting can never misattribute one pitcher's inputs to another.
    Duplicate candidates (doubleheaders, repeated pulls) collapse to the
    best-EV instance of each (event, market, player, side, line).
    """
    best: dict[tuple, Edge] = {}
    for cand in candidates:
        meta = {k: v for k, v in cand.items() if k.startswith("_")}
        edge = evaluate(conn, **{k: v for k, v in cand.items() if not k.startswith("_")})
        if edge is None:
            continue
        if meta.get("_inputs"):
            edge.inputs["_inputs"] = meta["_inputs"]
        key = (edge.event_id, edge.market, edge.player, edge.side, edge.line)
        if key not in best or edge.ev > best[key].ev:
            best[key] = edge
    edges = sorted(best.values(), key=lambda e: e.ev, reverse=True)
    return edges
