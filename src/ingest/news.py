"""News query helper feeding the deep-research pipeline (spec §4).

Query construction lives here so deep_dive briefs and any future RSS/news
ingestion share one vocabulary of angles: beat writers, coach quotes,
lineup leaks, weather, motivation (eliminated teams, resting starters).
"""

from __future__ import annotations

ANGLES = ["beat writer report", "coach quotes minutes role", "lineup leak",
          "weather forecast", "resting starters eliminated"]


def build_queries(player: str | None, team: str | None, market: str) -> list[str]:
    who = player or team or ""
    base = [f"{who} {angle}" for angle in ANGLES[:3] if who]
    if "yds" in market or "total" in market:
        base.append(f"{team or who} weather forecast wind")
    return base or [f"{market} news"]
