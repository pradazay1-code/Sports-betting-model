"""Deep bet-analysis grading engine.

Give it a single bet or a multi-leg slip and it returns a **letter grade**
(A+ … F) plus a structured, human-readable breakdown: the model's probability,
the no-vig fair probability, EV edge, projected stat value vs. the posted line,
recent form (last 5 / 10 / 25 games), Kelly stake, and an itemised list of
strengths and concerns.

It reuses the exact same modelling stack as the picks generator
(`prop_model` + `features` + `ev`) so a grade for a bet you type in is fully
consistent with the auto-generated picks on the dashboard.

CLI:
    python -m app.analysis '{"sport":"NBA","player_name":"Nikola Jokic",
        "market":"player_points","side":"over","line":24.5,"price_american":-115}'

    python -m app.analysis '[{...leg...}, {...leg...}]'   # parlay
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field

from app.betslip import Leg, analyze
from app.ev import kelly_fraction, price as price_one, rating
from app.features import build_inference_features
from app.models import prop_model
from app.utils import american_to_decimal, get_logger, today_local

LOG = get_logger("analysis")

# Ordered worst -> best so we can take min() of two grade ceilings.
GRADES = ["F", "D-", "D", "D+", "C-", "C", "C+", "B-", "B", "B+", "A-", "A", "A+"]

# rating (0..100) -> base grade index. Generous at the top because the
# rating function is deliberately conservative.
_RATING_BANDS = [
    (90, "A+"), (84, "A"), (78, "A-"), (72, "B+"), (66, "B"), (60, "B-"),
    (54, "C+"), (48, "C"), (42, "C-"), (36, "D+"), (30, "D"), (24, "D-"),
]


def _grade_index(letter: str) -> int:
    return GRADES.index(letter)


def _letter_from(rating_value: float, edge_pct: float) -> str:
    """Blend the 0-100 rating with the EV edge sign into a letter grade.

    A bet can never grade above a ceiling set by its edge: you do not get an
    A on a play the model thinks is -EV, no matter how 'confident' it looks.
    """
    base = "F"
    for threshold, letter in _RATING_BANDS:
        if rating_value >= threshold:
            base = letter
            break

    if edge_pct <= -5.0:
        ceiling = "D-"
    elif edge_pct < 0.0:
        ceiling = "C-"
    elif edge_pct < 1.0:
        ceiling = "B-"
    elif edge_pct < 3.0:
        ceiling = "A-"
    else:
        ceiling = "A+"

    return GRADES[min(_grade_index(base), _grade_index(ceiling))]


@dataclass
class BetGrade:
    sport: str
    player_name: str
    market: str
    side: str
    line: float
    price_american: int
    grade: str
    score: float                 # 0..100 rating
    modeled: bool                # was a trained model available for this player?
    model_prob: float
    fair_prob: float
    edge_pct: float
    kelly_stake: float
    projection: float | None     # model's projected stat value
    margin: float | None         # projection - line (signed toward the bet side)
    recent_form: dict = field(default_factory=dict)
    strengths: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    summary: str = ""


def _recent_form(feats: dict | None) -> dict:
    if not feats:
        return {}
    keys = {
        "last5_avg": "r5_mean", "last10_avg": "r10_mean", "last25_avg": "r25_mean",
        "season_avg": "season_avg", "volatility": "r10_std",
        "games_sampled": "n_games", "days_rest": "days_rest",
        "opp_allowed_avg": "opp_allowed",
    }
    out = {}
    for label, col in keys.items():
        v = feats.get(col)
        if v is not None:
            out[label] = round(float(v), 2)
    return out


def grade_single(leg: Leg | dict, on_date: str | None = None) -> BetGrade:
    if isinstance(leg, dict):
        leg = Leg(**{k: leg[k] for k in (
            "sport", "player_name", "market", "line", "side", "price_american")
            if k in leg}, **{k: leg.get(k) for k in ("game_id", "team", "opp_team")})
    on_date = on_date or today_local().isoformat()

    dec = american_to_decimal(leg.price_american)
    implied = 1.0 / dec

    tm = prop_model.load(leg.sport, leg.market)
    feats = build_inference_features(
        leg.sport, leg.market, leg.player_name, on_date, opp_team=leg.opp_team)

    modeled = tm is not None and feats is not None
    projection = None
    if modeled:
        p_over = tm.prob_over(feats, float(leg.line))
        model_prob = p_over if leg.side == "over" else 1.0 - p_over
        projection = round(tm.predict_mean(feats), 2)
    else:
        # No model/history for this player — fall back to the book's own
        # implied probability so the bet still grades (neutrally).
        model_prob = implied

    fair_prob = implied  # single-sided input: best available no-vig proxy
    priced = price_one(leg.side, model_prob, fair_prob, leg.price_american)
    n_train = tm.n_train if modeled else 0
    score, parts = rating(
        edge_pct=priced.edge_pct, model_prob=model_prob, fair_prob=fair_prob,
        n_train_rows=n_train, n_books=1)
    letter = _letter_from(score, priced.edge_pct)

    form = _recent_form(feats)
    margin = None
    if projection is not None:
        margin = round((projection - leg.line) * (1 if leg.side == "over" else -1), 2)

    strengths, concerns = _narrate(
        leg, modeled, model_prob, priced.edge_pct, parts, form, margin, n_train)

    summary = _summary(letter, leg, priced.edge_pct, modeled)

    return BetGrade(
        sport=leg.sport, player_name=leg.player_name, market=leg.market,
        side=leg.side, line=float(leg.line), price_american=int(leg.price_american),
        grade=letter, score=round(score, 1), modeled=modeled,
        model_prob=round(model_prob, 4), fair_prob=round(fair_prob, 4),
        edge_pct=round(priced.edge_pct, 2),
        kelly_stake=round(kelly_fraction(model_prob, leg.price_american), 4),
        projection=projection, margin=margin, recent_form=form,
        strengths=strengths, concerns=concerns, summary=summary,
    )


def _narrate(leg, modeled, model_prob, edge_pct, parts, form, margin, n_train):
    strengths: list[str] = []
    concerns: list[str] = []

    if not modeled:
        concerns.append(
            "No trained model or game history for this player/market — graded "
            "off the book's implied price only, so treat it as un-vetted.")
        return strengths, concerns

    if edge_pct >= 5:
        strengths.append(f"Large model edge of {edge_pct:.1f}% over the posted price.")
    elif edge_pct >= 1.5:
        strengths.append(f"Positive expected value (+{edge_pct:.1f}% edge).")
    elif edge_pct >= 0:
        concerns.append(f"Thin edge (+{edge_pct:.1f}%) — barely beats the vig.")
    else:
        concerns.append(f"Negative expected value ({edge_pct:.1f}%) at this price.")

    if margin is not None:
        if margin >= 0:
            strengths.append(
                f"Projection clears the line by {abs(margin):.1f} in the bet's favor "
                f"({leg.side} {leg.line}).")
        else:
            concerns.append(
                f"Projection sits {abs(margin):.1f} on the wrong side of the line.")

    conf = parts.get("confidence", 0.0)
    if conf >= 0.6:
        strengths.append(f"Model is confident ({model_prob*100:.0f}% to hit).")
    elif model_prob < 0.5:
        concerns.append(f"Model gives this under a coin-flip ({model_prob*100:.0f}%).")

    vol = form.get("volatility")
    l10 = form.get("last10_avg")
    if vol is not None and l10:
        cv = vol / max(abs(l10), 1e-6)
        if cv >= 0.6:
            concerns.append(
                f"High game-to-game volatility (σ≈{vol:.1f} on a {l10:.1f} average).")
        elif cv <= 0.3:
            strengths.append(f"Stable recent production (σ≈{vol:.1f}, avg {l10:.1f}).")

    l5, l25 = form.get("last5_avg"), form.get("last25_avg")
    if l5 is not None and l25:
        if l5 >= l25 * 1.12:
            strengths.append(f"Trending up: last-5 avg {l5:.1f} vs last-25 {l25:.1f}.")
        elif l5 <= l25 * 0.88:
            concerns.append(f"Cooling off: last-5 avg {l5:.1f} vs last-25 {l25:.1f}.")

    if n_train < 400:
        concerns.append(f"Small training sample ({n_train} rows) for this market.")
    elif n_train >= 1500:
        strengths.append(f"Deep training sample ({n_train} rows).")

    return strengths, concerns


def _summary(letter: str, leg, edge_pct: float, modeled: bool) -> str:
    side = leg.side.upper()
    if not modeled:
        return (f"Grade {letter}: {leg.player_name} {side} {leg.line} could not be "
                f"independently modeled; no recommendation.")
    if letter[0] in ("A", "B") and edge_pct > 0:
        verb = "A strong play" if letter[0] == "A" else "A solid play"
        return (f"Grade {letter}: {verb}. {leg.player_name} {side} {leg.line} "
                f"carries a +{edge_pct:.1f}% model edge.")
    if letter[0] == "C":
        return (f"Grade {letter}: Marginal. {leg.player_name} {side} {leg.line} "
                f"is roughly fair value — pass unless you love the spot.")
    return (f"Grade {letter}: Avoid. {leg.player_name} {side} {leg.line} grades as "
            f"{edge_pct:.1f}% EV against you.")


# --- parlay grading -------------------------------------------------------


def grade_slip(legs: list[Leg | dict], on_date: str | None = None) -> dict:
    """Grade a multi-leg slip: per-leg grades plus an overall parlay grade that
    accounts for same-game correlation (via app.betslip.analyze)."""
    on_date = on_date or today_local().isoformat()
    norm_legs = [_as_leg(l) for l in legs]

    leg_grades = [grade_single(l, on_date) for l in norm_legs]
    slip = analyze(norm_legs, on_date)

    # Overall parlay grade: drive a synthetic rating off the parlay edge and
    # the weakest leg, then letter it. A chain is only as trustworthy as its
    # shakiest link.
    weakest = min((g.score for g in leg_grades), default=0.0)
    n_unmodeled = sum(1 for g in leg_grades if not g.modeled)
    parlay_rating = max(0.0, min(100.0,
        0.55 * _edge_to_score(slip.parlay_edge_pct) + 0.45 * weakest
        - 8.0 * n_unmodeled))
    parlay_grade = _letter_from(parlay_rating, slip.parlay_edge_pct)

    return {
        "on_date": on_date,
        "n_legs": len(norm_legs),
        "legs": [asdict(g) for g in leg_grades],
        "parlay": {
            "grade": parlay_grade,
            "score": round(parlay_rating, 1),
            "decimal": round(slip.parlay_decimal, 3),
            "american": slip.parlay_american,
            "naive_prob": round(slip.naive_model_prob, 4),
            "correlated_prob": round(slip.correlated_model_prob, 4),
            "edge_pct": round(slip.parlay_edge_pct, 2),
            "verdict": slip.verdict,
            "weakest_leg_score": round(weakest, 1),
            "unmodeled_legs": n_unmodeled,
            "summary": _slip_summary(parlay_grade, len(norm_legs),
                                     slip.parlay_edge_pct, n_unmodeled),
        },
    }


def _edge_to_score(edge_pct: float) -> float:
    # Map parlay edge% to a 0..100 scale (15%+ edge tops it out).
    return max(0.0, min(100.0, 50.0 + edge_pct * (50.0 / 15.0)))


def _slip_summary(grade: str, n: int, edge: float, unmodeled: int) -> str:
    head = f"Grade {grade}: {n}-leg parlay"
    if unmodeled:
        head += f" ({unmodeled} leg(s) un-modeled)"
    if edge >= 5:
        return f"{head} with a strong +{edge:.1f}% correlation-adjusted edge."
    if edge >= 0:
        return f"{head} at +{edge:.1f}% edge — playable but variance is high."
    return f"{head} grading {edge:.1f}% against you; the math says pass."


def _as_leg(l: Leg | dict) -> Leg:
    if isinstance(l, Leg):
        return l
    return Leg(
        sport=l["sport"], player_name=l["player_name"], market=l["market"],
        line=float(l["line"]), side=l["side"], price_american=int(l["price_american"]),
        game_id=l.get("game_id"), team=l.get("team"), opp_team=l.get("opp_team"))


def grade(payload: list | dict, on_date: str | None = None) -> dict:
    """Top-level entry: a dict grades a single bet, a list grades a parlay."""
    if isinstance(payload, dict):
        return asdict(grade_single(payload, on_date))
    return grade_slip(payload, on_date)


if __name__ == "__main__":
    raw = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    data = json.loads(raw)
    print(json.dumps(grade(data), indent=2, default=str))
