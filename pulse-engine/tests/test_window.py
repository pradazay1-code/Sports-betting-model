"""Window-boundary math, including DST transitions."""
from datetime import datetime, timezone

import config
from engine import window as win


def _ts(y, mo, d, h, mi, s=0):
    return int(datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc).timestamp())


def test_bounds_align_to_quarter_hours():
    t = _ts(2026, 7, 6, 14, 7, 33)
    start, close = win.window_bounds(t)
    assert start % 900 == 0 and close - start == 900
    assert start <= t < close


def test_exact_boundary_belongs_to_new_window():
    t = _ts(2026, 7, 6, 14, 15, 0)
    start, close = win.window_bounds(t)
    assert start == t and close == t + 900


def test_et_alignment_year_round():
    # ET is always a whole-hour UTC offset, so every window boundary must
    # land on :00/:15/:30/:45 ET — including across both DST transitions.
    for probe in [_ts(2026, 3, 8, 6, 59), _ts(2026, 3, 8, 7, 1),   # spring fwd
                  _ts(2026, 11, 1, 5, 59), _ts(2026, 11, 1, 6, 1),  # fall back
                  _ts(2026, 7, 6, 12, 0), _ts(2026, 1, 15, 23, 44)]:
        start, close = win.window_bounds(probe)
        for b in (start, close):
            et = datetime.fromtimestamp(b, tz=timezone.utc).astimezone(config.TZ)
            assert et.minute in (0, 15, 30, 45) and et.second == 0


def test_seconds_to_close_and_prediction_time():
    t = _ts(2026, 7, 6, 14, 0, 10)
    assert win.seconds_to_close(t) == 890
    start, _ = win.window_bounds(t)
    assert win.prediction_time(start) == start + config.PREDICTION_DELAY_SECONDS


def test_iter_window_starts():
    t0 = _ts(2026, 7, 6, 14, 3)
    t1 = _ts(2026, 7, 6, 15, 3)
    starts = win.iter_window_starts(t0, t1)
    assert starts == [_ts(2026, 7, 6, 14, 15), _ts(2026, 7, 6, 14, 30),
                      _ts(2026, 7, 6, 14, 45)]
    assert all(s % 900 == 0 for s in starts)
