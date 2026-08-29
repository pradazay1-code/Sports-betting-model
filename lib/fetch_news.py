"""
The real-time layer: injuries, lineups, and weather.

This is what you check LAST, right before a recommendation, and it overrides the
model. A great number on a team whose starting point guard was just scratched is
not a great number.

Weather comes from Open-Meteo (free, no key). Wind *direction relative to
stadium orientation* is the part most people skip and the part that actually
moves MLB totals — a 12 mph wind straight out to center at Wrigley is a
different game than 12 mph across the diamond.

Injury and lineup feeds here are the public ESPN/MLB endpoints. They are a
starting point, not the whole job — beat writers break scratches before feeds
update, so the agent should still WebSearch for anything within a few hours of
lock and prefer the more recent source.

CLI:
    python3 -m lib.fetch_news weather --venue "Wrigley Field"
    python3 -m lib.fetch_news weather --lat 41.948 --lon -87.655 --at 2026-08-30T19:20
    python3 -m lib.fetch_news injuries --sport nfl
    python3 -m lib.fetch_news pitchers
    python3 -m lib.fetch_news venues
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Any

from lib import cache

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
ESPN_CORE = "https://site.api.espn.com/apis/site/v2/sports"
MLB_STATS = "https://statsapi.mlb.com/api/v1"

ESPN_PATHS = {
    "nfl": "football/nfl",
    "ncaaf": "football/college-football",
    "nba": "basketball/nba",
    "ncaab": "basketball/mens-college-basketball",
    "wnba": "basketball/wnba",
    "mlb": "baseball/mlb",
    "nhl": "hockey/nhl",
}

#: Outdoor and retractable-roof venues, with the compass bearing (degrees) the
#: batter faces from home plate toward center field, or that the field runs for
#: football. Wind blowing FROM that bearing is blowing in; wind blowing TOWARD it
#: is blowing out. `roof` marks venues where weather usually doesn't matter —
#: "retractable" means check whether it's open before using any of this.
VENUES: dict[str, dict[str, Any]] = {
    # --- MLB ---
    "Wrigley Field":            {"lat": 41.9484, "lon": -87.6553, "bearing": 40,  "roof": "open", "sport": "MLB"},
    "Fenway Park":              {"lat": 42.3467, "lon": -71.0972, "bearing": 45,  "roof": "open", "sport": "MLB"},
    "Yankee Stadium":           {"lat": 40.8296, "lon": -73.9262, "bearing": 78,  "roof": "open", "sport": "MLB"},
    "Oracle Park":              {"lat": 37.7786, "lon": -122.3893, "bearing": 62, "roof": "open", "sport": "MLB"},
    "Coors Field":              {"lat": 39.7559, "lon": -104.9942, "bearing": 5,  "roof": "open", "sport": "MLB"},
    "Dodger Stadium":           {"lat": 34.0739, "lon": -118.2400, "bearing": 24, "roof": "open", "sport": "MLB"},
    "Citi Field":               {"lat": 40.7571, "lon": -73.8458, "bearing": 30,  "roof": "open", "sport": "MLB"},
    "Camden Yards":             {"lat": 39.2839, "lon": -76.6217, "bearing": 32,  "roof": "open", "sport": "MLB"},
    "Great American Ball Park": {"lat": 39.0975, "lon": -84.5069, "bearing": 60,  "roof": "open", "sport": "MLB"},
    "Petco Park":               {"lat": 32.7076, "lon": -117.1570, "bearing": 0,  "roof": "open", "sport": "MLB"},
    "PNC Park":                 {"lat": 40.4469, "lon": -80.0057, "bearing": 118, "roof": "open", "sport": "MLB"},
    "Progressive Field":        {"lat": 41.4962, "lon": -81.6852, "bearing": 0,   "roof": "open", "sport": "MLB"},
    "Comerica Park":            {"lat": 42.3390, "lon": -83.0485, "bearing": 25,  "roof": "open", "sport": "MLB"},
    "Target Field":             {"lat": 44.9817, "lon": -93.2776, "bearing": 80,  "roof": "open", "sport": "MLB"},
    "Kauffman Stadium":         {"lat": 39.0517, "lon": -94.4803, "bearing": 0,   "roof": "open", "sport": "MLB"},
    "Angel Stadium":            {"lat": 33.8003, "lon": -117.8827, "bearing": 40, "roof": "open", "sport": "MLB"},
    "Busch Stadium":            {"lat": 38.6226, "lon": -90.1928, "bearing": 60,  "roof": "open", "sport": "MLB"},
    "Nationals Park":           {"lat": 38.8730, "lon": -77.0074, "bearing": 30,  "roof": "open", "sport": "MLB"},
    "Citizens Bank Park":       {"lat": 39.9061, "lon": -75.1665, "bearing": 15,  "roof": "open", "sport": "MLB"},
    "Truist Park":              {"lat": 33.8907, "lon": -84.4677, "bearing": 55,  "roof": "open", "sport": "MLB"},
    "Oriole Park":              {"lat": 39.2839, "lon": -76.6217, "bearing": 32,  "roof": "open", "sport": "MLB"},
    "Rogers Centre":            {"lat": 43.6414, "lon": -79.3894, "bearing": 0, "roof": "retractable", "sport": "MLB"},
    "American Family Field":    {"lat": 43.0280, "lon": -87.9712, "bearing": 0, "roof": "retractable", "sport": "MLB"},
    "Minute Maid Park":         {"lat": 29.7572, "lon": -95.3555, "bearing": 0, "roof": "retractable", "sport": "MLB"},
    "Chase Field":              {"lat": 33.4455, "lon": -112.0667, "bearing": 0, "roof": "retractable", "sport": "MLB"},
    "T-Mobile Park":            {"lat": 47.5914, "lon": -122.3325, "bearing": 0, "roof": "retractable", "sport": "MLB"},
    "loanDepot Park":           {"lat": 25.7781, "lon": -80.2197, "bearing": 0, "roof": "retractable", "sport": "MLB"},
    "Globe Life Field":         {"lat": 32.7473, "lon": -97.0842, "bearing": 0, "roof": "retractable", "sport": "MLB"},
    "Tropicana Field":          {"lat": 27.7683, "lon": -82.6534, "bearing": 0, "roof": "dome", "sport": "MLB"},
    # --- NFL outdoor ---
    "Highmark Stadium":         {"lat": 42.7738, "lon": -78.7870, "bearing": 0,   "roof": "open", "sport": "NFL"},
    "Soldier Field":            {"lat": 41.8623, "lon": -87.6167, "bearing": 0,   "roof": "open", "sport": "NFL"},
    "Lambeau Field":            {"lat": 44.5013, "lon": -88.0622, "bearing": 0,   "roof": "open", "sport": "NFL"},
    "Arrowhead Stadium":        {"lat": 39.0489, "lon": -94.4839, "bearing": 0,   "roof": "open", "sport": "NFL"},
    "Gillette Stadium":         {"lat": 42.0909, "lon": -71.2643, "bearing": 0,   "roof": "open", "sport": "NFL"},
    "MetLife Stadium":          {"lat": 40.8135, "lon": -74.0745, "bearing": 0,   "roof": "open", "sport": "NFL"},
    "Cleveland Browns Stadium": {"lat": 41.5061, "lon": -81.6995, "bearing": 0,   "roof": "open", "sport": "NFL"},
    "Acrisure Stadium":         {"lat": 40.4468, "lon": -80.0158, "bearing": 0,   "roof": "open", "sport": "NFL"},
    "Empower Field":            {"lat": 39.7439, "lon": -105.0201, "bearing": 0,  "roof": "open", "sport": "NFL"},
    "Lumen Field":              {"lat": 47.5952, "lon": -122.3316, "bearing": 0,  "roof": "open", "sport": "NFL"},
    "Bank of America Stadium":  {"lat": 35.2258, "lon": -80.8528, "bearing": 0,   "roof": "open", "sport": "NFL"},
    "Lincoln Financial Field":  {"lat": 39.9008, "lon": -75.1675, "bearing": 0,   "roof": "open", "sport": "NFL"},
    "M&T Bank Stadium":         {"lat": 39.2780, "lon": -76.6227, "bearing": 0,   "roof": "open", "sport": "NFL"},
    "Paycor Stadium":           {"lat": 39.0955, "lon": -84.5161, "bearing": 0,   "roof": "open", "sport": "NFL"},
    "Nissan Stadium":           {"lat": 36.1665, "lon": -86.7713, "bearing": 0,   "roof": "open", "sport": "NFL"},
    "TIAA Bank Field":          {"lat": 30.3239, "lon": -81.6373, "bearing": 0,   "roof": "open", "sport": "NFL"},
    "Hard Rock Stadium":        {"lat": 25.9580, "lon": -80.2389, "bearing": 0,   "roof": "open", "sport": "NFL"},
    "Levi's Stadium":           {"lat": 37.4033, "lon": -121.9694, "bearing": 0,  "roof": "open", "sport": "NFL"},
    "FedExField":               {"lat": 38.9076, "lon": -76.8645, "bearing": 0,   "roof": "open", "sport": "NFL"},
    "Raymond James Stadium":    {"lat": 27.9759, "lon": -82.5033, "bearing": 0,   "roof": "open", "sport": "NFL"},
}

#: Compass bearing -> wind description, 16-point.
_COMPASS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def compass(deg: float) -> str:
    return _COMPASS[int((deg % 360) / 22.5 + 0.5) % 16]


def wind_relative_to_field(wind_from_deg: float, field_bearing: float) -> dict:
    """
    Turn a raw wind direction into the thing that matters: is it blowing out,
    blowing in, or across?

    Open-Meteo reports the direction the wind is coming FROM. A ballpark's
    `bearing` is home-plate-to-center-field. So wind coming FROM the bearing is
    blowing IN toward home; wind coming from the opposite is blowing OUT.
    """
    # Signed angle between where the wind comes FROM and where center field is,
    # normalized to [-180, 180).
    delta = (wind_from_deg - field_bearing + 180.0) % 360.0 - 180.0
    a = abs(delta)
    if a <= 45:
        effect = "in"
        note = "blowing in from center — suppresses fly balls, favors the under"
    elif a >= 135:
        effect = "out"
        note = "blowing out to center — carries fly balls, favors the over"
    else:
        # Facing out from home toward center, a positive delta means the wind
        # originates on the right-field side, so it BLOWS toward left field.
        # Naming the destination, not the origin — that's the half that matters
        # for where balls carry.
        from_side = "right field" if delta > 0 else "left field"
        to_side = "left field" if delta > 0 else "right field"
        effect = "across"
        note = (
            f"crossing from {from_side} toward {to_side} — mostly a spray/pull "
            "effect, small impact on the total"
        )
    return {
        "effect": effect,
        "angle_off_center": round(delta, 1),
        "note": note,
        "from_compass": compass(wind_from_deg),
    }


def get_weather(
    lat: float,
    lon: float,
    *,
    at: str | None = None,
    ttl: float | None = None,
) -> tuple[dict, dict]:
    """
    Hourly forecast from Open-Meteo. No API key needed.

    `at` is an ISO local hour like "2026-08-30T19:00". Omit it for the current
    conditions plus the next 24 hours.
    """
    if requests is None:
        raise RuntimeError("`requests` isn't installed. pip install -r requirements.txt")

    key = f"weather:{lat:.4f},{lon:.4f}"

    def fetch():
        resp = requests.get(
            OPEN_METEO,
            params={
                "latitude": lat,
                "longitude": lon,
                "hourly": "temperature_2m,precipitation_probability,precipitation,"
                          "wind_speed_10m,wind_direction_10m,wind_gusts_10m,relative_humidity_2m",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "precipitation_unit": "inch",
                "timezone": "auto",
                "forecast_days": 3,
            },
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()

    data, meta = cache.get_or_fetch("weather", key, fetch, ttl=ttl)

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    if not times:
        return {"error": "no hourly data returned"}, meta

    idx = 0
    if at:
        want = at[:13]  # YYYY-MM-DDTHH
        matches = [i for i, t in enumerate(times) if t.startswith(want)]
        if matches:
            idx = matches[0]
        else:
            return (
                {"error": f"no forecast hour matching {at}; range is {times[0]} to {times[-1]}"},
                meta,
            )

    def pick(field):
        vals = hourly.get(field) or []
        return vals[idx] if idx < len(vals) else None

    return (
        {
            "time": times[idx],
            "temp_f": pick("temperature_2m"),
            "humidity_pct": pick("relative_humidity_2m"),
            "wind_mph": pick("wind_speed_10m"),
            "gust_mph": pick("wind_gusts_10m"),
            "wind_from_deg": pick("wind_direction_10m"),
            "wind_from": compass(pick("wind_direction_10m") or 0),
            "precip_prob_pct": pick("precipitation_probability"),
            "precip_in": pick("precipitation"),
        },
        meta,
    )


def venue_weather(venue: str, *, at: str | None = None) -> tuple[dict, dict]:
    """Weather for a known venue, with the wind resolved against field orientation."""
    v = VENUES.get(venue)
    if v is None:
        matches = [k for k in VENUES if venue.lower() in k.lower()]
        if len(matches) == 1:
            venue, v = matches[0], VENUES[matches[0]]
        else:
            raise KeyError(
                f"unknown venue {venue!r}. "
                + (f"Did you mean: {', '.join(matches)}?" if matches else "See `venues` for the list.")
            )

    if v["roof"] == "dome":
        return (
            {"venue": venue, "roof": "dome", "note": "indoor — weather is not a factor"},
            {"source": "static", "age": "n/a"},
        )

    w, meta = get_weather(v["lat"], v["lon"], at=at)
    w["venue"] = venue
    w["roof"] = v["roof"]
    if v["roof"] == "retractable":
        w["roof_warning"] = (
            "Retractable roof — confirm whether it's open before applying any of this. "
            "Books know; if you don't, you're guessing."
        )
    if v.get("bearing") and w.get("wind_from_deg") is not None and v["sport"] == "MLB":
        w["wind_effect"] = wind_relative_to_field(w["wind_from_deg"], v["bearing"])
    elif w.get("wind_mph") is not None:
        w["wind_effect"] = {
            "effect": "n/a",
            "note": (
                "No reliable field orientation stored for this venue. Wind speed alone: "
                "under ~10 mph is noise; 15+ mph starts to matter for kicking and the "
                "passing game."
            ),
        }
    return w, meta


def get_injuries(sport: str, *, ttl: float | None = None) -> tuple[list[dict], dict]:
    """
    Public ESPN injury feed. Free, no key.

    This lags beat reporters. Treat it as the floor of what's known, not the
    ceiling, and WebSearch anything close to lock.
    """
    if requests is None:
        raise RuntimeError("`requests` isn't installed.")
    path = ESPN_PATHS.get(sport.lower())
    if not path:
        raise ValueError(f"no ESPN path for {sport!r}; known: {', '.join(ESPN_PATHS)}")

    def fetch():
        resp = requests.get(f"{ESPN_CORE}/{path}/injuries", timeout=20)
        resp.raise_for_status()
        return resp.json()

    data, meta = cache.get_or_fetch("news", f"injuries:{sport.lower()}", fetch, ttl=ttl)

    out = []
    for team in data.get("injuries", []):
        for item in team.get("injuries", []):
            athlete = item.get("athlete") or {}
            out.append(
                {
                    "team": team.get("displayName"),
                    "player": athlete.get("displayName"),
                    "position": (athlete.get("position") or {}).get("abbreviation"),
                    "status": item.get("status"),
                    "detail": (item.get("details") or {}).get("type") or item.get("shortComment"),
                    "date": item.get("date"),
                }
            )
    return out, meta


def get_probable_pitchers(*, date: str | None = None, ttl: float | None = None) -> tuple[list[dict], dict]:
    """
    MLB probable starters off the free MLB StatsAPI.

    "Probable" is doing work in that name — a probable is not a confirmed
    starter, and the difference is worth real money on an F5 line.
    """
    if requests is None:
        raise RuntimeError("`requests` isn't installed.")
    d = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def fetch():
        resp = requests.get(
            f"{MLB_STATS}/schedule",
            params={"sportId": 1, "date": d, "hydrate": "probablePitcher,team,linescore"},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()

    data, meta = cache.get_or_fetch("news", f"pitchers:{d}", fetch, ttl=ttl)

    games = []
    for day in data.get("dates", []):
        for g in day.get("games", []):
            teams = g.get("teams", {})

            def side(k):
                t = teams.get(k, {})
                pp = t.get("probablePitcher") or {}
                return {
                    "team": (t.get("team") or {}).get("name"),
                    "pitcher": pp.get("fullName") or "TBD",
                    "pitcher_id": pp.get("id"),
                }

            games.append(
                {
                    "game_pk": g.get("gamePk"),
                    "start": g.get("gameDate"),
                    "status": (g.get("status") or {}).get("detailedState"),
                    "venue": (g.get("venue") or {}).get("name"),
                    "away": side("away"),
                    "home": side("home"),
                }
            )
    return games, meta


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_weather(args) -> int:
    try:
        if args.venue:
            w, meta = venue_weather(args.venue, at=args.at)
        elif args.lat is not None and args.lon is not None:
            w, meta = get_weather(args.lat, args.lon, at=args.at)
        else:
            print("give --venue or both --lat and --lon")
            return 2
    except Exception as e:  # noqa: BLE001
        print(f"FETCH FAILED: {type(e).__name__}: {e}")
        return 1

    if w.get("error"):
        print(f"no data: {w['error']}")
        return 1
    if w.get("roof") == "dome":
        print(f"{w['venue']}: {w['note']}")
        return 0

    print(f"{w.get('venue', f'{args.lat},{args.lon}')}  @ {w['time']}   [{meta.get('source')}, age {meta.get('age')}]")
    print(f"  temp      : {w['temp_f']}F   humidity {w['humidity_pct']}%")
    print(f"  wind      : {w['wind_mph']} mph from {w['wind_from']} ({w['wind_from_deg']}deg), gusts {w['gust_mph']}")
    print(f"  precip    : {w['precip_prob_pct']}% chance, {w['precip_in']} in")
    if w.get("wind_effect"):
        we = w["wind_effect"]
        print(f"  effect    : {we['effect']} — {we['note']}")
    if w.get("roof_warning"):
        print(f"  !! {w['roof_warning']}")
    return 0


def _cmd_injuries(args) -> int:
    try:
        rows, meta = get_injuries(args.sport)
    except Exception as e:  # noqa: BLE001
        print(f"FETCH FAILED: {type(e).__name__}: {e}")
        return 1
    print(f"[{meta.get('source')}, age {meta.get('age')}]  {len(rows)} entries")
    if meta.get("degraded"):
        print(f"!! {meta['warning']}")
    key = args.team.lower() if args.team else None
    shown = 0
    for r in rows:
        if key and key not in (r["team"] or "").lower():
            continue
        print(f"  {r['team']:<26} {r['position'] or '':<4} {r['player']:<26} {r['status']:<14} {r['detail'] or ''}")
        shown += 1
    if not shown:
        print("  nothing matching.")
    print("\nThis feed lags beat reporters. Search for late news before you bet.")
    return 0


def _cmd_pitchers(args) -> int:
    try:
        games, meta = get_probable_pitchers(date=args.date)
    except Exception as e:  # noqa: BLE001
        print(f"FETCH FAILED: {type(e).__name__}: {e}")
        return 1
    print(f"[{meta.get('source')}, age {meta.get('age')}]")
    for g in games:
        print(f"  {g['away']['team']} ({g['away']['pitcher']}) @ {g['home']['team']} ({g['home']['pitcher']})")
        print(f"      {g['start']}  {g['venue']}  — {g['status']}")
    if not games:
        print("  no games scheduled.")
    print("\n'Probable' is not 'confirmed'. Verify before betting an F5.")
    return 0


def _cmd_venues(args) -> int:
    for name, v in sorted(VENUES.items(), key=lambda kv: (kv[1]["sport"], kv[0])):
        print(f"  {v['sport']:<4} {name:<28} {v['roof']:<12} bearing {v['bearing']:>3}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lib.fetch_news", description="The Desk — real-time layer.")
    sub = p.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("weather", help="forecast, with wind resolved against the field")
    w.add_argument("--venue")
    w.add_argument("--lat", type=float)
    w.add_argument("--lon", type=float)
    w.add_argument("--at", help="ISO local hour, e.g. 2026-08-30T19:00")
    w.set_defaults(func=_cmd_weather)

    i = sub.add_parser("injuries", help="ESPN injury feed")
    i.add_argument("--sport", required=True, choices=list(ESPN_PATHS))
    i.add_argument("--team", default=None)
    i.set_defaults(func=_cmd_injuries)

    pp = sub.add_parser("pitchers", help="MLB probable starters")
    pp.add_argument("--date", default=None, help="YYYY-MM-DD")
    pp.set_defaults(func=_cmd_pitchers)

    sub.add_parser("venues", help="known venues and orientations").set_defaults(func=_cmd_venues)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
