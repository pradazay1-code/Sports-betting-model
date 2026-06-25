"""Runtime configuration — pure dataclass, no Pydantic.

Reads from environment with safe defaults so the system runs in CI, on a
laptop, and in any GitHub Action without setup.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str) -> str:
    val = os.environ.get(name)
    return val if val is not None and val != "" else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    db_path: Path = field(default_factory=lambda: Path(_env("DB_PATH", str(ROOT / "data" / "pradapicks.db"))))
    models_dir: Path = field(default_factory=lambda: Path(_env("MODELS_DIR", str(ROOT / "models"))))
    docs_dir: Path = field(default_factory=lambda: Path(_env("DOCS_DIR", str(ROOT / "docs"))))
    tz: str = field(default_factory=lambda: _env("TZ", "America/New_York"))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))
    http_timeout: int = field(default_factory=lambda: _env_int("HTTP_TIMEOUT", 20))
    backfill_days: int = field(default_factory=lambda: _env_int("BACKFILL_DAYS", 45))
    bankroll: float = field(default_factory=lambda: _env_float("BANKROLL", 1000.0))
    kelly_fraction: float = field(default_factory=lambda: _env_float("KELLY_FRACTION", 0.25))
    user_agent: str = "pradapicks/0.1 (+https://github.com)"


CFG = Config()


def ensure_dirs() -> None:
    CFG.db_path.parent.mkdir(parents=True, exist_ok=True)
    CFG.models_dir.mkdir(parents=True, exist_ok=True)
    CFG.docs_dir.mkdir(parents=True, exist_ok=True)


SPORTS = ("NBA", "MLB", "NHL", "NFL", "EPL")

# Human-readable league labels for the dashboard.
SPORT_LABELS = {
    "NBA": "NBA Basketball",
    "MLB": "MLB Baseball",
    "NHL": "NHL Hockey",
    "NFL": "NFL Football",
    "EPL": "Soccer (EPL + top leagues)",
}

# Markets we train + price models for. Keep this list explicit — the daily
# pipeline iterates these.
MARKETS = {
    "NBA": (
        "player_points",
        "player_rebounds",
        "player_assists",
        "player_threes",
        "player_steals",
        "player_blocks",
        "player_pra",
    ),
    "MLB": (
        "batter_total_bases",
        "batter_hits",
        "batter_runs",
        "batter_rbis",
        "batter_strikeouts",
        "pitcher_strikeouts",
        "pitcher_outs",
        "pitcher_earned_runs",
    ),
    "NHL": (
        "player_points",
        "player_shots_on_goal",
        "player_goals",
        "player_assists",
        "goalie_saves",
    ),
    "NFL": (
        "player_pass_yards",
        "player_pass_tds",
        "player_pass_completions",
        "player_pass_attempts",
        "player_interceptions",
        "player_rush_yards",
        "player_rush_attempts",
        "player_receptions",
        "player_rec_yards",
    ),
    "EPL": (
        "player_shots",
        "player_shots_on_target",
        "player_goals",
        "player_assists",
        "player_passes",
        "player_tackles",
        "goalie_saves",
    ),
}
