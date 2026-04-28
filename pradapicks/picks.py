"""Daily Top-N picks generator.

Pipeline per pick day:
  1) Pull current PropOffers from DB (or freshly fetched odds).
  2) Resolve player_external_id from name (rapidfuzz on Player table).
  3) Build features as of game_date for each prop.
  4) Score (model_prob, fair_prob, edge, rating).
  5) Take the highest-EV side per (player, market, line, game).
  6) De-dup and rank by rating; cap to N.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from typing import Iterable

from rapidfuzz import process, fuzz
from sqlalchemy.orm import Session

from .config import get_settings
from .db import Pick, Player, PropOffer
from .features import build_features_for_target
from .models.trainer import load_active_model
from .scoring import fair_two_way, rating_from_components
from .utils import american_to_implied, edge_pct, kelly_fraction

log = logging.getLogger(__name__)


def _resolve_player(db: Session, sport: str, name: str) -> Player | None:
    if not name:
        return None
    candidates = db.query(Player).filter(Player.sport == sport).all()
    if not candidates:
        return None
    names = [p.name for p in candidates]
    match = process.extractOne(name, names, scorer=fuzz.WRatio, score_cutoff=82)
    if not match:
        return None
    idx = match[2]
    return candidates[idx]


def _consensus(offers: list[PropOffer]) -> dict:
    """Group by (player, market, line, side) and return consensus stats per (player, market, line)."""
    by_key: dict[tuple, list[PropOffer]] = defaultdict(list)
    for o in offers:
        by_key[(o.player_name.lower(), o.market, round(o.line, 2))].append(o)
    return by_key


def generate_daily_picks(db: Session, on: date | None = None, top_n: int | None = None) -> list[Pick]:
    settings = get_settings()
    on = on or date.today()
    top_n = top_n or settings.daily_pick_count

    offers = (
        db.query(PropOffer)
        .filter(PropOffer.game_date == on)
        .all()
    )
    if not offers:
        log.info("no offers for %s", on)
        return []

    cache_models: dict[tuple[str, str], object] = {}
    candidates: list[dict] = []

    grouped = _consensus(offers)
    for (player_lc, market, line), group in grouped.items():
        sport = group[0].sport
        # find best price per side across books
        best_over = max((o for o in group if o.side.startswith("over")), key=lambda x: _decimal_price(x.price_american), default=None)
        best_under = max((o for o in group if o.side.startswith("under")), key=lambda x: _decimal_price(x.price_american), default=None)

        # fair (no-vig) probabilities using consensus median if both sides exist
        fair_o = fair_u = None
        if best_over and best_under:
            fair_o, fair_u = fair_two_way(best_over.price_american, best_under.price_american)

        # load model
        key = (sport, market)
        if key not in cache_models:
            cache_models[key] = load_active_model(db, sport, market)
        model = cache_models[key]

        # resolve player
        player = _resolve_player(db, sport, group[0].player_name)
        player_ext = player.external_id if player else None
        team = player.team if player else None
        opponent = _opponent_for(db, sport, group[0].game_external_id, team) if team else None

        if model and player_ext:
            feats = build_features_for_target(
                db, sport=sport, market=market,
                player_external_id=player_ext, game_date=on,
                opponent=opponent, is_home=None, line=line,
            )
            p_over, mu = model.predict_over_prob(feats, line)
            sample_size = model.metrics.n
        else:
            # fallback: use no-vig fair as model probability (zero edge); won't beat threshold.
            p_over = fair_o if fair_o is not None else 0.5
            mu = line
            sample_size = 0

        for side_name, offer, p_side, fair_p in (
            ("over", best_over, p_over, fair_o),
            ("under", best_under, 1.0 - p_over, fair_u),
        ):
            if offer is None:
                continue
            ed = edge_pct(p_side, offer.price_american)
            if ed < settings.min_edge_pct:
                continue
            rating, breakdown = rating_from_components(
                model_prob=p_side,
                price_american=offer.price_american,
                fair_prob=fair_p,
                sample_size=sample_size,
                market_consensus_count=len({o.book for o in group}),
            )
            kel = kelly_fraction(p_side, offer.price_american, settings.kelly_fraction)
            candidates.append({
                "sport": sport,
                "player_name": offer.player_name,
                "team": team,
                "opponent": opponent,
                "market": market,
                "line": line,
                "side": side_name,
                "book": offer.book,
                "price_american": offer.price_american,
                "model_prob": p_side,
                "implied_prob": american_to_implied(offer.price_american),
                "edge_pct": ed,
                "rating": rating,
                "kelly_unit": kel,
                "rationale": {**breakdown, "predicted_value": round(mu, 3), "sample_size": sample_size},
                "game_external_id": offer.game_external_id,
            })

    # one pick per (player, market) — keep highest rating
    best_per_key: dict[tuple, dict] = {}
    for c in candidates:
        k = (c["player_name"].lower(), c["market"])
        if k not in best_per_key or c["rating"] > best_per_key[k]["rating"]:
            best_per_key[k] = c

    ranked = sorted(best_per_key.values(), key=lambda x: x["rating"], reverse=True)[:top_n]

    # persist
    db.query(Pick).filter(Pick.pick_date == on).delete()
    pick_objs = [Pick(pick_date=on, **c) for c in ranked]
    db.add_all(pick_objs)
    db.commit()
    return pick_objs


def _opponent_for(db: Session, sport: str, game_ext_id: str, team: str | None) -> str | None:
    if not team:
        return None
    from .db import Game
    g = db.query(Game).filter(Game.sport == sport, Game.external_id == str(game_ext_id)).one_or_none()
    if not g:
        return None
    if g.home_team and team and team.lower() in g.home_team.lower():
        return g.away_team
    return g.home_team


def _decimal_price(american: int) -> float:
    if american > 0:
        return 1 + american / 100
    if american < 0:
        return 1 + 100 / abs(american)
    return 1.0
