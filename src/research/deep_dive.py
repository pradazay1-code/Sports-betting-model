"""Claude-driven research pass for every EV > 6% pick (spec §4).

The model finds candidates; research validates them; only validated
edges get full bet sizing. Flow:

1. `generate_briefs` writes a research brief per flagged pick (48h news
   sweep targets, the model's key assumption to verify, kill-switch
   questions) to data/research/<date>/.
2. The research pass runs either via the Claude API (ANTHROPIC_API_KEY set:
   web-search-enabled request per brief) or by Claude Code working the
   brief files directly.
3. `attach_memo` records the 3-5 sentence memo + verdict. Any kill-switch
   YES demotes the pick to NO PLAY regardless of model EV; VALIDATED
   restores full tier sizing.

    python -m src.research.deep_dive --generate
    python -m src.research.deep_dive --validate PICK_ID --memo "..." [--kill]
"""

from __future__ import annotations

import argparse
import json
import os

from src import config, db

KILL_SWITCH_QUESTIONS = [
    "Is there a lineup change the model missed?",
    "Is there a pitch-count or innings limit today?",
    "Is there a minutes restriction or planned rest?",
    "Is there a new starting goalkeeper / backup catcher situation?",
    "Is this a locked-qualification rotation spot (soccer game 3 trap)?",
]


def build_brief(pick: dict) -> dict:
    who = pick["player"] or f"{pick['market']} market"
    return {
        "pick_id": pick["pick_id"],
        "pick": f"{who} {pick['side']} {pick['line']} {pick['market']} "
                f"@ {pick['odds_american']} ({pick['book']})",
        "model_prob": pick["model_prob"],
        "market_fair_prob": pick["market_fair_prob"],
        "ev_pct": pick["ev_pct"],
        "model_inputs": pick.get("notes"),
        "search_queries": [
            f"{who} news last 48 hours",
            f"{who} injury status lineup",
            f"{who} coach quotes role minutes",
        ],
        "key_assumption": (
            "The market prices this at "
            f"{pick['market_fair_prob']:.1%} fair; the model says {pick['model_prob']:.1%}. "
            "The market is usually right — find the reason the market disagrees, "
            "or the story the market missed. If you cannot find why, assume the "
            "model is missing something."),
        "kill_switch_questions": KILL_SWITCH_QUESTIONS,
        "required_output": "3-5 sentence memo with sources and timestamps, "
                           "then verdict: VALIDATED or KILL.",
    }


def generate_briefs(conn, day: str) -> list[str]:
    """Write one brief file per research-flagged pending pick."""
    picks = conn.execute(
        """SELECT * FROM picks WHERE needs_research = 1 AND research_memo IS NULL
           AND status = 'pending' AND date(created_at) = date(?)""", (day,)).fetchall()
    out_dir = config.REPO_ROOT / "data" / "research" / day
    paths = []
    for p in picks:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"pick_{p['pick_id']}.json"
        path.write_text(json.dumps(build_brief(dict(p)), indent=2))
        paths.append(str(path))
    return paths


def attach_memo(conn, pick_id: int, memo: str, validated: bool,
                kill_switch_hit: bool = False) -> str:
    """Record the research result. KILL -> NO PLAY, stake zeroed (spec §4.3)."""
    if kill_switch_hit or not validated:
        conn.execute(
            """UPDATE picks SET research_memo = ?, status = 'no_play', tier = NULL,
               stake_units = 0 WHERE pick_id = ?""",
            (memo + " [KILL-SWITCH]" if kill_switch_hit else memo, pick_id))
        conn.commit()
        return "no_play"
    # validated: lift the C-tier research cap back to the pick's tier sizing
    p = conn.execute("SELECT * FROM picks WHERE pick_id = ?", (pick_id,)).fetchone()
    from src.engine import staking
    tiers = config.settings()["tiers"]
    mult = tiers[p["tier"]]["stake_multiplier"] if p["tier"] else 0.0
    frac = staking.stake_fraction(p["model_prob"], p["odds_decimal"], mult)
    conn.execute(
        "UPDATE picks SET research_memo = ?, stake_units = ? WHERE pick_id = ?",
        (memo, round(frac * 100.0, 2), pick_id))
    conn.commit()
    return "validated"


# --------------------------------------------------- Claude API research run

def research_via_api(brief: dict) -> dict | None:
    """One web-search-enabled Claude request per brief. Needs ANTHROPIC_API_KEY."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    import requests
    prompt = (
        "You are the research desk for a sports betting model. Work this brief:\n\n"
        + json.dumps(brief, indent=2)
        + "\n\nSearch the web for the last 48 hours of news. Answer every "
          "kill-switch question explicitly. Reply with JSON only: "
          '{"memo": "3-5 sentences with sources+timestamps", '
          '"kill_switch_hit": bool, "validated": bool}'
    )
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": os.environ.get("RESEARCH_MODEL", "claude-sonnet-5"),
                  "max_tokens": 1500,
                  "tools": [{"type": "web_search_20250305", "name": "web_search",
                             "max_uses": 5}],
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=120)
        if resp.status_code != 200:
            return None
        text = "".join(b.get("text", "") for b in resp.json().get("content", [])
                       if b.get("type") == "text")
        start, end = text.find("{"), text.rfind("}")
        return json.loads(text[start:end + 1]) if start >= 0 else None
    except Exception:
        return None


def run_research(conn, day: str) -> dict:
    """Generate briefs and, when the API is available, work them end-to-end."""
    paths = generate_briefs(conn, day)
    results = {"briefs": len(paths), "validated": 0, "killed": 0, "pending": 0}
    for path in paths:
        brief = json.loads(open(path).read())
        verdict = research_via_api(brief)
        if verdict is None:
            results["pending"] += 1     # brief awaits a manual/Claude Code pass
            continue
        status = attach_memo(conn, brief["pick_id"], verdict.get("memo", ""),
                             validated=bool(verdict.get("validated")),
                             kill_switch_hit=bool(verdict.get("kill_switch_hit")))
        results["validated" if status == "validated" else "killed"] += 1
    return results


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--generate", action="store_true")
    ap.add_argument("--run", action="store_true", help="generate + API research pass")
    ap.add_argument("--validate", type=int, metavar="PICK_ID")
    ap.add_argument("--memo", default="")
    ap.add_argument("--kill", action="store_true")
    ap.add_argument("--date")
    args = ap.parse_args(argv)
    from datetime import date
    day = args.date or date.today().isoformat()
    conn = db.connect()
    if args.generate:
        for p in generate_briefs(conn, day):
            print(p)
    if args.run:
        print(run_research(conn, day))
    if args.validate:
        print(attach_memo(conn, args.validate, args.memo,
                          validated=not args.kill, kill_switch_hit=args.kill))
    conn.close()


if __name__ == "__main__":
    main()
