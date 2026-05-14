"""Recommended parlays — combinations of today's top picks scored with the
same-game correlation analyzer. The dashboard renders these so users have a
ready-made +EV slip without typing anything."""

from __future__ import annotations

import json
from itertools import combinations

from app.betslip import Leg, analyze
from app.store import fetch_picks_on


def build_for_date(on_date: str, *, max_legs: int = 3, top_n: int = 10,
                   max_combinations: int = 200) -> list[dict]:
    picks = fetch_picks_on(on_date)
    if not picks:
        return []
    # Use only the strongest 8 individual picks to keep combinatorics sane.
    pool = picks[:8]

    def to_leg(p: dict) -> Leg:
        return Leg(
            sport=p["sport"], player_name=p["player_name"], market=p["market"],
            line=float(p["line"]), side=p["side"],
            price_american=int(p["price_american"]),
            game_id=None, team=None, opp_team=None,
        )

    candidates: list[dict] = []
    for n in (2, min(3, max_legs)):
        seen = 0
        for combo in combinations(pool, n):
            if seen >= max_combinations:
                break
            seen += 1
            legs = [to_leg(p) for p in combo]
            res = analyze(legs, on_date)
            if res.parlay_edge_pct < 0.0:
                continue
            candidates.append({
                "legs": [{
                    "sport": l.leg.sport, "player_name": l.leg.player_name,
                    "market": l.leg.market, "side": l.leg.side, "line": l.leg.line,
                    "price_american": l.leg.price_american,
                    "model_prob": l.model_prob, "rating": l.rating,
                } for l in res.legs],
                "parlay_american": res.parlay_american,
                "parlay_decimal": round(res.parlay_decimal, 3),
                "naive_model_prob": round(res.naive_model_prob, 4),
                "correlated_model_prob": round(res.correlated_model_prob, 4),
                "parlay_edge_pct": round(res.parlay_edge_pct, 2),
                "verdict": res.verdict,
            })
    candidates.sort(key=lambda r: r["parlay_edge_pct"], reverse=True)
    return candidates[:top_n]
