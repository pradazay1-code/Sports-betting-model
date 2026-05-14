"""Shared HTTP, logging, and small helpers."""

from __future__ import annotations

import logging
import sys
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import CFG


_LOG_INITIALIZED = False


def get_logger(name: str) -> logging.Logger:
    global _LOG_INITIALIZED
    if not _LOG_INITIALIZED:
        logging.basicConfig(
            level=getattr(logging, CFG.log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
            stream=sys.stdout,
        )
        _LOG_INITIALIZED = True
    return logging.getLogger(name)


_LOG = get_logger("http")


def today_local() -> date:
    return datetime.now(ZoneInfo(CFG.tz)).date()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def date_range(start: date, end: date) -> list[date]:
    out = []
    d = start
    while d <= end:
        out.append(d)
        d += timedelta(days=1)
    return out


def to_local(dt_utc: datetime) -> datetime:
    return dt_utc.astimezone(ZoneInfo(CFG.tz))


_TRANSIENT = (httpx.TransportError, httpx.HTTPStatusError)


@retry(
    reraise=True,
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(_TRANSIENT),
)
def http_get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int | None = None,
) -> Any:
    """GET a JSON resource with retries on transient errors.

    On 4xx we do NOT retry — most "no games today" style responses are 404s
    we want to surface immediately."""
    h = {"User-Agent": CFG.user_agent, "Accept": "application/json"}
    if headers:
        h.update(headers)
    t0 = time.monotonic()
    with httpx.Client(timeout=timeout or CFG.http_timeout, follow_redirects=True) as client:
        r = client.get(url, params=params, headers=h)
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    if r.status_code >= 500:
        _LOG.warning("GET %s -> %d (%dms)", url, r.status_code, elapsed_ms)
        r.raise_for_status()
    if r.status_code >= 400:
        _LOG.info("GET %s -> %d (non-retry)", url, r.status_code)
        return None
    _LOG.debug("GET %s -> %d (%dms)", url, r.status_code, elapsed_ms)
    try:
        return r.json()
    except Exception:
        return None


def american_to_decimal(odds: int | float) -> float:
    o = float(odds)
    if o >= 100:
        return 1.0 + o / 100.0
    if o <= -100:
        return 1.0 + 100.0 / abs(o)
    raise ValueError(f"invalid american odds: {odds}")


def american_to_prob(odds: int | float) -> float:
    """Implied probability from American odds — includes vig."""
    return 1.0 / american_to_decimal(odds)


def decimal_to_american(d: float) -> int:
    if d <= 1.0:
        raise ValueError("decimal must be > 1.0")
    if d >= 2.0:
        return int(round((d - 1.0) * 100))
    return int(round(-100.0 / (d - 1.0)))


def safe_get(d: dict, *path, default=None):
    cur: Any = d
    for k in path:
        if cur is None:
            return default
        if isinstance(cur, list):
            try:
                cur = cur[k]
            except (IndexError, TypeError):
                return default
        elif isinstance(cur, dict):
            cur = cur.get(k, default if path[-1] == k else None)
        else:
            return default
    return cur if cur is not None else default
