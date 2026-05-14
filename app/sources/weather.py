"""Weather via Open-Meteo (free, no key).

Looks up forecast for the venue lat/lon at game start time. We only call this
for outdoor MLB stadiums — NBA / NHL play indoors.
"""

from __future__ import annotations

from datetime import datetime

from app.utils import http_get_json, now_iso

# Venue lat/lon for MLB stadiums (subset; missing venues simply skip).
STADIUMS = {
    "Yankee Stadium": (40.829659, -73.926186),
    "Fenway Park": (42.346676, -71.097218),
    "Wrigley Field": (41.948438, -87.655339),
    "Dodger Stadium": (34.073851, -118.240294),
    "Oracle Park": (37.778572, -122.389717),
    "Citi Field": (40.756945, -73.845821),
    "Citizens Bank Park": (39.906057, -75.166548),
    "PNC Park": (40.446904, -80.005903),
    "Great American Ball Park": (39.097389, -84.506611),
    "Camden Yards": (39.283787, -76.621622),
    "Petco Park": (32.707656, -117.157003),
    "Coors Field": (39.756111, -104.994167),
    "Minute Maid Park": (29.757222, -95.355556),
    "Busch Stadium": (38.622469, -90.193040),
    "Truist Park": (33.890672, -84.467684),
    "Target Field": (44.981667, -93.277778),
    "Comerica Park": (42.339167, -83.048611),
    "Kauffman Stadium": (39.051389, -94.480556),
    "Progressive Field": (41.495861, -81.685306),
    "American Family Field": (43.028056, -87.971111),
    "Angel Stadium": (33.800278, -117.882778),
    "Oakland Coliseum": (37.751667, -122.200556),
    "Globe Life Field": (32.747222, -97.083889),
    "T-Mobile Park": (47.591389, -122.332500),
    "Nationals Park": (38.872778, -77.007222),
    "loanDepot park": (25.778056, -80.219722),
    "Tropicana Field": (27.768333, -82.653333),
    "Rogers Centre": (43.641389, -79.389167),
    "Chase Field": (33.445278, -112.066944),
}


def forecast_for(game_id: str, venue: str, start_utc: str | None) -> dict | None:
    coords = STADIUMS.get(venue)
    if not coords:
        return None
    lat, lon = coords
    data = http_get_json(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "hourly": "temperature_2m,precipitation_probability,wind_speed_10m,wind_direction_10m,weather_code",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "forecast_days": 2,
            "timezone": "UTC",
        },
    )
    if not data or "hourly" not in data:
        return None
    times = data["hourly"].get("time") or []
    if not times:
        return None
    # Pick hour closest to game start.
    try:
        target = datetime.fromisoformat((start_utc or "").replace("Z", "+00:00"))
        idx = min(range(len(times)), key=lambda i: abs(
            (datetime.fromisoformat(times[i]).replace(tzinfo=target.tzinfo) - target).total_seconds()
        ))
    except Exception:
        idx = 0
    h = data["hourly"]
    return {
        "game_id": game_id,
        "fetched_at": now_iso(),
        "temp_f": _at(h.get("temperature_2m"), idx),
        "wind_mph": _at(h.get("wind_speed_10m"), idx),
        "wind_dir": _wind_dir(_at(h.get("wind_direction_10m"), idx)),
        "precip_pct": _at(h.get("precipitation_probability"), idx),
        "conditions": _wx_code(_at(h.get("weather_code"), idx)),
    }


def _at(arr, i):
    if not arr or i is None or i >= len(arr):
        return None
    return arr[i]


def _wind_dir(deg) -> str | None:
    if deg is None:
        return None
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return dirs[int((deg % 360) / 45 + 0.5) % 8]


def _wx_code(c) -> str | None:
    if c is None:
        return None
    code = int(c)
    if code == 0: return "clear"
    if code <= 3: return "cloudy"
    if code in (45, 48): return "fog"
    if 51 <= code <= 67: return "rain"
    if 71 <= code <= 77: return "snow"
    if 80 <= code <= 82: return "showers"
    if 95 <= code <= 99: return "thunderstorm"
    return f"code:{code}"
