"""Injury reports + confirmed-lineup gate (spec §2.3).

ESPN's public injuries API covers every league. NBA/soccer props are
HOLD status until lineups confirm; `apply_lineup_gate` upgrades them.
"""

from __future__ import annotations

import requests

from src import config, db

ESPN_INJURIES = {
    "basketball_nba": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries",
    "americanfootball_nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries",
    "baseball_mlb": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/injuries",
}

LINEUP_GATED_SPORTS = ("basketball_nba", "soccer_fifa_world_cup")


def parse_espn_injuries(payload: dict, sport: str) -> list[dict]:
    rows = []
    for team_blk in payload.get("injuries", []):
        team = team_blk.get("displayName")
        for inj in team_blk.get("injuries", []):
            athlete = inj.get("athlete") or {}
            rows.append({
                "sport": sport,
                "player": athlete.get("displayName"),
                "team": team,
                "status": inj.get("status"),
                "detail": ((inj.get("details") or {}).get("type") or ""),
            })
    return [r for r in rows if r["player"]]


def store_injuries(conn, rows: list[dict]) -> int:
    now = db.utcnow()
    conn.executemany(
        """INSERT OR IGNORE INTO injuries (sport, player, team, status, detail, fetched_at)
           VALUES (:sport, :player, :team, :status, :detail, :fetched_at)""",
        [{**r, "fetched_at": now} for r in rows])
    conn.commit()
    return len(rows)


def pull_all(conn) -> int:
    total = 0
    for sport, url in ESPN_INJURIES.items():
        try:
            resp = requests.get(url, timeout=config.sources()["http"]["timeout_seconds"])
            if resp.status_code == 200:
                total += store_injuries(conn, parse_espn_injuries(resp.json(), sport))
        except requests.RequestException:
            continue
    return total


def player_injury_status(conn, sport: str, player: str) -> str | None:
    row = conn.execute(
        """SELECT status FROM injuries WHERE sport = ? AND player = ?
           ORDER BY fetched_at DESC LIMIT 1""", (sport, player)).fetchone()
    return row["status"] if row else None


# ---------------------------------------------------------------- lineup gate

def hold_ungated_picks(conn) -> int:
    """New NBA/soccer picks start as HOLD until lineups confirm (spec §2.3)."""
    cur = conn.execute(
        f"""UPDATE picks SET status = 'hold_lineup'
            WHERE status = 'pending' AND player IS NOT NULL
              AND sport IN ({','.join('?' * len(LINEUP_GATED_SPORTS))})""",
        LINEUP_GATED_SPORTS)
    conn.commit()
    return cur.rowcount


def apply_lineup_gate(conn, sport: str, confirmed_players: list[str]) -> int:
    """Auto-upgrade HOLD -> pending (PLAY) once the player is confirmed."""
    n = 0
    for player in confirmed_players:
        cur = conn.execute(
            """UPDATE picks SET status = 'pending'
               WHERE status = 'hold_lineup' AND sport = ? AND player = ?""",
            (sport, player))
        n += cur.rowcount
    conn.commit()
    return n
