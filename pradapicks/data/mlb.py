"""MLB Stats API provider — public, no key required.

Endpoints used:
  https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=YYYY-MM-DD&hydrate=probablePitcher,linescore,team,venue
  https://statsapi.mlb.com/api/v1/game/{gamePk}/boxscore
"""
from __future__ import annotations

from datetime import date
from typing import Any

from .base import SportProvider


class MLBProvider(SportProvider):
    sport = "MLB"
    base_url = "https://statsapi.mlb.com"

    @property
    def supported_markets(self) -> list[str]:
        return [
            "batter_hits",
            "batter_total_bases",
            "batter_home_runs",
            "batter_rbis",
            "batter_runs_scored",
            "batter_strikeouts",
            "pitcher_strikeouts",
            "pitcher_outs",
            "pitcher_earned_runs",
            "pitcher_hits_allowed",
        ]

    def fetch_schedule(self, on: date) -> list[dict]:
        data = self._get(
            "/api/v1/schedule",
            params={
                "sportId": 1,
                "date": on.isoformat(),
                "hydrate": "probablePitcher,linescore,team,venue,weather",
            },
        )
        out: list[dict] = []
        for d in data.get("dates", []):
            for g in d.get("games", []):
                teams = g.get("teams", {})
                home = teams.get("home", {}).get("team", {})
                away = teams.get("away", {}).get("team", {})
                out.append({
                    "external_id": str(g.get("gamePk")),
                    "game_date": on,
                    "home_team": home.get("name"),
                    "away_team": away.get("name"),
                    "starts_at": g.get("gameDate"),
                    "venue": (g.get("venue") or {}).get("name"),
                    "meta": {
                        "status": g.get("status", {}).get("abstractGameState"),
                        "probable_pitchers": {
                            "home": (teams.get("home", {}).get("probablePitcher") or {}).get("fullName"),
                            "away": (teams.get("away", {}).get("probablePitcher") or {}).get("fullName"),
                        },
                        "weather": g.get("weather"),
                    },
                })
        return out

    def fetch_player_box_scores(self, on: date) -> list[dict]:
        sched = self.fetch_schedule(on)
        rows: list[dict] = []
        for g in sched:
            try:
                box = self._get(f"/api/v1/game/{g['external_id']}/boxscore")
            except Exception:
                continue
            for side in ("home", "away"):
                team_block = box.get("teams", {}).get(side, {})
                team_name = team_block.get("team", {}).get("name")
                opp = g["away_team"] if side == "home" else g["home_team"]
                for pid, pdata in (team_block.get("players") or {}).items():
                    person = pdata.get("person", {})
                    stats = pdata.get("stats", {}) or {}
                    bat = stats.get("batting", {}) or {}
                    pit = stats.get("pitching", {}) or {}
                    if not bat and not pit:
                        continue
                    rows.append({
                        "player_external_id": str(person.get("id")),
                        "player_name": person.get("fullName"),
                        "game_external_id": g["external_id"],
                        "game_date": on,
                        "team": team_name,
                        "opponent": opp,
                        "is_home": side == "home",
                        "stats": {
                            "batter_hits": bat.get("hits"),
                            "batter_total_bases": bat.get("totalBases"),
                            "batter_home_runs": bat.get("homeRuns"),
                            "batter_rbis": bat.get("rbi"),
                            "batter_runs_scored": bat.get("runs"),
                            "batter_strikeouts": bat.get("strikeOuts"),
                            "batter_walks": bat.get("baseOnBalls"),
                            "at_bats": bat.get("atBats"),
                            "pitcher_strikeouts": pit.get("strikeOuts"),
                            "pitcher_outs": _innings_to_outs(pit.get("inningsPitched")),
                            "pitcher_earned_runs": pit.get("earnedRuns"),
                            "pitcher_hits_allowed": pit.get("hits"),
                            "pitcher_walks": pit.get("baseOnBalls"),
                        },
                    })
        return rows

    def fetch_team_box_scores(self, on: date) -> list[dict]:
        sched = self.fetch_schedule(on)
        out: list[dict] = []
        for g in sched:
            try:
                box = self._get(f"/api/v1/game/{g['external_id']}/boxscore")
            except Exception:
                continue
            for side in ("home", "away"):
                tb = box.get("teams", {}).get(side, {})
                team_name = tb.get("team", {}).get("name")
                opp = g["away_team"] if side == "home" else g["home_team"]
                ts = (tb.get("teamStats") or {})
                bat = ts.get("batting", {}) or {}
                pit = ts.get("pitching", {}) or {}
                out.append({
                    "team": team_name,
                    "game_external_id": g["external_id"],
                    "game_date": on,
                    "opponent": opp,
                    "is_home": side == "home",
                    "stats": {
                        "runs": bat.get("runs"),
                        "hits": bat.get("hits"),
                        "home_runs": bat.get("homeRuns"),
                        "strikeouts": bat.get("strikeOuts"),
                        "team_era": pit.get("era"),
                        "team_whip": pit.get("whip"),
                        "team_k_per_9": pit.get("strikeoutsPer9Inn"),
                    },
                })
        return out


def _innings_to_outs(ip: Any) -> int | None:
    if ip is None:
        return None
    try:
        whole, _, frac = str(ip).partition(".")
        return int(whole) * 3 + int(frac or 0)
    except ValueError:
        return None
