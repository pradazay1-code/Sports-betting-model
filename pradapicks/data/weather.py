"""Free weather data from open-meteo.com — no key, no rate limits.

Used to enrich MLB outdoor games. Wind, temperature, and precipitation
materially affect run scoring; the model picks these up as features.
"""
from __future__ import annotations

import logging

from .base import HTTPProvider

log = logging.getLogger(__name__)

# Approximate latlon for MLB stadium cities — coarse but enough for
# day-of forecast which is what we care about.
MLB_CITY_COORDS = {
    "New York Yankees": (40.83, -73.93),
    "New York Mets": (40.76, -73.85),
    "Boston Red Sox": (42.35, -71.10),
    "Toronto Blue Jays": (43.64, -79.39),
    "Baltimore Orioles": (39.28, -76.62),
    "Tampa Bay Rays": (27.77, -82.65),
    "Chicago White Sox": (41.83, -87.63),
    "Chicago Cubs": (41.95, -87.65),
    "Cleveland Guardians": (41.50, -81.69),
    "Detroit Tigers": (42.34, -83.05),
    "Minnesota Twins": (44.98, -93.28),
    "Kansas City Royals": (39.05, -94.48),
    "Houston Astros": (29.76, -95.36),
    "Los Angeles Angels": (33.80, -117.88),
    "Los Angeles Dodgers": (34.07, -118.24),
    "Oakland Athletics": (37.75, -122.20),
    "Seattle Mariners": (47.59, -122.33),
    "Texas Rangers": (32.75, -97.08),
    "Atlanta Braves": (33.89, -84.47),
    "Miami Marlins": (25.78, -80.22),
    "Philadelphia Phillies": (39.91, -75.17),
    "Washington Nationals": (38.87, -77.01),
    "Cincinnati Reds": (39.10, -84.51),
    "Milwaukee Brewers": (43.03, -87.97),
    "Pittsburgh Pirates": (40.45, -80.01),
    "St. Louis Cardinals": (38.62, -90.19),
    "San Francisco Giants": (37.78, -122.39),
    "San Diego Padres": (32.71, -117.16),
    "Colorado Rockies": (39.76, -104.99),
    "Arizona Diamondbacks": (33.45, -112.07),
}


class WeatherProvider(HTTPProvider):
    base_url = "https://api.open-meteo.com"
    headers = {"Accept": "application/json", "User-Agent": "Pradapicks/0.1"}

    def fetch(self, home_team: str) -> dict | None:
        coords = MLB_CITY_COORDS.get(home_team)
        if not coords:
            return None
        lat, lon = coords
        try:
            data = self._get(
                "/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,wind_speed_10m,wind_direction_10m,precipitation",
                    "temperature_unit": "fahrenheit",
                    "wind_speed_unit": "mph",
                    "precipitation_unit": "inch",
                },
            )
        except Exception as e:
            log.warning("weather fetch failed for %s: %s", home_team, e)
            return None
        cur = data.get("current") or {}
        return {
            "temperature_f": cur.get("temperature_2m"),
            "wind_mph": cur.get("wind_speed_10m"),
            "wind_dir_deg": cur.get("wind_direction_10m"),
            "precipitation_in": cur.get("precipitation"),
        }
