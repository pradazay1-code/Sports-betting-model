"""MLB stats ingest — statsapi.mlb.com (free, official, no key) (spec §2.2).

Pulls schedules with probable pitchers, pitcher game logs (Ks, batters
faced, pitch counts), and team K rates vs pitcher handedness. Every raw
response is cached to data/raw/mlb/ with a timestamp (honesty layer §0.4).

Parsers are pure functions so they are unit-testable without network.
"""

from __future__ import annotations

import json
from datetime import date as date_cls

import requests

from src import config, db

BASE = "https://statsapi.mlb.com/api/v1"

# Park run factors, hardcoded per spec §2.2 (update yearly; 1.0 = neutral).
PARK_FACTORS = {
    "Coors Field": 1.28, "Fenway Park": 1.09, "Great American Ball Park": 1.09,
    "Yankee Stadium": 1.05, "Citizens Bank Park": 1.05, "Wrigley Field": 1.03,
    "Chase Field": 1.03, "Globe Life Field": 1.02, "Truist Park": 1.01,
    "Camden Yards": 1.00, "Angel Stadium": 1.00, "Rogers Centre": 1.00,
    "Target Field": 0.99, "Busch Stadium": 0.98, "Dodger Stadium": 0.98,
    "Comerica Park": 0.98, "Kauffman Stadium": 0.98, "PNC Park": 0.97,
    "Nationals Park": 0.97, "American Family Field": 0.97, "Minute Maid Park": 0.97,
    "Progressive Field": 0.96, "Guaranteed Rate Field": 0.96, "Citi Field": 0.95,
    "Oracle Park": 0.94, "Oakland Coliseum": 0.93, "loanDepot park": 0.92,
    "Petco Park": 0.92, "T-Mobile Park": 0.91, "Tropicana Field": 0.94,
}


def _get(path: str, **params) -> dict | None:
    http = config.sources()["http"]
    try:
        resp = requests.get(f"{BASE}{path}", params=params,
                            timeout=http["timeout_seconds"])
        if resp.status_code == 200:
            return resp.json()
    except requests.RequestException:
        pass
    return None


def _cache_raw(payload: dict, label: str, pulled_at: str) -> str:
    day_dir = config.raw_dir() / "mlb" / pulled_at[:10]
    day_dir.mkdir(parents=True, exist_ok=True)
    out = day_dir / f"{pulled_at.replace(':', '').replace('-', '')}_{label}.json"
    out.write_text(json.dumps(payload, indent=1))
    return str(out.relative_to(config.REPO_ROOT))


# ------------------------------------------------------------------ parsers

def ip_to_outs(ip: str | float | None) -> int | None:
    """MLB innings notation: '6.2' = 6 innings + 2 outs = 20 outs."""
    if ip is None:
        return None
    whole, _, frac = str(ip).partition(".")
    return int(whole) * 3 + (int(frac) if frac else 0)


def parse_schedule(payload: dict) -> list[dict]:
    games = []
    for day in payload.get("dates", []):
        for g in day.get("games", []):
            teams = g.get("teams", {})
            home, away = teams.get("home", {}), teams.get("away", {})
            games.append({
                "game_pk": g["gamePk"],
                "game_date": day.get("date"),
                "commence_time": g.get("gameDate"),
                "home_team_id": home.get("team", {}).get("id"),
                "home_team": home.get("team", {}).get("name"),
                "away_team_id": away.get("team", {}).get("id"),
                "away_team": away.get("team", {}).get("name"),
                "home_probable_id": (home.get("probablePitcher") or {}).get("id"),
                "home_probable": (home.get("probablePitcher") or {}).get("fullName"),
                "away_probable_id": (away.get("probablePitcher") or {}).get("id"),
                "away_probable": (away.get("probablePitcher") or {}).get("fullName"),
                "venue": (g.get("venue") or {}).get("name"),
                "state": (g.get("status") or {}).get("abstractGameState"),
            })
    return games


def parse_pitcher_gamelog(payload: dict, player_id: int) -> list[dict]:
    """Game log splits -> rows, most recent LAST (chronological)."""
    rows = []
    for group in payload.get("stats", []):
        for split in group.get("splits", []):
            stat = split.get("stat", {})
            rows.append({
                "player_id": player_id,
                "player_name": (split.get("player") or {}).get("fullName"),
                "game_date": split.get("date"),
                "opponent": (split.get("opponent") or {}).get("name"),
                "innings_outs": ip_to_outs(stat.get("inningsPitched")),
                "batters_faced": stat.get("battersFaced"),
                "strikeouts": stat.get("strikeOuts"),
                "pitches": stat.get("numberOfPitches") or stat.get("pitchesThrown"),
                "hand": ((split.get("player") or {}).get("pitchHand") or {}).get("code"),
            })
    rows.sort(key=lambda r: r["game_date"] or "")
    return rows


def parse_team_splits(payload: dict, team_id: int, season: int) -> list[dict]:
    """statSplits (sitCodes vl/vr) -> K rate vs L / vs R."""
    out = []
    code_map = {"vl": "L", "vr": "R"}
    for group in payload.get("stats", []):
        for split in group.get("splits", []):
            code = (split.get("split") or {}).get("code")
            stat = split.get("stat", {})
            pa, so = stat.get("plateAppearances"), stat.get("strikeOuts")
            if code in code_map and pa:
                out.append({
                    "team_id": team_id,
                    "team_name": (split.get("team") or {}).get("name"),
                    "season": season,
                    "vs_hand": code_map[code],
                    "pa": pa, "so": so,
                    "k_rate": round(so / pa, 5),
                })
    return out


# ------------------------------------------------------------------ storage

def store_games(conn, games: list[dict]) -> int:
    now = db.utcnow()
    conn.executemany(
        """INSERT INTO mlb_games VALUES
           (:game_pk, :game_date, :commence_time, :home_team_id, :home_team,
            :away_team_id, :away_team, :home_probable_id, :home_probable,
            :away_probable_id, :away_probable, :venue, :state, :fetched_at)
           ON CONFLICT (game_pk) DO UPDATE SET
            home_probable_id=excluded.home_probable_id, home_probable=excluded.home_probable,
            away_probable_id=excluded.away_probable_id, away_probable=excluded.away_probable,
            state=excluded.state, fetched_at=excluded.fetched_at""",
        [{**g, "fetched_at": now} for g in games])
    conn.commit()
    return len(games)


def store_pitcher_logs(conn, rows: list[dict]) -> int:
    now = db.utcnow()
    before = conn.total_changes
    conn.executemany(
        """INSERT INTO mlb_pitcher_logs
           (player_id, player_name, game_date, opponent, innings_outs,
            batters_faced, strikeouts, pitches, hand, fetched_at)
           VALUES (:player_id, :player_name, :game_date, :opponent, :innings_outs,
                   :batters_faced, :strikeouts, :pitches, :hand, :fetched_at)
           ON CONFLICT (player_id, game_date) DO UPDATE SET
            strikeouts=excluded.strikeouts, batters_faced=excluded.batters_faced,
            pitches=excluded.pitches, fetched_at=excluded.fetched_at""",
        [{**r, "fetched_at": now} for r in rows])
    conn.commit()
    return conn.total_changes - before


def store_team_batting(conn, rows: list[dict]) -> int:
    now = db.utcnow()
    conn.executemany(
        """INSERT OR REPLACE INTO mlb_team_batting VALUES
           (:team_id, :team_name, :season, :vs_hand, :pa, :so, :k_rate, :fetched_at)""",
        [{**r, "fetched_at": now} for r in rows])
    conn.commit()
    return len(rows)


# --------------------------------------------------------------- live pulls

def pull_day(conn, date: str | None = None) -> dict:
    """Schedule + probables, then game logs + opponent K rates for each probable."""
    date = date or date_cls.today().isoformat()
    season = int(date[:4])
    pulled_at = db.utcnow()
    sched = _get("/schedule", sportId=1, date=date, hydrate="probablePitcher")
    if sched is None:
        return {"games": 0, "error": "statsapi unreachable"}
    _cache_raw(sched, "schedule", pulled_at)
    games = parse_schedule(sched)
    store_games(conn, games)

    pitchers, teams = set(), set()
    for g in games:
        for pid in (g["home_probable_id"], g["away_probable_id"]):
            if pid:
                pitchers.add(pid)
        for tid in (g["home_team_id"], g["away_team_id"]):
            if tid:
                teams.add(tid)

    logs = 0
    for pid in pitchers:
        payload = _get(f"/people/{pid}/stats", stats="gameLog",
                       group="pitching", season=season)
        if payload:
            _cache_raw(payload, f"gamelog_{pid}", pulled_at)
            logs += store_pitcher_logs(conn, parse_pitcher_gamelog(payload, pid))
    splits = 0
    for tid in teams:
        payload = _get(f"/teams/{tid}/stats", stats="statSplits",
                       group="hitting", season=season, sitCodes="vl,vr")
        if payload:
            _cache_raw(payload, f"teamsplits_{tid}", pulled_at)
            splits += store_team_batting(conn, parse_team_splits(payload, tid, season))
    return {"games": len(games), "pitcher_log_rows": logs, "team_split_rows": splits}


# ------------------------------------------------------------------ queries

def pitcher_recent_games(conn, player_id: int, limit: int = 15) -> list[dict]:
    """Most recent first — the order weighted_recent_rate expects."""
    rows = conn.execute(
        """SELECT * FROM mlb_pitcher_logs WHERE player_id = ?
           ORDER BY game_date DESC LIMIT ?""", (player_id, limit)).fetchall()
    return [dict(r) for r in rows]


def team_k_rate(conn, team_id: int, vs_hand: str, season: int) -> float | None:
    row = conn.execute(
        """SELECT k_rate FROM mlb_team_batting
           WHERE team_id = ? AND vs_hand = ? AND season = ?""",
        (team_id, vs_hand, season)).fetchone()
    return row["k_rate"] if row else None


def todays_games(conn, date: str) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM mlb_games WHERE game_date = ?", (date,)).fetchall()]
