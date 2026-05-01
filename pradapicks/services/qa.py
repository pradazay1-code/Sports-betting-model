"""Natural-language Q&A engine for sports-betting questions.

Rule-based intent router (no paid LLM). Recognizes patterns like:
  "will the lakers win tonight?"     -> game prediction lookup
  "what team will not hit a home run today?"  -> low-probability HR scan
  "best nba prop tonight"            -> top NBA pick
  "lebron james over points"         -> player prop analysis
  "how is judge hitting lately?"     -> player recent form
  "biggest favorite in mlb today"    -> highest home_win_prob

Each intent calls the existing data + model layer and returns a structured
analysis plus a human-readable answer. No external API needed.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from rapidfuzz import process, fuzz
from sqlalchemy.orm import Session

from ..db import GamePrediction, Pick, Player
from ..services.live_metrics import metrics_for_leg, resolve_player
from ..services.players import player_detail


# --- intent detection ----------------------------------------------------

_TEAM_WORDS = {
    "lakers": "Los Angeles Lakers", "celtics": "Boston Celtics",
    "warriors": "Golden State Warriors", "heat": "Miami Heat",
    "knicks": "New York Knicks", "nets": "Brooklyn Nets",
    "mavs": "Dallas Mavericks", "mavericks": "Dallas Mavericks",
    "bucks": "Milwaukee Bucks", "76ers": "Philadelphia 76ers",
    "sixers": "Philadelphia 76ers", "thunder": "Oklahoma City Thunder",
    "yankees": "New York Yankees", "red sox": "Boston Red Sox",
    "dodgers": "Los Angeles Dodgers", "mets": "New York Mets",
    "astros": "Houston Astros", "braves": "Atlanta Braves",
    "rangers": "New York Rangers", "bruins": "Boston Bruins",
    "oilers": "Edmonton Oilers", "lightning": "Tampa Bay Lightning",
    "leafs": "Toronto Maple Leafs", "panthers": "Florida Panthers",
}

_SPORT_WORDS = {
    "nba": "NBA", "basketball": "NBA",
    "mlb": "MLB", "baseball": "MLB",
    "nhl": "NHL", "hockey": "NHL",
}

_MARKET_WORDS = {
    "points": "player_points", "rebounds": "player_rebounds",
    "assists": "player_assists", "threes": "player_threes",
    "3s": "player_threes", "3-pointers": "player_threes",
    "pra": "player_pra", "p+r+a": "player_pra",
    "hits": "batter_hits", "home runs": "batter_home_runs",
    "homers": "batter_home_runs", "hr": "batter_home_runs",
    "rbis": "batter_rbis", "total bases": "batter_total_bases",
    "strikeouts": "pitcher_strikeouts", "ks": "pitcher_strikeouts",
    "shots on goal": "player_shots_on_goal", "sog": "player_shots_on_goal",
    "saves": "goalie_saves",
}


def _fuzzy_team(text: str, db: Session, sport: str | None) -> str | None:
    t = text.lower()
    for word, full in _TEAM_WORDS.items():
        if word in t:
            return full
    # Try matching against actual game predictions today
    games = db.query(GamePrediction).filter(GamePrediction.game_date == date.today()).all()
    teams = {g.home_team for g in games if g.home_team} | {g.away_team for g in games if g.away_team}
    if teams:
        m = process.extractOne(text, list(teams), scorer=fuzz.partial_ratio, score_cutoff=70)
        if m:
            return m[0]
    return None


def _detect_sport(text: str) -> str | None:
    t = text.lower()
    for w, s in _SPORT_WORDS.items():
        if w in t:
            return s
    return None


def _detect_market(text: str) -> str | None:
    t = text.lower()
    for w, m in _MARKET_WORDS.items():
        if w in t:
            return m
    return None


def _detect_player(db: Session, text: str, sport: str | None) -> Player | None:
    base = db.query(Player)
    if sport:
        base = base.filter(Player.sport == sport)
    cands = base.all()
    if not cands:
        return None
    names = [p.name for p in cands]
    m = process.extractOne(text, names, scorer=fuzz.partial_ratio, score_cutoff=80)
    if not m:
        return None
    return cands[m[2]]


# --- intent handlers -----------------------------------------------------

def _intent_game_winner(db: Session, text: str) -> dict | None:
    """Will [TEAM] win? — find today's game with that team."""
    if not re.search(r"\b(win|beat|cover|lose|favorite|favourite)\b", text, re.I):
        return None
    sport = _detect_sport(text)
    team = _fuzzy_team(text, db, sport)
    if not team:
        return None
    # Find today's game with this team
    pred = (
        db.query(GamePrediction)
        .filter(GamePrediction.game_date == date.today())
        .filter((GamePrediction.home_team == team) | (GamePrediction.away_team == team))
        .first()
    )
    if not pred:
        return {
            "intent": "game_winner",
            "answer": f"No game found for {team} today.",
            "data": None,
        }
    is_home = pred.home_team == team
    win_prob = pred.home_win_prob if is_home else (1 - pred.home_win_prob)
    pred_score = pred.pred_home_score if is_home else pred.pred_away_score
    opp_score = pred.pred_away_score if is_home else pred.pred_home_score
    opp_team = pred.away_team if is_home else pred.home_team
    verdict = "favored" if win_prob > 0.55 else "slight favorite" if win_prob > 0.5 else "underdog"
    answer = (
        f"{team} {'hosts' if is_home else 'visits'} {opp_team} today. "
        f"Model gives {team} a {win_prob*100:.1f}% win probability ({verdict}). "
        f"Predicted score: {pred_score:.1f}–{opp_score:.1f} "
        f"(total {pred.pred_total:.1f}, spread {pred.pred_spread:+.1f} for home). "
        f"Confidence: {pred.confidence*100:.0f}%."
    )
    return {
        "intent": "game_winner",
        "team": team,
        "opponent": opp_team,
        "is_home": is_home,
        "win_prob": round(win_prob, 4),
        "pred_score": pred_score,
        "opp_score": opp_score,
        "answer": answer,
        "data": {
            "game_id": pred.game_external_id,
            "sport": pred.sport,
            "total": pred.pred_total,
            "spread": pred.pred_spread,
            "confidence": pred.confidence,
        },
    }


def _intent_player_prop(db: Session, text: str) -> dict | None:
    """Player + market detection — analyze a prop question."""
    sport = _detect_sport(text)
    market = _detect_market(text)
    if not market:
        return None
    player = _detect_player(db, text, sport)
    if not player:
        return None
    side_match = re.search(r"\b(over|under|more|less|fewer|than)\b", text, re.I)
    side = "over"
    if side_match:
        if side_match.group(1).lower() in ("under", "less", "fewer"):
            side = "under"
    line_match = re.search(r"(\d+(?:\.\d+)?)", text)
    line = float(line_match.group(1)) if line_match else None

    # If no line provided, use the model's predicted value as the implicit line.
    detail = player_detail(db, player.sport, player.external_id, last_n=15)
    agg = (detail.get("aggregates") or {}).get(market)
    if line is None and agg:
        line = round(agg.get("avg") or 0, 1)
    if line is None:
        return None

    # Use the leg metrics service for a full read.
    m = metrics_for_leg(
        db, sport=player.sport, player_name=player.name, market=market,
        line=line, side=side, price_american=-110,
    )
    p = m.get("model_prob")
    answer = (
        f"{player.name} ({player.sport}) {side} {line} {market.replace('_', ' ')}: "
        f"model says {p*100:.1f}% probability." if p is not None else
        f"{player.name} ({player.sport}) recent average for {market.replace('_', ' ')} "
        f"is {m.get('season_avg')} (L5 {m.get('last5_avg')}, L10 {m.get('last10_avg')})."
    )
    if m.get("opponent_matchup"):
        mu = m["opponent_matchup"]
        answer += f" Opponent ranks #{mu['rank']}/{mu['of']} at allowing this stat."
    if m.get("hit_rate_l10") is not None:
        answer += f" L10 hit rate vs {line}: {m['hit_rate_l10']*100:.0f}%."
    return {"intent": "player_prop", "player": player.name, "market": market,
            "line": line, "side": side, "answer": answer, "data": m}


def _intent_top_picks(db: Session, text: str) -> dict | None:
    """Best [sport] [pick/prop/parlay/bet] today/tonight."""
    if not re.search(r"\b(best|top|safest|locks?|biggest)\b", text, re.I):
        return None
    sport = _detect_sport(text)
    q = db.query(Pick).filter(Pick.pick_date == date.today())
    if sport:
        q = q.filter(Pick.sport == sport)
    rows = q.order_by(Pick.rating.desc()).limit(5).all()
    if not rows:
        return {"intent": "top_picks", "answer": "No picks generated yet today.", "data": []}
    picks = [
        {
            "player": p.player_name, "market": p.market, "line": p.line,
            "side": p.side, "price": p.price_american, "rating": p.rating,
            "edge_pct": p.edge_pct, "sport": p.sport,
        } for p in rows
    ]
    sport_label = sport or "all sports"
    top = picks[0]
    answer = (
        f"Top {sport_label} pick: **{top['player']}** {top['side']} {top['line']} {top['market']} "
        f"({top['price']:+d}) — rating {top['rating']:.0f}/100, edge {top['edge_pct']:+.1f}%."
        f"\n\nNext 4: " + " · ".join(
            f"{p['player']} {p['side']} {p['line']} ({p['rating']:.0f})" for p in picks[1:5]
        )
    )
    return {"intent": "top_picks", "answer": answer, "data": picks}


def _intent_low_prob_market(db: Session, text: str) -> dict | None:
    """'Which team will NOT do X' — find lowest probability."""
    market = _detect_market(text)
    if not market:
        return None
    if not re.search(r"\b(not|won't|wont|fewer|under|less|least|fewest)\b", text, re.I):
        return None
    sport = _detect_sport(text) or ("MLB" if "home run" in text.lower() else None)
    rows = (
        db.query(Pick)
        .filter(Pick.pick_date == date.today())
        .filter(Pick.market == market)
        .filter(Pick.side == "under")
    )
    if sport:
        rows = rows.filter(Pick.sport == sport)
    rows = rows.order_by(Pick.model_prob.desc()).limit(5).all()
    if not rows:
        return {
            "intent": "low_prob",
            "answer": f"Couldn't find a high-probability under for {market} today (no picks for this market yet).",
            "data": [],
        }
    top = rows[0]
    answer = (
        f"Most likely **NOT** to hit: **{top.player_name}** ({top.team or '?'}) — "
        f"model gives {top.model_prob*100:.1f}% probability of staying UNDER {top.line}, "
        f"rating {top.rating:.0f}/100."
    )
    return {
        "intent": "low_prob",
        "answer": answer,
        "data": [{"player": r.player_name, "team": r.team, "prob_under": r.model_prob,
                  "line": r.line, "rating": r.rating} for r in rows],
    }


def _intent_player_form(db: Session, text: str) -> dict | None:
    """How is X hitting/playing/shooting lately?"""
    if not re.search(r"\b(how|form|hitting|playing|shooting|streak|hot|cold|trend)\b", text, re.I):
        return None
    sport = _detect_sport(text)
    player = _detect_player(db, text, sport)
    if not player:
        return None
    detail = player_detail(db, player.sport, player.external_id, last_n=10)
    if not detail or not detail.get("aggregates"):
        return {"intent": "player_form", "answer": f"No recent stats for {player.name}.", "data": None}
    parts = []
    for stat, agg in list(detail["aggregates"].items())[:5]:
        delta = agg["last5_avg"] - agg["avg"]
        arrow = "↑" if delta > 0 else "↓"
        parts.append(f"{stat.replace('_', ' ')} {agg['last5_avg']:.1f} {arrow} (season {agg['avg']:.1f})")
    answer = f"**{player.name}** ({player.sport}, {player.team or '?'}) — last 5 games:\n" + " · ".join(parts)
    return {"intent": "player_form", "player": player.name, "answer": answer, "data": detail["aggregates"]}


def _intent_biggest_favorite(db: Session, text: str) -> dict | None:
    if not re.search(r"\b(biggest|largest|strongest|surest)\s+(favorite|favourite|lock)", text, re.I):
        return None
    sport = _detect_sport(text)
    q = db.query(GamePrediction).filter(GamePrediction.game_date == date.today())
    if sport:
        q = q.filter(GamePrediction.sport == sport)
    rows = q.all()
    if not rows:
        return {"intent": "biggest_fav", "answer": "No game predictions today.", "data": None}
    rows.sort(key=lambda g: max(g.home_win_prob, 1 - g.home_win_prob), reverse=True)
    g = rows[0]
    fav = g.home_team if g.home_win_prob > 0.5 else g.away_team
    prob = max(g.home_win_prob, 1 - g.home_win_prob)
    answer = (
        f"Biggest favorite today: **{fav}** at {prob*100:.1f}% win probability "
        f"vs {g.away_team if fav == g.home_team else g.home_team}. "
        f"Predicted: {g.pred_home_score:.1f}–{g.pred_away_score:.1f}."
    )
    return {"intent": "biggest_fav", "answer": answer, "data": {
        "team": fav, "win_prob": prob, "sport": g.sport,
    }}


# --- public --------------------------------------------------------------

def _intent_total_spread(db: Session, text: str) -> dict | None:
    """Total / over-under / spread questions about a game."""
    if not re.search(r"\b(total|over\s*under|o/u|spread|points|score)\b", text, re.I):
        return None
    sport = _detect_sport(text)
    team = _fuzzy_team(text, db, sport)
    if not team:
        return None
    pred = (
        db.query(GamePrediction)
        .filter(GamePrediction.game_date == date.today())
        .filter((GamePrediction.home_team == team) | (GamePrediction.away_team == team))
        .first()
    )
    if not pred:
        return None
    answer = (
        f"{pred.away_team} @ {pred.home_team}: predicted total **{pred.pred_total:.1f}** "
        f"({pred.pred_home_score:.1f}–{pred.pred_away_score:.1f}). "
        f"Spread {pred.pred_spread:+.1f} (home favorite means negative). "
        f"Confidence {pred.confidence*100:.0f}%."
    )
    return {"intent": "total_spread", "answer": answer, "data": {
        "total": pred.pred_total, "spread": pred.pred_spread, "confidence": pred.confidence,
    }}


def _intent_team_compare(db: Session, text: str) -> dict | None:
    """X vs Y comparison."""
    if not re.search(r"\b(vs|versus|against|compared)\b", text, re.I):
        return None
    # Find two teams
    teams_found = []
    for word, full in _TEAM_WORDS.items():
        if word in text.lower() and full not in teams_found:
            teams_found.append(full)
        if len(teams_found) >= 2:
            break
    if len(teams_found) < 2:
        return None
    a, b = teams_found[0], teams_found[1]
    pred = (
        db.query(GamePrediction)
        .filter(GamePrediction.game_date == date.today())
        .filter(((GamePrediction.home_team == a) & (GamePrediction.away_team == b)) |
                ((GamePrediction.home_team == b) & (GamePrediction.away_team == a)))
        .first()
    )
    if not pred:
        return {"intent": "team_compare",
                "answer": f"{a} and {b} aren't playing each other today.", "data": None}
    fav = pred.home_team if pred.home_win_prob > 0.5 else pred.away_team
    fav_prob = max(pred.home_win_prob, 1 - pred.home_win_prob)
    answer = (
        f"**{fav}** is favored ({fav_prob*100:.1f}%) in {pred.away_team} @ {pred.home_team}. "
        f"Predicted: {pred.pred_home_score:.1f}–{pred.pred_away_score:.1f}, "
        f"total {pred.pred_total:.1f}."
    )
    return {"intent": "team_compare", "answer": answer, "data": None}


def _intent_safest_pick(db: Session, text: str) -> dict | None:
    if not re.search(r"\b(safe|safest|lock|surest|highest\s+rated)\b", text, re.I):
        return None
    sport = _detect_sport(text)
    q = db.query(Pick).filter(Pick.pick_date == date.today())
    if sport:
        q = q.filter(Pick.sport == sport)
    p = q.order_by(Pick.rating.desc()).first()
    if not p:
        return {"intent": "safest", "answer": "No picks generated yet today.", "data": None}
    answer = (
        f"Safest play today: **{p.player_name}** ({p.team or '?'}) "
        f"{p.side.upper()} {p.line} {p.market} ({p.price_american:+d}) — "
        f"rating {p.rating:.0f}/100, model {p.model_prob*100:.1f}%, edge {p.edge_pct:+.1f}%."
    )
    return {"intent": "safest", "answer": answer, "data": None}


def _intent_parlay(db: Session, text: str) -> dict | None:
    if not re.search(r"\b(parlay|slip|sgp|combo|combine)\b", text, re.I):
        return None
    from .recommended_slips import generate_recommended_slips
    slips = generate_recommended_slips(db, on=date.today())
    if not slips:
        return {"intent": "parlay", "answer": "No recommended slips yet today.", "data": None}
    parts = []
    for s in slips[:3]:
        legs_text = " · ".join(
            f"{l['player_name']} {l['side']} {l['line']}" for l in s["legs"][:5]
        )
        parts.append(
            f"**{s['label']}** ({fmt := s['combined_american_odds']:+d}, "
            f"model {s['combined_model_prob']*100:.1f}%): {legs_text}"
        )
    return {"intent": "parlay", "answer": "Today's recommended slips:\n" + "\n".join(parts), "data": slips}


def _intent_help(db: Session, text: str) -> dict | None:
    if not re.search(r"^\s*(help|what can you|examples?|how to)", text, re.I):
        return None
    answer = (
        "I can answer:\n"
        "• Game outcomes — *will the Lakers win tonight?*\n"
        "• Best picks — *best NBA pick today*, *safest play*\n"
        "• Player form — *how is Judge hitting lately?*\n"
        "• Player props — *LeBron over 25 points*\n"
        "• Totals — *Lakers total points tonight*\n"
        "• Comparisons — *Yankees vs Red Sox*\n"
        "• Parlays — *recommended parlay today*\n"
        "• Low-prob — *what team won't hit a home run?*\n"
        "Set GROQ_API_KEY for unlimited free general sports Q&A via Llama 3.3."
    )
    return {"intent": "help", "answer": answer, "data": None}


INTENT_HANDLERS = [
    _intent_help,
    _intent_low_prob_market,
    _intent_biggest_favorite,
    _intent_safest_pick,
    _intent_parlay,
    _intent_top_picks,
    _intent_player_form,
    _intent_team_compare,
    _intent_total_spread,
    _intent_game_winner,
    _intent_player_prop,
]


def ask(db: Session, question: str) -> dict:
    """Route a question to the first matching intent handler."""
    if not question or not question.strip():
        return {"intent": "empty", "answer": "Ask a question — e.g., 'will the Lakers win tonight?'", "data": None}
    for handler in INTENT_HANDLERS:
        try:
            result = handler(db, question)
            if result:
                return result
        except Exception as e:
            continue
    return {
        "intent": "unrecognized",
        "answer": (
            "Couldn't match that to a question I know. Try: "
            "'will the Lakers win tonight?', 'best NBA pick today', "
            "'how is Judge hitting lately?', or 'LeBron over 25 points'."
        ),
        "data": None,
    }
