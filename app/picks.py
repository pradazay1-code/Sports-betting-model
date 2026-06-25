"""Daily picks generator.

For every recent prop offer, look up the relevant (sport, market) model, run
inference for the player, compute fair prob (de-vig the book's two-sided
price), edge%, Kelly stake, and the 0..100 rating. Keep the top N globally.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Iterable

from app.config import CFG, SPORTS
from app.ev import devig_two_way, kelly_fraction, price, rating
from app.features import build_inference_features
from app.models import prop_model
from app.store import (
    connection,
    fetch_recent_offers,
    insert_pick,
    replace_picks_for_date,
)
from app.utils import american_to_decimal, get_logger, now_iso, today_local

LOG = get_logger("picks")


def _offers_today(sport: str, since_iso: str) -> list[dict]:
    rows = fetch_recent_offers(sport, since_iso)
    # Collapse to (player, market, line) -> list of (book, over, under)
    return rows


def _consensus_groups(rows: Iterable[dict]) -> dict[tuple, list[dict]]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        key = (r["sport"], r["player_name"], r["market"], float(r["line"]))
        groups[key].append(r)
    return groups


def _best_two_way(books: list[dict]) -> tuple[dict | None, dict | None]:
    """Pick the book offering the best over price and the book offering the
    best under price (the actual line-shopped offer)."""
    best_over = max((b for b in books if b.get("over_price") is not None),
                    key=lambda b: american_to_decimal(b["over_price"]), default=None)
    best_under = max((b for b in books if b.get("under_price") is not None),
                     key=lambda b: american_to_decimal(b["under_price"]), default=None)
    return best_over, best_under


def generate(on_date: str | None = None, *, top_n: int = 25,
             min_edge_pct: float = 1.0, min_rating: float = 40.0) -> list[dict]:
    if on_date is None:
        on_date = today_local().isoformat()

    # Use offers fetched within the last 36h.
    since = (datetime.utcnow() - timedelta(hours=36)).isoformat(timespec="seconds")

    candidates: list[dict] = []
    for sport in SPORTS:
        offers = _offers_today(sport, since)
        if not offers:
            continue
        groups = _consensus_groups(offers)
        for (sport_, name, market, line), books in groups.items():
            best_over, best_under = _best_two_way(books)
            if not best_over or not best_under:
                continue
            tm = prop_model.load(sport_, market)
            if tm is None:
                continue
            feats = build_inference_features(sport_, market, name, on_date)
            if feats is None:
                continue

            fair_over, fair_under = devig_two_way(
                best_over["over_price"], best_under["under_price"]
            )
            try:
                p_over = tm.prob_over(feats, float(line))
            except Exception as e:  # noqa: BLE001
                LOG.debug("prob_over failed for %s/%s/%s: %s", sport_, market, name, e)
                continue
            p_under = 1.0 - p_over

            for side, model_p, fair_p, off in (
                ("over", p_over, fair_over, best_over),
                ("under", p_under, fair_under, best_under),
            ):
                amer = off["over_price"] if side == "over" else off["under_price"]
                if amer is None:
                    continue
                priced = price(side, model_p, fair_p, amer)
                if priced.edge_pct < min_edge_pct:
                    continue
                rate, parts = rating(
                    edge_pct=priced.edge_pct,
                    model_prob=model_p,
                    fair_prob=fair_p,
                    n_train_rows=tm.n_train,
                    n_books=len({b["book"] for b in books}),
                )
                if rate < min_rating:
                    continue
                rationale = json.dumps({
                    "components": parts,
                    "books_count": len({b["book"] for b in books}),
                    "pred_mean": tm.predict_mean(feats),
                    "residual_std": tm.residual_std,
                    "book": off["book"],
                })
                candidates.append({
                    "sport": sport_, "player_name": name, "market": market,
                    "side": side, "line": float(line), "price_american": amer,
                    "book": off["book"], "model_prob": model_p,
                    "fair_prob": fair_p, "edge_pct": priced.edge_pct,
                    "kelly_stake": priced.kelly_stake * CFG.kelly_fraction,
                    "rating": rate, "rationale": rationale,
                })

    candidates.sort(key=lambda r: r["rating"], reverse=True)
    candidates = candidates[:top_n]

    replace_picks_for_date(on_date)
    generated_at = now_iso()
    saved: list[dict] = []
    for c in candidates:
        row = {**c, "generated_at": generated_at, "on_date": on_date}
        insert_pick(row)
        saved.append(row)
    LOG.info("generated %d picks for %s", len(saved), on_date)
    return saved
