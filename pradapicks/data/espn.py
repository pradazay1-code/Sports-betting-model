"""ESPN public scoreboard + box score provider.

ESPN's `site.api.espn.com` endpoints are free, require no auth, and work
reliably from cloud IPs (Render, Fly, AWS). Same URL shape covers MLB,
NBA, and NHL — only the league slug changes.

Endpoints used:
  /apis/site/v2/sports/{sport}/{league}/scoreboard?dates=YYYYMMDD
  /apis/site/v2/sports/{sport}/{league}/summary?event={gameId}
"""
from __future__ import annotations

from datetime import date
from typing import Any

from .base import SportProvider

ESPN_PATH = {
    "MLB": "baseball/mlb",
    "NBA": "basketball/nba",
    "NHL": "hockey/nhl",
}


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        s = str(v).strip()
        if "-" in s and not s.startswith("-"):
            # "8-12" style — take made
            return float(s.split("-")[0])
        return float(s.replace("+", "").replace("EVEN", "100"))
    except (ValueError, TypeError):
        return None


class ESPNProvider(SportProvider):
    """Single class, parametrized by sport."""

    base_url = "https://site.api.espn.com"
    headers = {
        "Accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
    }

    def __init__(self, sport: str) -> None:
        super().__init__()
        self.sport = sport
        self._path = ESPN_PATH[sport]

    @property
    def supported_markets(self) -> list[str]:
        if self.sport == "NBA":
            return [
                "player_points", "player_rebounds", "player_assists",
                "player_threes", "player_steals", "player_blocks",
                "player_turnovers", "player_pra", "player_pa",
                "player_pr", "player_ra",
            ]
        if self.sport == "MLB":
            return [
                "batter_hits", "batter_total_bases", "batter_home_runs",
                "batter_rbis", "batter_runs_scored", "batter_strikeouts",
                "pitcher_strikeouts", "pitcher_outs",
                "pitcher_earned_runs", "pitcher_hits_allowed",
            ]
        if self.sport == "NHL":
            return [
                "player_shots_on_goal", "player_points", "player_goals",
                "player_assists", "goalie_saves", "goalie_goals_against",
            ]
        return []

    # ---- schedule ----
    def fetch_schedule(self, on: date) -> list[dict]:
        ymd = on.strftime("%Y%m%d")
        try:
            data = self._get(
                f"/apis/site/v2/sports/{self._path}/scoreboard",
                params={"dates": ymd},
            )
        except Exception:
            return []
        out: list[dict] = []
        for ev in data.get("events") or []:
            comps = (ev.get("competitions") or [{}])[0].get("competitors") or []
            home = away = None
            home_logo = away_logo = None
            home_color = away_color = None
            home_abbr = away_abbr = None
            for c in comps:
                team = c.get("team") or {}
                name = team.get("displayName")
                logo = team.get("logo") or (team.get("logos") or [{}])[0].get("href")
                color = team.get("color")
                abbr = team.get("abbreviation")
                if c.get("homeAway") == "home":
                    home = name; home_logo = logo; home_color = color; home_abbr = abbr
                else:
                    away = name; away_logo = logo; away_color = color; away_abbr = abbr
            out.append({
                "external_id": str(ev.get("id")),
                "game_date": on,
                "home_team": home,
                "away_team": away,
                "starts_at": ev.get("date"),
                "venue": ((ev.get("competitions") or [{}])[0].get("venue") or {}).get("fullName"),
                "meta": {
                    "status": (ev.get("status", {}).get("type") or {}).get("description"),
                    "home_logo": home_logo,
                    "away_logo": away_logo,
                    "home_color": home_color,
                    "away_color": away_color,
                    "home_abbr": home_abbr,
                    "away_abbr": away_abbr,
                },
            })
        return out

    # ---- player box scores ----
    def fetch_player_box_scores(self, on: date) -> list[dict]:
        sched = self.fetch_schedule(on)
        rows: list[dict] = []
        for g in sched:
            try:
                summary = self._get(
                    f"/apis/site/v2/sports/{self._path}/summary",
                    params={"event": g["external_id"]},
                )
            except Exception:
                continue
            box = summary.get("boxscore") or {}
            for team_block in box.get("players") or []:
                team_name = (team_block.get("team") or {}).get("displayName")
                opp = g["away_team"] if team_name == g["home_team"] else g["home_team"]
                is_home = team_name == g["home_team"]
                for grp in team_block.get("statistics") or []:
                    names = [n.lower() for n in (grp.get("names") or [])]
                    for ath in grp.get("athletes") or []:
                        person = ath.get("athlete") or {}
                        stats_arr = ath.get("stats") or []
                        if not stats_arr:
                            continue
                        stats = self._parse_stats(self.sport, names, stats_arr, grp)
                        if not stats:
                            continue
                        # Pull jersey + headshot from athlete record (ESPN exposes them).
                        jersey = person.get("jersey")
                        headshot = (person.get("headshot") or {}).get("href") if isinstance(person.get("headshot"), dict) else person.get("headshot")
                        position = (person.get("position") or {}).get("abbreviation") if isinstance(person.get("position"), dict) else person.get("position")
                        rows.append({
                            "player_external_id": str(person.get("id")),
                            "player_name": person.get("displayName"),
                            "game_external_id": g["external_id"],
                            "game_date": on,
                            "team": team_name,
                            "opponent": opp,
                            "is_home": is_home,
                            "stats": stats,
                            "jersey": jersey,
                            "headshot_url": headshot,
                            "position": position,
                        })
        return rows

    def fetch_team_box_scores(self, on: date) -> list[dict]:
        # Team aggregates can be derived from player rows when needed; ESPN's
        # team-level numbers are sport-specific. Skip for now — features.py
        # only uses opponent context which we get from player rows.
        return []

    def _parse_stats(
        self, sport: str, names: list[str], values: list[str], grp: dict
    ) -> dict:
        idx = {n: i for i, n in enumerate(names)}
        def get(*keys: str) -> float | None:
            for k in keys:
                if k in idx and idx[k] < len(values):
                    return _f(values[idx[k]])
            return None

        if sport == "NBA":
            pts = get("pts")
            reb = get("reb")
            ast = get("ast")
            three = get("3pt")
            return _drop_none({
                "player_points": pts,
                "player_rebounds": reb,
                "player_assists": ast,
                "player_threes": three,
                "player_steals": get("stl"),
                "player_blocks": get("blk"),
                "player_turnovers": get("to"),
                "player_minutes": get("min"),
                "player_pra": _sum(pts, reb, ast),
                "player_pa": _sum(pts, ast),
                "player_pr": _sum(pts, reb),
                "player_ra": _sum(reb, ast),
            })

        if sport == "MLB":
            label = (grp.get("name") or grp.get("displayName") or "").lower()
            # Batting block uses ab/r/h/rbi/bb/k/avg; pitching uses ip/h/r/er/bb/k.
            if "pitch" in label:
                ip = get("ip")
                outs = None
                if ip is not None:
                    whole = int(ip)
                    frac = round((ip - whole) * 10)
                    outs = whole * 3 + frac
                return _drop_none({
                    "pitcher_strikeouts": get("k"),
                    "pitcher_outs": outs,
                    "pitcher_earned_runs": get("er"),
                    "pitcher_hits_allowed": get("h"),
                    "pitcher_walks": get("bb"),
                })
            else:
                return _drop_none({
                    "batter_hits": get("h"),
                    "at_bats": get("ab"),
                    "batter_runs_scored": get("r"),
                    "batter_rbis": get("rbi"),
                    "batter_walks": get("bb"),
                    "batter_strikeouts": get("k"),
                    "batter_total_bases": get("tb"),
                    "batter_home_runs": get("hr"),
                })

        if sport == "NHL":
            label = (grp.get("name") or grp.get("displayName") or "").lower()
            if "goalie" in label or "goalies" in label:
                return _drop_none({
                    "goalie_saves": get("sa") and (get("sa") - (get("ga") or 0)) or get("sv"),
                    "goalie_goals_against": get("ga"),
                    "goalie_shots_against": get("sa"),
                })
            return _drop_none({
                "player_goals": get("g"),
                "player_assists": get("a"),
                "player_points": get("pts"),
                "player_shots_on_goal": get("sog", "s"),
                "player_pim": get("pim"),
                "player_hits": get("ht", "hits"),
                "player_blocks": get("bs", "blk"),
            })
        return {}


def _sum(*vals: float | None) -> float | None:
    if any(v is None for v in vals):
        return None
    return float(sum(vals))


def _drop_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}
