"""Grade picks against actual box scores and report ROI / hit rate.

Self-improvement: after grading, retraining the per-(sport,market) models on
the now-larger labeled history is what closes the loop. The scheduler runs
trainer.train_all nightly.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable

from sqlalchemy.orm import Session

from .db import Pick, PlayerGameStat, Player
from .picks import _resolve_player
from .utils import american_to_decimal


def grade_picks(db: Session, on: date | None = None) -> dict:
    on = on or (date.today() - timedelta(days=1))
    picks = db.query(Pick).filter(Pick.pick_date == on, Pick.result.is_(None)).all()
    graded = wins = losses = pushes = 0
    pl_units = 0.0

    for p in picks:
        player = _resolve_player(db, p.sport, p.player_name)
        if not player:
            continue
        # find that player's stat row for the game
        row = (
            db.query(PlayerGameStat)
            .filter(
                PlayerGameStat.sport == p.sport,
                PlayerGameStat.player_external_id == player.external_id,
                PlayerGameStat.game_external_id == str(p.game_external_id) if p.game_external_id else PlayerGameStat.game_date == on,
            )
            .one_or_none()
        )
        if not row:
            continue
        actual = (row.stats or {}).get(p.market)
        if actual is None:
            continue
        actual = float(actual)

        if actual == p.line:
            p.result = "push"
            pushes += 1
        elif (p.side == "over" and actual > p.line) or (p.side == "under" and actual < p.line):
            p.result = "win"
            wins += 1
            pl_units += american_to_decimal(p.price_american) - 1.0
        else:
            p.result = "loss"
            losses += 1
            pl_units -= 1.0
        p.actual_value = actual
        p.graded_at = datetime.utcnow()
        graded += 1

    db.commit()
    return {
        "date": on.isoformat(),
        "graded": graded,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "hit_rate": round(wins / max(1, wins + losses), 4),
        "pl_units": round(pl_units, 3),
    }


def progress_report(db: Session, days: int = 30) -> dict:
    cutoff = date.today() - timedelta(days=days)
    picks = (
        db.query(Pick)
        .filter(Pick.pick_date >= cutoff, Pick.result.in_(("win", "loss", "push")))
        .all()
    )
    total = len(picks)
    if total == 0:
        return {"days": days, "picks": 0}
    wins = sum(1 for p in picks if p.result == "win")
    losses = sum(1 for p in picks if p.result == "loss")
    pushes = sum(1 for p in picks if p.result == "push")
    pl = sum(
        (american_to_decimal(p.price_american) - 1.0) if p.result == "win"
        else (-1.0 if p.result == "loss" else 0.0)
        for p in picks
    )
    by_sport: dict[str, dict] = {}
    for p in picks:
        b = by_sport.setdefault(p.sport, {"n": 0, "w": 0, "l": 0, "pl": 0.0})
        b["n"] += 1
        b["w"] += int(p.result == "win")
        b["l"] += int(p.result == "loss")
        b["pl"] += (american_to_decimal(p.price_american) - 1.0) if p.result == "win" else (-1.0 if p.result == "loss" else 0.0)
    for s in by_sport.values():
        s["hit_rate"] = round(s["w"] / max(1, s["w"] + s["l"]), 4)
        s["pl_units"] = round(s["pl"], 3)
        del s["pl"]
    return {
        "days": days,
        "picks": total,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "hit_rate": round(wins / max(1, wins + losses), 4),
        "pl_units": round(pl, 3),
        "roi_pct": round(100.0 * pl / max(1, total), 3),
        "by_sport": by_sport,
    }
