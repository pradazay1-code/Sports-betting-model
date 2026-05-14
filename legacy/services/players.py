"""Player search, roster browse, and recent-stats services."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import mean, median
from typing import Any, Iterable

from rapidfuzz import process, fuzz
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..db import Player, PlayerGameStat


def search_players(db: Session, q: str, sport: str | None = None, limit: int = 20) -> list[dict]:
    """Fuzzy player search by name."""
    base = db.query(Player)
    if sport:
        base = base.filter(Player.sport == sport)
    cands = base.all()
    if not q:
        return [_player_summary(p) for p in cands[:limit]]
    names = [p.name for p in cands]
    matches = process.extract(q, names, scorer=fuzz.WRatio, limit=limit, score_cutoff=50)
    return [_player_summary(cands[idx]) for _, _, idx in matches]


def _player_summary(p: Player) -> dict:
    meta = p.meta or {}
    return {
        "id": p.external_id,
        "name": p.name,
        "team": p.team,
        "sport": p.sport,
        "position": p.position,
        "jersey": meta.get("jersey"),
        "headshot_url": meta.get("headshot_url"),
    }


def list_roster(db: Session, sport: str, team: str | None = None) -> list[dict]:
    """Active roster for a sport, optionally filtered to a team. "Active"
    means the player has appeared in a box-score within the last 21 days."""
    cutoff = date.today() - timedelta(days=21)
    active_ids_subq = (
        select(PlayerGameStat.player_external_id)
        .where(PlayerGameStat.sport == sport)
        .where(PlayerGameStat.game_date >= cutoff)
        .distinct()
    )
    q = (
        db.query(Player)
        .filter(Player.sport == sport)
        .filter(Player.external_id.in_(active_ids_subq))
    )
    if team:
        q = q.filter(Player.team.ilike(f"%{team}%"))
    return sorted(
        (_player_summary(p) for p in q.all()),
        key=lambda x: ((x["team"] or "z"), x["name"]),
    )


def list_teams(db: Session, sport: str) -> list[str]:
    rows = (
        db.query(Player.team)
        .filter(Player.sport == sport)
        .filter(Player.team.is_not(None))
        .distinct()
        .all()
    )
    return sorted({r[0] for r in rows if r[0]})


def player_detail(db: Session, sport: str, external_id: str, last_n: int = 20) -> dict:
    """Full player profile: season aggregates, last-N games, hit-rate vs typical lines."""
    p = (
        db.query(Player)
        .filter(Player.sport == sport, Player.external_id == external_id)
        .one_or_none()
    )
    if not p:
        return {}
    rows = (
        db.query(PlayerGameStat)
        .filter(
            PlayerGameStat.sport == sport,
            PlayerGameStat.player_external_id == external_id,
        )
        .order_by(PlayerGameStat.game_date.desc())
        .limit(last_n)
        .all()
    )
    games = [
        {
            "date": r.game_date.isoformat(),
            "team": r.team,
            "opponent": r.opponent,
            "is_home": r.is_home,
            "stats": _clean_stats(r.stats or {}),
        }
        for r in rows
    ]

    # Aggregate per-stat means/medians/highs.
    by_stat: dict[str, list[float]] = defaultdict(list)
    for g in games:
        for k, v in (g["stats"] or {}).items():
            try:
                by_stat[k].append(float(v))
            except (TypeError, ValueError):
                continue
    agg: dict[str, dict[str, float]] = {}
    for stat, vals in by_stat.items():
        if not vals:
            continue
        agg[stat] = {
            "n": len(vals),
            "avg": round(mean(vals), 3),
            "median": round(median(vals), 3),
            "max": round(max(vals), 3),
            "min": round(min(vals), 3),
            "last5_avg": round(mean(vals[:5]) if len(vals) >= 1 else 0.0, 3),
            "last10_avg": round(mean(vals[:10]) if len(vals) >= 1 else 0.0, 3),
        }

    meta = p.meta or {}
    return {
        "id": p.external_id,
        "name": p.name,
        "team": p.team,
        "sport": p.sport,
        "position": p.position,
        "jersey": meta.get("jersey"),
        "headshot_url": meta.get("headshot_url"),
        "games": games,
        "aggregates": agg,
    }


def _clean_stats(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if v is None:
            continue
        try:
            out[k] = round(float(v), 2)
        except (TypeError, ValueError):
            out[k] = v
    return out
