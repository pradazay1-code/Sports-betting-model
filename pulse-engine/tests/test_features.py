"""Feature builder: no-lookahead enforcement and basic sanity."""
import numpy as np
import pandas as pd

from engine.features import FEATURE_COLUMNS, build_features


def _make_candles(n: int, start_ts: int, seed: int = 1,
                  base: float = 100.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    closes = base * np.cumprod(1 + rng.normal(0, 0.0005, n))
    opens = np.roll(closes, 1)
    opens[0] = base
    df = pd.DataFrame({
        "open": opens,
        "high": np.maximum(opens, closes) * 1.0002,
        "low": np.minimum(opens, closes) * 0.9998,
        "close": closes,
        "volume": rng.uniform(5, 50, n),
    }, index=[start_ts + 60 * i for i in range(n)])
    return df


START = 1_760_000_400  # aligned: divisible by 900
N = 60 * 48            # 48 hours of 1m candles


def test_future_candles_do_not_change_features():
    candles = _make_candles(N, START)
    at_ts = START + 60 * 60 * 24 + 75   # mid-history prediction time
    past_only = candles[candles.index < at_ts + 3600]  # includes some future rows

    f_full = build_features("BTC", at_ts, candles)
    f_trunc = build_features("BTC", at_ts, past_only)
    assert f_full is not None and f_trunc is not None
    assert f_full == f_trunc, "features leaked information from future candles"


def test_incomplete_current_candle_excluded():
    candles = _make_candles(N, START)
    # at_ts lands 30s into a minute: that minute's candle is not complete yet
    at_ts = START + 60 * 600 + 30
    without_current = candles[candles.index <= at_ts - 60]
    f_a = build_features("BTC", at_ts, candles)
    f_b = build_features("BTC", at_ts, without_current)
    assert f_a == f_b


def test_returns_none_on_stale_data():
    candles = _make_candles(120, START)
    stale_ts = START + 120 * 60 + 3600 * 2  # 2h after the last candle
    assert build_features("BTC", stale_ts, candles) is None


def test_returns_none_on_thin_data():
    candles = _make_candles(20, START)
    assert build_features("BTC", START + 20 * 60 + 75, candles) is None


def test_all_columns_present_and_finite():
    candles = _make_candles(N, START)
    btc = _make_candles(N, START, seed=2)
    at_ts = START + 60 * 60 * 30 + 75
    f = build_features("ETH", at_ts, candles, btc_candles=btc,
                       kalshi_implied=0.53, kalshi_implied_2m_ago=0.51,
                       kalshi_spread=0.02,
                       news={"news_count_60m": 3, "news_sent_60m": 0.2},
                       fng={"value": 61, "change": -3})
    assert f is not None
    assert set(f.keys()) == set(FEATURE_COLUMNS)
    assert all(np.isfinite(v) for v in f.values())
    assert f["kalshi_implied"] == 0.53
    assert abs(f["kalshi_drift_2m"] - 0.02) < 1e-9
    assert f["fng_level"] == 61.0


def test_window_open_to_now_uses_current_window():
    candles = _make_candles(N, START)
    wstart = START + 900 * 40
    at_ts = wstart + 75
    f = build_features("BTC", at_ts, candles)
    # only one completed candle into the window: open-to-now must be small
    assert f is not None and abs(f["win_open_to_now"]) < 0.01
