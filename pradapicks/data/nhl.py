"""NHL provider — uses api-web.nhle.com (public)."""
from __future__ import annotations

from datetime import date
from typing import Any

from .base import SportProvider


class NHLProvider(SportProvider):
    sport = "NHL"
    base_url = "https://api-web.nhle.com"

    @property
    def supported_markets(self) -> list[str]:
        return [
            "player_shots_on_goal",
            "player_points",
            "player_goals",
            "player_assists",
            "goalie_saves",
            "goalie_goals_against",
        ]

    def fetch_schedule(self, on: date) -> list[dict]:
        data = self._get(f"/v1/schedule/{on.isoformat()}")
        out: list[dict] = []
        for week in data.get("gameWeek", []) or []:
            if week.get("date") != on.isoformat():
                continue
            for g in week.get("games", []) or []:
                home = g.get("homeTeam", {})
                away = g.get("awayTeam", {})
                out.append({
                    "external_id": str(g.get("id")),
                    "game_date": on,
                    "home_team": _team_name(home),
                    "away_team": _team_name(away),
                    "starts_at": g.get("startTimeUTC"),
                    "venue": (g.get("venue") or {}).get("default"),
                    "meta": {"state": g.get("gameState")},
                })
        return out

    def fetch_player_box_scores(self, on: date) -> list[dict]:
        sched = self.fetch_schedule(on)
        rows: list[dict] = []
        for g in sched:
            try:
                box = self._get(f"/v1/gamecenter/{g['external_id']}/boxscore")
            except Exception:
                continue
            pbg = box.get("playerByGameStats") or {}
            for side, opp_side in (("homeTeam", "awayTeam"), ("awayTeam", "homeTeam")):
                team_name = g["home_team"] if side == "homeTeam" else g["away_team"]
                opp = g["away_team"] if side == "homeTeam" else g["home_team"]
                squad = pbg.get(side, {})
                for group in ("forwards", "defense", "goalies"):
                    for p in squad.get(group, []) or []:
                        is_goalie = group == "goalies"
                        rows.append({
                            "player_external_id": str(p.get("playerId")),
                            "player_name": (p.get("name") or {}).get("default") or p.get("name"),
                            "game_external_id": g["external_id"],
                            "game_date": on,
                            "team": team_name,
                            "opponent": opp,
                            "is_home": side == "homeTeam",
                            "stats": (
                                {
                                    "goalie_saves": _num(p.get("saves")),
                                    "goalie_shots_against": _num(p.get("shotsAgainst")),
                                    "goalie_goals_against": _num(p.get("goalsAgainst")),
                                    "goalie_toi": p.get("toi"),
                                }
                                if is_goalie
                                else {
                                    "player_goals": _num(p.get("goals")),
                                    "player_assists": _num(p.get("assists")),
                                    "player_points": _num(p.get("points")),
                                    "player_shots_on_goal": _num(p.get("sog")),
                                    "player_pim": _num(p.get("pim")),
                                    "player_hits": _num(p.get("hits")),
                                    "player_blocks": _num(p.get("blockedShots")),
                                    "player_toi": p.get("toi"),
                                }
                            ),
                        })
        return rows

    def fetch_team_box_scores(self, on: date) -> list[dict]:
        sched = self.fetch_schedule(on)
        out: list[dict] = []
        for g in sched:
            try:
                box = self._get(f"/v1/gamecenter/{g['external_id']}/boxscore")
            except Exception:
                continue
            for side, opp_side in (("homeTeam", "awayTeam"), ("awayTeam", "homeTeam")):
                tb = box.get(side, {})
                out.append({
                    "team": g["home_team"] if side == "homeTeam" else g["away_team"],
                    "game_external_id": g["external_id"],
                    "game_date": on,
                    "opponent": g["away_team"] if side == "homeTeam" else g["home_team"],
                    "is_home": side == "homeTeam",
                    "stats": {
                        "score": _num(tb.get("score")),
                        "sog": _num(tb.get("sog")),
                        "pp_pct": _num((tb.get("powerPlayConversion") or "")),
                        "faceoff_pct": _num(tb.get("faceoffWinningPctg")),
                        "pim": _num(tb.get("pim")),
                        "hits": _num(tb.get("hits")),
                        "blocks": _num(tb.get("blocks")),
                    },
                })
        return out


def _team_name(t: dict) -> str:
    n = t.get("commonName") or t.get("name") or {}
    if isinstance(n, dict):
        return n.get("default") or t.get("abbrev") or ""
    return n or t.get("abbrev") or ""


def _num(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None
