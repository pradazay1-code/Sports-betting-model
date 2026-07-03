"""Config system: loads config/*.yaml with environment overrides.

Secrets (API keys, webhook URLs) come from the environment or a local
.env file — never from committed YAML (spec §7).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"


def _load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader (stdlib only). Existing env vars win."""
    env_file = path or REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


@lru_cache(maxsize=None)
def _load_yaml(name: str) -> dict:
    path = CONFIG_DIR / f"{name}.yaml"
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def settings() -> dict:
    return _load_yaml("settings")


def sources() -> dict:
    return _load_yaml("sources")


def books() -> dict:
    return _load_yaml("books")


def db_path() -> Path:
    """DB location; EDGE_DB_PATH env var overrides settings.yaml."""
    override = os.environ.get("EDGE_DB_PATH")
    if override:
        return Path(override)
    return REPO_ROOT / settings()["paths"]["db"]


def raw_dir() -> Path:
    return REPO_ROOT / settings()["paths"]["raw"]


def odds_api_key() -> str | None:
    _load_dotenv()
    env_name = sources()["odds_api"]["api_key_env"]
    return os.environ.get(env_name) or None


def enabled_sports() -> dict[str, dict]:
    """Sport name -> config, for sports flagged enabled in settings.yaml."""
    return {k: v for k, v in settings()["sports"].items() if v.get("enabled")}
