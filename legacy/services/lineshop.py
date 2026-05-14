"""Line shopping: for a given (player, market, line, side), return every
book's posted price so the user can take the best one."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..db import PropOffer
from ..utils import american_to_implied, american_to_decimal


def best_price_table(
    db: Session, sport: str, player_name: str, market: str, line: float, side: str,
    fresh_minutes: int = 120,
) -> list[dict]:
    from datetime import datetime
    cutoff = datetime.utcnow() - timedelta(minutes=fresh_minutes)
    rows = (
        db.query(PropOffer)
        .filter(
            PropOffer.sport == sport,
            PropOffer.market == market,
            PropOffer.captured_at >= cutoff,
        )
        .all()
    )
    matches = []
    pn = (player_name or "").lower().strip()
    for r in rows:
        if (r.player_name or "").lower().strip() != pn:
            continue
        if abs(r.line - line) > 0.01:
            continue
        if not r.side.lower().startswith(side.lower()):
            continue
        matches.append({
            "book": r.book,
            "price_american": r.price_american,
            "implied_prob": round(american_to_implied(r.price_american), 4),
            "decimal_odds": round(american_to_decimal(r.price_american), 3),
        })
    matches.sort(key=lambda x: x["decimal_odds"], reverse=True)
    return matches


def alt_line_ladder(
    db: Session, sport: str, player_name: str, market: str, side: str,
    fresh_minutes: int = 120,
) -> list[dict]:
    """All distinct lines posted for this (player, market, side), sorted
    by line value. Useful for picking a sweet-spot line."""
    from datetime import datetime
    cutoff = datetime.utcnow() - timedelta(minutes=fresh_minutes)
    rows = (
        db.query(PropOffer)
        .filter(
            PropOffer.sport == sport,
            PropOffer.market == market,
            PropOffer.captured_at >= cutoff,
        )
        .all()
    )
    pn = (player_name or "").lower().strip()
    by_line: dict[float, list[PropOffer]] = {}
    for r in rows:
        if (r.player_name or "").lower().strip() != pn:
            continue
        if not r.side.lower().startswith(side.lower()):
            continue
        by_line.setdefault(round(r.line, 2), []).append(r)
    out = []
    for line_val, offers in sorted(by_line.items()):
        best = max(offers, key=lambda o: american_to_decimal(o.price_american))
        out.append({
            "line": line_val,
            "best_book": best.book,
            "best_price_american": best.price_american,
            "n_books": len(offers),
        })
    return out
