"""LLM-augmented Q&A. If GROQ_API_KEY or OPENAI_API_KEY is set in env,
route hard questions through a hosted LLM with Pradapicks data injected
as context. Otherwise fall back to the rule-based intent router.

Why both? Groq's free tier is generous (30 req/min Llama 3.3) and gives
the AI Chat tab the ability to handle ANY sports question. The rule
system stays as offline fallback so the app works without keys.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date

import httpx
from sqlalchemy.orm import Session

from ..db import GamePrediction, Pick, Player
from .qa import ask as rule_ask

log = logging.getLogger(__name__)


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def _get_llm_config() -> tuple[str, str, str] | None:
    """Returns (url, model, api_key) for whichever provider has a key set."""
    groq = os.environ.get("GROQ_API_KEY")
    if groq:
        return GROQ_URL, os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"), groq
    openai = os.environ.get("OPENAI_API_KEY")
    if openai:
        return OPENAI_URL, os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), openai
    return None


def _build_context(db: Session, question: str) -> str:
    """Build a compact context blob — today's picks, predictions, and
    relevant rosters — for the LLM to ground its answer in."""
    today = date.today()
    picks = (
        db.query(Pick).filter(Pick.pick_date == today)
        .order_by(Pick.rating.desc()).limit(15).all()
    )
    games = (
        db.query(GamePrediction).filter(GamePrediction.game_date == today)
        .order_by(GamePrediction.confidence.desc()).limit(20).all()
    )
    parts = [f"Today is {today.isoformat()}."]
    if games:
        parts.append("Today's game predictions:")
        for g in games:
            parts.append(
                f"  {g.sport}: {g.away_team} @ {g.home_team} — predicted score "
                f"{g.pred_home_score:.1f}-{g.pred_away_score:.1f}, "
                f"home win prob {g.home_win_prob*100:.1f}%, "
                f"total {g.pred_total:.1f}, spread {g.pred_spread:+.1f}, "
                f"confidence {g.confidence*100:.0f}%."
            )
    if picks:
        parts.append("Today's top model picks:")
        for p in picks[:10]:
            parts.append(
                f"  {p.sport}: {p.player_name} ({p.team or '?'}) — "
                f"{p.side.upper()} {p.line} {p.market} @ {p.price_american:+d}, "
                f"rating {p.rating:.0f}/100, edge {p.edge_pct:+.1f}%, "
                f"model prob {p.model_prob*100:.1f}%."
            )

    # If the question mentions a specific player, attach their recent stats.
    from .qa import _detect_player, _detect_sport
    sport = _detect_sport(question)
    player = _detect_player(db, question, sport)
    if player:
        from .players import player_detail
        d = player_detail(db, player.sport, player.external_id, last_n=10)
        agg = d.get("aggregates") or {}
        if agg:
            parts.append(f"Recent form for {player.name} ({player.sport}, {player.team or '?'}):")
            for stat, a in list(agg.items())[:6]:
                parts.append(
                    f"  {stat}: season avg {a['avg']}, L5 {a['last5_avg']}, "
                    f"L10 {a['last10_avg']}, max {a['max']}"
                )
    return "\n".join(parts)


SYSTEM_PROMPT = (
    "You are Pradapicks, an expert AI sports-betting analyst covering MLB, NBA, "
    "and NHL. You receive a structured context blob with today's model picks, "
    "game predictions, and relevant player stats. Answer the user's question "
    "directly and concisely. Cite specific numbers from the context. If the "
    "context doesn't cover the question, say what's missing rather than "
    "inventing data. Keep answers under 200 words. Use **bold** for key picks. "
    "Never recommend illegal betting; you provide analysis only."
)


def ask_llm(db: Session, question: str) -> dict:
    """Route through LLM if a key is configured, else fall back to rules."""
    cfg = _get_llm_config()
    if not cfg:
        # Fall back to rule-based and tag it
        result = rule_ask(db, question)
        result["llm_used"] = False
        return result

    url, model, key = cfg
    context = _build_context(db, question)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}"},
        ],
        "temperature": 0.3,
        "max_tokens": 600,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    try:
        r = httpx.post(url, json=payload, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()
        answer = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        return {
            "intent": "llm",
            "answer": answer.strip() or "(empty answer from LLM)",
            "data": None,
            "llm_used": True,
            "llm_model": model,
        }
    except Exception as e:
        log.warning("LLM call failed, falling back to rules: %s", e)
        result = rule_ask(db, question)
        result["llm_used"] = False
        result["llm_error"] = str(e)
        return result
