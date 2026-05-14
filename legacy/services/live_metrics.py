"""Live metrics for a single player + market + line — used by the bet slip
analyzer to surface "why" alongside the rating."""
from __future__ import annotations

from datetime import date

from rapidfuzz import process, fuzz
from sqlalchemy.orm import Session

from ..db import Player, PlayerGameStat
from ..features import build_features_for_target
from ..models.trainer import load_active_model
from ..utils import american_to_implied, edge_pct
from .matchups import matchup_for_team
from .players import player_detail


def resolve_player(db: Session, sport: str, name: str) -> Player | None:
    if not name:
        return None
    candidates = db.query(Player).filter(Player.sport == sport).all()
    if not candidates:
        return None
    names = [p.name for p in candidates]
    match = process.extractOne(name, names, scorer=fuzz.WRatio, score_cutoff=80)
    return candidates[match[2]] if match else None


def metrics_for_leg(
    db: Session,
    sport: str,
    player_name: str,
    market: str,
    line: float,
    side: str,
    price_american: int,
    opponent: str | None = None,
    is_home: bool | None = None,
) -> dict:
    """Return rich diagnostics for one bet leg."""
    player = resolve_player(db, sport, player_name)
    today = date.today()

    out = {
        "resolved_player": player.name if player else None,
        "team": player.team if player else None,
        "sport": sport,
        "market": market,
        "line": line,
        "side": side,
        "price_american": price_american,
        "implied_prob": round(american_to_implied(price_american), 4),
    }

    if not player:
        out["model_prob"] = None
        out["edge_pct"] = None
        out["note"] = "player not found in roster"
        return out

    # Recent form
    detail = player_detail(db, sport, player.external_id, last_n=15)
    agg = (detail.get("aggregates") or {}).get(market)
    games = detail.get("games") or []

    # Hit rates against the requested line
    vals = []
    for g in games:
        v = (g.get("stats") or {}).get(market)
        if v is not None:
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                pass
    hit_rate_5 = (
        round(sum(1 for v in vals[:5] if v > line) / max(1, min(5, len(vals))), 3)
        if vals else None
    )
    hit_rate_10 = (
        round(sum(1 for v in vals[:10] if v > line) / max(1, min(10, len(vals))), 3)
        if vals else None
    )

    # Model probability
    model = load_active_model(db, sport, market)
    p_over = None
    predicted = None
    if model:
        feats = build_features_for_target(
            db, sport=sport, market=market,
            player_external_id=player.external_id, game_date=today,
            opponent=opponent, is_home=is_home, line=line,
        )
        p_over, predicted = model.predict_over_prob(feats, line)
    p_side = (
        p_over if side.startswith("over")
        else (1.0 - p_over) if p_over is not None else None
    )

    # Defensive matchup if we have an opponent
    matchup = matchup_for_team(db, sport, opponent) if opponent else {}
    matchup_for_market = matchup.get(market)

    out.update({
        "model_prob": round(p_side, 4) if p_side is not None else None,
        "predicted_value": round(predicted, 3) if predicted is not None else None,
        "edge_pct": round(edge_pct(p_side, price_american), 3) if p_side is not None else None,
        "season_avg": agg.get("avg") if agg else None,
        "season_median": agg.get("median") if agg else None,
        "last5_avg": agg.get("last5_avg") if agg else None,
        "last10_avg": agg.get("last10_avg") if agg else None,
        "hit_rate_l5": hit_rate_5,
        "hit_rate_l10": hit_rate_10,
        "games_played": agg.get("n") if agg else 0,
        "opponent": opponent,
        "opponent_matchup": matchup_for_market,  # rank vs allowing this stat
        "recent": [
            {"date": g["date"], "v": (g.get("stats") or {}).get(market), "opp": g.get("opponent")}
            for g in games[:10]
        ],
    })
    return out
