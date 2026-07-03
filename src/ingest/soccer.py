"""Soccer / World Cup ingest — football-data.org + Understat/FBref rates (spec §2.2).

World Cup weighting is the heart of it: international form != club form.
Blend = club underlying numbers 60% / international last-10 30% /
tournament context 10%. Books grade props on 90 minutes — everything here
models 90', never 120'.
"""

from __future__ import annotations

import json
import os

import requests

from src import config, db

FD_BASE = "https://api.football-data.org/v4"
WC_BLEND = {"club": 0.60, "intl": 0.30, "tournament": 0.10}
RATE_COLS = ("shots_p90", "sot_p90", "xg_p90", "xa_p90", "fouls_p90")


def parse_matches(payload: dict) -> list[dict]:
    """football-data.org /competitions/{code}/matches response."""
    out = []
    for m in payload.get("matches", []):
        refs = m.get("referees") or []
        out.append({
            "match_id": str(m.get("id")),
            "utc_date": m.get("utcDate"),
            "competition": (m.get("competition") or {}).get("name"),
            "stage": m.get("stage"),
            "home_team": (m.get("homeTeam") or {}).get("name"),
            "away_team": (m.get("awayTeam") or {}).get("name"),
            "status": m.get("status"),
            "referee": refs[0].get("name") if refs else None,
        })
    return out


def store_matches(conn, matches: list[dict]) -> int:
    now = db.utcnow()
    conn.executemany(
        """INSERT OR REPLACE INTO soccer_matches VALUES
           (:match_id, :utc_date, :competition, :stage, :home_team, :away_team,
            :status, :referee, :fetched_at)""",
        [{**m, "fetched_at": now} for m in matches])
    conn.commit()
    return len(matches)


def pull_competition_matches(conn, code: str = "WC") -> int:
    key = os.environ.get(config.sources()["stats"]["soccer"]["api_key_env"], "")
    if not key:
        return 0
    try:
        resp = requests.get(f"{FD_BASE}/competitions/{code}/matches",
                            headers={"X-Auth-Token": key},
                            timeout=config.sources()["http"]["timeout_seconds"])
        if resp.status_code != 200:
            return 0
    except requests.RequestException:
        return 0
    pulled_at = db.utcnow()
    day_dir = config.raw_dir() / "soccer" / pulled_at[:10]
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / f"matches_{code}.json").write_text(json.dumps(resp.json()))
    return store_matches(conn, parse_matches(resp.json()))


# ------------------------------------------------------------- player rates

def store_player_rates(conn, rows: list[dict]) -> int:
    """rows: player/team/context/season + per-90 rates (from FBref/Understat
    scrapes or manual research sheets — every row carries fetched_at)."""
    now = db.utcnow()
    conn.executemany(
        """INSERT OR REPLACE INTO soccer_player_rates VALUES
           (:player, :team, :context, :season, :minutes, :shots_p90, :sot_p90,
            :xg_p90, :xa_p90, :fouls_p90, :penalty_duty, :fetched_at)""",
        [{"penalty_duty": 0, **r, "fetched_at": now} for r in rows])
    conn.commit()
    return len(rows)


def player_rates(conn, player: str, season: str) -> dict[str, dict]:
    """context -> rates row for one player."""
    rows = conn.execute(
        "SELECT * FROM soccer_player_rates WHERE player = ? AND season = ?",
        (player, season)).fetchall()
    return {r["context"]: dict(r) for r in rows}


def wc_blended_rates(rates_by_context: dict[str, dict]) -> dict | None:
    """60/30/10 club/intl/tournament blend; renormalizes over what exists.

    Tournament rows with tiny minutes (< 90) are ignored — one sub
    appearance is noise, not signal.
    """
    usable = {
        ctx: r for ctx, r in rates_by_context.items()
        if ctx in WC_BLEND and not (ctx == "tournament" and (r.get("minutes") or 0) < 90)
    }
    if "club" not in usable:
        return None            # club underlying numbers are the anchor (spec §2.2)
    total_w = sum(WC_BLEND[c] for c in usable)
    blended = {"player": usable["club"]["player"], "contexts_used": sorted(usable)}
    for col in RATE_COLS:
        vals = [(WC_BLEND[c] / total_w, r[col]) for c, r in usable.items()
                if r.get(col) is not None]
        blended[col] = round(sum(w * v for w, v in vals), 4) if vals else None
    blended["penalty_duty"] = max(int(r.get("penalty_duty") or 0) for r in usable.values())
    return blended


def rotation_risk(stage: str | None, qualification_locked: bool) -> bool:
    """The #1 WC prop trap: group-stage game 3 with qualification locked."""
    return bool(stage and "GROUP" in stage.upper() and qualification_locked)
