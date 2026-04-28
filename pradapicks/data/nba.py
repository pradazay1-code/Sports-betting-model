"""NBA provider — uses stats.nba.com public endpoints.

These endpoints require a browser-like User-Agent and Referer header. They are
rate-sensitive; we add throttling at the call site rather than here.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from .base import SportProvider


class NBAProvider(SportProvider):
    sport = "NBA"
    base_url = "https://stats.nba.com"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.nba.com/",
        "Origin": "https://www.nba.com",
        "x-nba-stats-origin": "stats",
        "x-nba-stats-token": "true",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
    }

    @property
    def supported_markets(self) -> list[str]:
        return [
            "player_points",
            "player_rebounds",
            "player_assists",
            "player_threes",
            "player_steals",
            "player_blocks",
            "player_turnovers",
            "player_pra",  # points + rebounds + assists
            "player_pa",
            "player_pr",
            "player_ra",
        ]

    def fetch_schedule(self, on: date) -> list[dict]:
        data = self._get(
            "/stats/scoreboardv3",
            params={"GameDate": on.strftime("%m/%d/%Y"), "LeagueID": "00"},
        )
        out: list[dict] = []
        for g in data.get("scoreboard", {}).get("games", []) or []:
            out.append({
                "external_id": str(g.get("gameId")),
                "game_date": on,
                "home_team": (g.get("homeTeam") or {}).get("teamName"),
                "away_team": (g.get("awayTeam") or {}).get("teamName"),
                "starts_at": g.get("gameTimeUTC"),
                "venue": (g.get("arena") or {}).get("arenaName"),
                "meta": {"status": g.get("gameStatusText")},
            })
        return out

    def fetch_player_box_scores(self, on: date) -> list[dict]:
        sched = self.fetch_schedule(on)
        rows: list[dict] = []
        for g in sched:
            try:
                data = self._get(
                    "/stats/boxscoretraditionalv3",
                    params={
                        "GameID": g["external_id"],
                        "LeagueID": "00",
                        "endPeriod": 0,
                        "endRange": 28800,
                        "rangeType": 0,
                        "startPeriod": 0,
                        "startRange": 0,
                    },
                )
            except Exception:
                continue
            box = data.get("boxScoreTraditional") or {}
            for side, opp_side in (("homeTeam", "awayTeam"), ("awayTeam", "homeTeam")):
                team_block = box.get(side, {})
                team_name = team_block.get("teamName")
                opp = box.get(opp_side, {}).get("teamName")
                for p in team_block.get("players", []) or []:
                    s = p.get("statistics", {}) or {}
                    pts = _num(s.get("points"))
                    reb = _num(s.get("reboundsTotal"))
                    ast = _num(s.get("assists"))
                    rows.append({
                        "player_external_id": str(p.get("personId")),
                        "player_name": f"{p.get('firstName','')} {p.get('familyName','')}".strip(),
                        "game_external_id": g["external_id"],
                        "game_date": on,
                        "team": team_name,
                        "opponent": opp,
                        "is_home": side == "homeTeam",
                        "stats": {
                            "player_points": pts,
                            "player_rebounds": reb,
                            "player_assists": ast,
                            "player_threes": _num(s.get("threePointersMade")),
                            "player_steals": _num(s.get("steals")),
                            "player_blocks": _num(s.get("blocks")),
                            "player_turnovers": _num(s.get("turnovers")),
                            "player_minutes": _minutes_to_float(s.get("minutes")),
                            "player_fga": _num(s.get("fieldGoalsAttempted")),
                            "player_fta": _num(s.get("freeThrowsAttempted")),
                            "player_pra": _sum_or_none(pts, reb, ast),
                            "player_pa": _sum_or_none(pts, ast),
                            "player_pr": _sum_or_none(pts, reb),
                            "player_ra": _sum_or_none(reb, ast),
                            "usage_rate": _num(s.get("usagePercentage")),
                        },
                    })
        return rows

    def fetch_team_box_scores(self, on: date) -> list[dict]:
        sched = self.fetch_schedule(on)
        out: list[dict] = []
        for g in sched:
            try:
                data = self._get(
                    "/stats/boxscoreadvancedv3",
                    params={
                        "GameID": g["external_id"],
                        "LeagueID": "00",
                        "endPeriod": 0,
                        "endRange": 28800,
                        "rangeType": 0,
                        "startPeriod": 0,
                        "startRange": 0,
                    },
                )
            except Exception:
                continue
            adv = data.get("boxScoreAdvanced") or {}
            for side, opp_side in (("homeTeam", "awayTeam"), ("awayTeam", "homeTeam")):
                tb = adv.get(side, {})
                ts = tb.get("statistics", {}) or {}
                out.append({
                    "team": tb.get("teamName"),
                    "game_external_id": g["external_id"],
                    "game_date": on,
                    "opponent": adv.get(opp_side, {}).get("teamName"),
                    "is_home": side == "homeTeam",
                    "stats": {
                        "off_rating": _num(ts.get("offensiveRating")),
                        "def_rating": _num(ts.get("defensiveRating")),
                        "pace": _num(ts.get("pace")),
                        "efg_pct": _num(ts.get("effectiveFieldGoalPercentage")),
                        "ts_pct": _num(ts.get("trueShootingPercentage")),
                    },
                })
        return out


def _num(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def _minutes_to_float(v: Any) -> float | None:
    if v is None:
        return None
    s = str(v)
    if ":" in s:
        m, sec = s.split(":", 1)
        try:
            return float(m) + float(sec) / 60.0
        except ValueError:
            return None
    return _num(s)


def _sum_or_none(*vals: Any) -> float | None:
    if any(v is None for v in vals):
        return None
    return float(sum(vals))
