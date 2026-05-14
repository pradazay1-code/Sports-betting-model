from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./pradapicks.db"
    odds_api_key: str = ""
    api_auth_token: str = "dev-token"
    run_scheduler: bool = True
    log_level: str = "INFO"
    tz: str = "America/New_York"

    artifacts_dir: Path = Path("models_artifacts")

    daily_pick_count: int = 25
    sports: tuple[str, ...] = ("MLB", "NBA", "NHL")
    auto_bootstrap_days: int = 30

    odds_regions: str = "us"
    odds_books: tuple[str, ...] = ("draftkings", "fanduel", "betmgm", "caesars")

    min_edge_pct: float = 2.0
    kelly_fraction: float = 0.25


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.artifacts_dir.mkdir(parents=True, exist_ok=True)
    return s
