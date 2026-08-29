"""
TTL-based JSON cache on disk.

Every network call in this repo goes through here. The point is not speed — it's
that The Odds API free tier is 500 requests a month and a careless loop burns it
in an afternoon. Cache lives in `data/cache/`, which is gitignored.

Entries carry their own fetch timestamp, so a stale hit can still be *served*
with an explicit staleness warning rather than silently returned as fresh. That
matters: a 40-minute-old line served as current is exactly the kind of quiet
error that produces a confidently wrong recommendation.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = Path(os.environ.get("DESK_CACHE_DIR", REPO_ROOT / "data" / "cache"))

# Defaults in seconds. Odds move; season-long stats don't.
DEFAULT_TTLS = {
    "odds": int(os.environ.get("CACHE_TTL_ODDS", 300)),        # 5 min
    "stats": int(os.environ.get("CACHE_TTL_STATS", 21600)),    # 6 h
    "news": int(os.environ.get("CACHE_TTL_NEWS", 900)),        # 15 min
    "weather": int(os.environ.get("CACHE_TTL_WEATHER", 3600)),  # 1 h
    "static": 86400 * 7,                                        # schedules, park factors
}


@dataclass
class CacheEntry:
    value: Any
    fetched_at: float
    age: float
    stale: bool
    key: str

    @property
    def age_str(self) -> str:
        if self.age < 90:
            return f"{self.age:.0f}s"
        if self.age < 5400:
            return f"{self.age / 60:.0f}m"
        return f"{self.age / 3600:.1f}h"


def _path_for(namespace: str, key: str) -> Path:
    digest = hashlib.sha256(key.encode()).hexdigest()[:20]
    return CACHE_DIR / namespace / f"{digest}.json"


def read(namespace: str, key: str, ttl: float | None = None) -> CacheEntry | None:
    """Return the entry if present. `stale` is set when it's past its TTL."""
    ttl = DEFAULT_TTLS.get(namespace, 300) if ttl is None else ttl
    path = _path_for(namespace, key)
    if not path.exists():
        return None
    try:
        blob = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    fetched_at = blob.get("_fetched_at", 0.0)
    age = time.time() - fetched_at
    return CacheEntry(
        value=blob.get("value"),
        fetched_at=fetched_at,
        age=age,
        stale=age > ttl,
        key=key,
    )


def write(namespace: str, key: str, value: Any) -> None:
    path = _path_for(namespace, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"_fetched_at": time.time(), "key": key, "value": value}))
    tmp.replace(path)  # atomic, so a killed process can't leave a half-written entry


def get_or_fetch(
    namespace: str,
    key: str,
    fetcher: Callable[[], Any],
    *,
    ttl: float | None = None,
    allow_stale_on_error: bool = True,
) -> tuple[Any, dict]:
    """
    Cache-through fetch.

    Returns `(value, meta)`. `meta` always says where the value came from and how
    old it is, and the caller is expected to surface that — a recommendation
    built on a stale board should say the board is stale.

    On a fetch failure with a stale entry available, we serve the stale entry and
    mark `meta["degraded"]`. That is a deliberate choice: stale-and-labeled beats
    nothing, and both beat a fabricated number. If there's no cached fallback the
    error propagates — we never invent one.
    """
    entry = read(namespace, key, ttl)
    if entry and not entry.stale:
        return entry.value, {
            "source": "cache",
            "age_seconds": entry.age,
            "age": entry.age_str,
            "stale": False,
            "degraded": False,
        }

    try:
        value = fetcher()
    except Exception as exc:  # noqa: BLE001 — we re-raise unless we have a fallback
        if entry and allow_stale_on_error:
            return entry.value, {
                "source": "cache",
                "age_seconds": entry.age,
                "age": entry.age_str,
                "stale": True,
                "degraded": True,
                "error": f"{type(exc).__name__}: {exc}",
                "warning": (
                    f"live fetch failed; serving a {entry.age_str}-old cached copy. "
                    "Treat prices as indicative, not current."
                ),
            }
        raise

    write(namespace, key, value)
    return value, {"source": "live", "age_seconds": 0.0, "age": "0s", "stale": False, "degraded": False}


def purge(namespace: str | None = None, older_than: float | None = None) -> int:
    """Delete cache files. Returns how many went."""
    root = CACHE_DIR / namespace if namespace else CACHE_DIR
    if not root.exists():
        return 0
    n = 0
    cutoff = time.time() - older_than if older_than else None
    for f in root.rglob("*.json"):
        if cutoff is not None and f.stat().st_mtime > cutoff:
            continue
        f.unlink()
        n += 1
    return n


def stats() -> dict:
    """What's in the cache right now, by namespace."""
    if not CACHE_DIR.exists():
        return {}
    out: dict[str, dict] = {}
    for ns_dir in sorted(p for p in CACHE_DIR.iterdir() if p.is_dir()):
        files = list(ns_dir.glob("*.json"))
        if not files:
            continue
        ages = [time.time() - f.stat().st_mtime for f in files]
        out[ns_dir.name] = {
            "entries": len(files),
            "bytes": sum(f.stat().st_size for f in files),
            "oldest_age_s": max(ages),
            "newest_age_s": min(ages),
            "ttl_s": DEFAULT_TTLS.get(ns_dir.name),
        }
    return out


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "purge":
        print(f"purged {purge(sys.argv[2] if len(sys.argv) > 2 else None)} entries")
    else:
        s = stats()
        if not s:
            print("cache empty")
        for ns, info in s.items():
            print(f"{ns:<10} {info['entries']:>4} entries  {info['bytes'] / 1024:>7.1f} KB  "
                  f"oldest {info['oldest_age_s'] / 60:.0f}m  ttl {info['ttl_s']}s")
