"""15-minute Kalshi window boundary math.

Kalshi's crypto windows open/close on ET quarter hours (:00, :15, :30, :45).
ET is always a whole-hour offset from UTC, so quarter-hour boundaries in ET
coincide with quarter-hour boundaries in UTC — flooring the UTC epoch to 900s
is exact through DST transitions. Display formatting converts to ET.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import config

WINDOW = config.WINDOW_SECONDS  # 900


def window_bounds(ts: float | None = None) -> tuple[int, int]:
    """(start, close) UTC epoch seconds of the window containing `ts`."""
    t = int(ts if ts is not None else time.time())
    start = t - (t % WINDOW)
    return start, start + WINDOW


def current_window(ts: float | None = None) -> tuple[int, int]:
    return window_bounds(ts)


def previous_window(ts: float | None = None) -> tuple[int, int]:
    start, _ = window_bounds(ts)
    return start - WINDOW, start


def seconds_to_close(ts: float | None = None) -> float:
    t = ts if ts is not None else time.time()
    _, close = window_bounds(t)
    return close - t


def prediction_time(window_start: int) -> int:
    """UTC epoch second at which the prediction for a window is made."""
    return window_start + config.PREDICTION_DELAY_SECONDS


def et_label(ts: int, fmt: str = "%-I:%M%p") -> str:
    """Format a UTC epoch second as an ET wall-clock label like '3:45PM'."""
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(config.TZ)
    try:
        return dt.strftime(fmt).lower().lstrip("0")
    except ValueError:  # platform without %-I
        return dt.strftime("%I:%M%p").lower().lstrip("0")


def et_datetime(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(config.TZ)


def iter_window_starts(start_ts: int, end_ts: int) -> list[int]:
    """All window starts s with start_ts <= s and s+WINDOW <= end_ts."""
    first = start_ts + (-start_ts) % WINDOW  # ceil to boundary
    return list(range(first, end_ts - WINDOW + 1, WINDOW))
