"""Ingestion: pull schedule, box scores, and odds into the DB."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session

from .config import get_settings
from .data import PROVIDERS, OddsAPIClient
from .data.free_odds import FreeOddsAggregator
from .data.synthetic import generate as generate_synthetic_odds
from .db import Game, PlayerGameStat, PropOffer, TeamGameStat, Player

log = logging.getLogger(__name__)


def ingest_box_scores(db: Session, on: date) -> dict:
    summary: dict[str, dict] = {}
    for sport, provider_cls in PROVIDERS.items():
        provider = provider_cls()
        try:
            sched = provider.fetch_schedule(on)
        except Exception as e:
            log.warning("schedule failed %s: %s", sport, e)
            sched = []
        for g in sched:
            _upsert_game(db, sport, g)
        try:
            pgs = provider.fetch_player_box_scores(on)
        except Exception as e:
            log.warning("player box failed %s: %s", sport, e)
            pgs = []
        for r in pgs:
            _upsert_player_game(db, sport, r)
        try:
            tbs = provider.fetch_team_box_scores(on)
        except Exception as e:
            log.warning("team box failed %s: %s", sport, e)
            tbs = []
        for r in tbs:
            _upsert_team_game(db, sport, r)
        provider.close()
        summary[sport] = {"games": len(sched), "player_rows": len(pgs), "team_rows": len(tbs)}
    db.commit()
    return summary


def backfill_box_scores(db: Session, days: int = 30) -> dict:
    today = date.today()
    out = {}
    for i in range(1, days + 1):
        d = today - timedelta(days=i)
        out[d.isoformat()] = ingest_box_scores(db, d)
    return out


def ingest_odds(db: Session, on: date | None = None) -> int:
    """Pull current player-prop offers from all available free sources.

    Uses PrizePicks + DraftKings public JSON by default (no key needed).
    If ODDS_API_KEY is set, also augments with The Odds API.
    """
    settings = get_settings()
    rows: list[dict] = []
    free = FreeOddsAggregator()
    try:
        rows.extend(free.fetch_all(("MLB", "NBA", "NHL"), on=on))
    finally:
        free.close()
    if settings.odds_api_key:
        client = OddsAPIClient()
        try:
            rows.extend(client.fetch_all(("MLB", "NBA", "NHL"), on=on))
        finally:
            client.close()

    # Synthetic fallback: if we got nothing live, build offers from rolling
    # averages so the system still publishes picks today.
    if not rows:
        log.warning("no live odds available; falling back to synthetic offers")
        rows = generate_synthetic_odds(db, ("MLB", "NBA", "NHL"), on=on or date.today())

    n = 0
    for r in rows:
        try:
            gd = date.fromisoformat(r["game_date"][:10]) if r.get("game_date") else (on or date.today())
        except ValueError:
            gd = on or date.today()
        db.add(PropOffer(
            sport=r["sport"],
            game_external_id=str(r["game_external_id"]),
            game_date=gd,
            player_name=r.get("player_name") or "",
            player_external_id=None,
            team=r.get("team"),
            market=r["market"],
            line=float(r.get("line") or 0.0),
            side=(r.get("side") or "").lower(),
            price_american=int(r.get("price_american") or 0),
            book=r.get("book") or "",
        ))
        n += 1
    db.commit()
    return n


def _upsert_game(db: Session, sport: str, g: dict) -> None:
    existing = (
        db.query(Game)
        .filter(Game.sport == sport, Game.external_id == g["external_id"])
        .one_or_none()
    )
    if existing is None:
        db.add(Game(
            sport=sport,
            external_id=g["external_id"],
            game_date=g["game_date"],
            home_team=g.get("home_team") or "",
            away_team=g.get("away_team") or "",
            starts_at=_parse_dt(g.get("starts_at")),
            venue=g.get("venue"),
            meta=g.get("meta") or {},
        ))
    else:
        existing.starts_at = _parse_dt(g.get("starts_at")) or existing.starts_at
        existing.meta = {**(existing.meta or {}), **(g.get("meta") or {})}


def _upsert_player_game(db: Session, sport: str, r: dict) -> None:
    pid = str(r.get("player_external_id"))
    if not pid or pid == "None":
        return
    existing = (
        db.query(PlayerGameStat)
        .filter(
            PlayerGameStat.sport == sport,
            PlayerGameStat.player_external_id == pid,
            PlayerGameStat.game_external_id == str(r["game_external_id"]),
        )
        .one_or_none()
    )
    if existing is None:
        db.add(PlayerGameStat(
            sport=sport,
            player_external_id=pid,
            game_external_id=str(r["game_external_id"]),
            game_date=r["game_date"],
            team=r.get("team"),
            opponent=r.get("opponent"),
            is_home=r.get("is_home"),
            stats=_clean_stats(r.get("stats") or {}),
        ))
    else:
        existing.stats = _clean_stats({**(existing.stats or {}), **(r.get("stats") or {})})

    # Maintain player roster.
    p = (
        db.query(Player)
        .filter(Player.sport == sport, Player.external_id == pid)
        .one_or_none()
    )
    if p is None and r.get("player_name"):
        db.add(Player(sport=sport, external_id=pid, name=r["player_name"], team=r.get("team")))


def _upsert_team_game(db: Session, sport: str, r: dict) -> None:
    if not r.get("team"):
        return
    existing = (
        db.query(TeamGameStat)
        .filter(
            TeamGameStat.sport == sport,
            TeamGameStat.team == r["team"],
            TeamGameStat.game_external_id == str(r["game_external_id"]),
        )
        .one_or_none()
    )
    if existing is None:
        db.add(TeamGameStat(
            sport=sport,
            team=r["team"],
            game_external_id=str(r["game_external_id"]),
            game_date=r["game_date"],
            opponent=r.get("opponent") or "",
            is_home=bool(r.get("is_home")),
            stats=_clean_stats(r.get("stats") or {}),
        ))
    else:
        existing.stats = _clean_stats({**(existing.stats or {}), **(r.get("stats") or {})})


def _clean_stats(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if v is None:
            continue
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            out[k] = v
    return out


def _parse_dt(v):
    if not v:
        return None
    try:
        from dateutil import parser
        return parser.parse(v)
    except Exception:
        return None
