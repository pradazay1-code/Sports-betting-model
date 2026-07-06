"""Feature engineering for 15-minute direction prediction.

`build_features` is the single code path used by training, backtest and the
live predictor. No-lookahead is enforced *inside* the builder: only candles
that are fully closed at `at_ts` (candle start + 60 <= at_ts) are used, no
matter what the caller passes in. Live-only inputs (latest tick, Kalshi
quotes, news, Fear & Greed) arrive as explicit arguments and default to
neutral values so historical training rows are computed identically.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import config

# Canonical feature order — models are trained and served against this list.
FEATURE_COLUMNS: list[str] = [
    "ret_1m", "ret_3m", "ret_5m", "ret_15m", "ret_30m", "ret_60m",
    "win_open_to_now",
    "ema_spread", "rsi_14", "macd_hist",
    "rvol_30m", "vol_regime",
    "vwap_dist", "dist_4h_high", "dist_4h_low",
    "body_1", "body_2", "body_3", "consec_updown",
    "vol_zscore",
    "btc_ret_5m", "btc_corr_1h",
    "hour_sin", "hour_cos", "dow",
    "us_open_prox", "us_close_prox",
    "fng_level", "fng_change",
    "news_count_60m", "news_hi_count_60m", "news_sent_60m", "news_breaking",
    "kalshi_implied", "kalshi_drift_2m", "kalshi_spread",
]


def _completed(candles: pd.DataFrame, at_ts: int) -> pd.DataFrame:
    """Rows fully closed at `at_ts` (the no-lookahead gate)."""
    if candles is None or candles.empty:
        return pd.DataFrame()
    cutoff = at_ts - 60
    pos = candles.index.searchsorted(cutoff, side="right")
    return candles.iloc[:pos]


def _ret(closes: np.ndarray, k: int) -> float:
    if len(closes) <= k or closes[-1 - k] == 0:
        return 0.0
    return float(closes[-1] / closes[-1 - k] - 1.0)


def _ema(x: np.ndarray, span: int) -> float:
    if len(x) == 0:
        return 0.0
    return float(pd.Series(x).ewm(span=span, adjust=False).mean().iloc[-1])


def _rsi(closes: np.ndarray, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    delta = np.diff(closes[-(period * 3 + 1):])
    up = np.where(delta > 0, delta, 0.0)
    dn = np.where(delta < 0, -delta, 0.0)
    ru = pd.Series(up).ewm(alpha=1 / period, adjust=False).mean().iloc[-1]
    rd = pd.Series(dn).ewm(alpha=1 / period, adjust=False).mean().iloc[-1]
    if rd == 0:
        return 100.0 if ru > 0 else 50.0
    return float(100.0 - 100.0 / (1.0 + ru / rd))


def _macd_hist(closes: np.ndarray) -> float:
    if len(closes) < 35:
        return 0.0
    s = pd.Series(closes[-120:])
    macd = s.ewm(span=12, adjust=False).mean() - s.ewm(span=26, adjust=False).mean()
    hist = macd - macd.ewm(span=9, adjust=False).mean()
    px = closes[-1] or 1.0
    return float(hist.iloc[-1] / px)


def _et(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(config.TZ)


def _minutes_to(ts: int, hh: int, mm: int) -> float:
    """|minutes| from ET wall time hh:mm, scaled to a 0-1 proximity score."""
    d = _et(ts)
    mins = abs((d.hour * 60 + d.minute) - (hh * 60 + mm))
    mins = min(mins, 1440 - mins)
    return max(0.0, 1.0 - mins / 60.0)  # 1 at the bell, 0 beyond an hour


def build_features(
    asset: str,
    at_ts: int,
    candles: pd.DataFrame,
    btc_candles: pd.DataFrame | None = None,
    live_price: float | None = None,
    kalshi_implied: float | None = None,
    kalshi_implied_2m_ago: float | None = None,
    kalshi_spread: float | None = None,
    news: dict[str, float] | None = None,
    fng: dict | None = None,
) -> dict[str, float] | None:
    """Feature dict for `asset` as of `at_ts` (UTC epoch s), or None if the
    data is too thin/stale to predict from honestly."""
    df = _completed(candles, at_ts)
    if len(df) < 60:
        return None
    last_ts = int(df.index[-1])
    if at_ts - last_ts > config.MAX_DATA_STALENESS_SECONDS + 60:
        return None  # stale feed — refuse to fabricate

    closes = df["close"].to_numpy(dtype=float)
    now_price = float(live_price) if live_price else float(closes[-1])

    # Current 15-min window open: first candle open at/after the boundary,
    # else the last close before it.
    wstart = at_ts - (at_ts % config.WINDOW_SECONDS)
    pos = df.index.searchsorted(wstart, side="left")
    if pos < len(df) and df.index[pos] < wstart + config.WINDOW_SECONDS:
        win_open = float(df.iloc[pos]["open"])
    else:
        win_open = float(closes[-1])

    f: dict[str, float] = {}
    for k, name in ((1, "ret_1m"), (3, "ret_3m"), (5, "ret_5m"),
                    (15, "ret_15m"), (30, "ret_30m"), (60, "ret_60m")):
        f[name] = _ret(closes, k)
    f["win_open_to_now"] = now_price / win_open - 1.0 if win_open else 0.0

    ema5, ema20 = _ema(closes[-60:], 5), _ema(closes[-60:], 20)
    f["ema_spread"] = (ema5 - ema20) / ema20 if ema20 else 0.0
    f["rsi_14"] = _rsi(closes)
    f["macd_hist"] = _macd_hist(closes)

    rets_1m = pd.Series(closes).pct_change().to_numpy()[1:]
    rv30 = float(np.std(rets_1m[-30:])) if len(rets_1m) >= 10 else 0.0
    f["rvol_30m"] = rv30
    if len(rets_1m) >= 120:
        trailing = pd.Series(rets_1m[-240:]).rolling(30).std().dropna()
        med = float(trailing.median()) if len(trailing) else 0.0
        f["vol_regime"] = rv30 / med - 1.0 if med > 0 else 0.0
    else:
        f["vol_regime"] = 0.0

    # Session VWAP since ET midnight.
    et_now = _et(at_ts)
    midnight_et = et_now.replace(hour=0, minute=0, second=0, microsecond=0)
    sess_start = int(midnight_et.timestamp())
    sess = df.iloc[df.index.searchsorted(sess_start, side="left"):]
    vol = sess["volume"].to_numpy(dtype=float)
    if len(sess) and vol.sum() > 0:
        vwap = float((sess["close"].to_numpy() * vol).sum() / vol.sum())
        f["vwap_dist"] = now_price / vwap - 1.0
    else:
        f["vwap_dist"] = 0.0

    last4h = df.iloc[df.index.searchsorted(at_ts - 4 * 3600, side="left"):]
    hi = float(last4h["high"].max()) if len(last4h) else now_price
    lo = float(last4h["low"].min()) if len(last4h) else now_price
    f["dist_4h_high"] = now_price / hi - 1.0 if hi else 0.0
    f["dist_4h_low"] = now_price / lo - 1.0 if lo else 0.0

    for i, name in ((1, "body_1"), (2, "body_2"), (3, "body_3")):
        if len(df) >= i:
            r = df.iloc[-i]
            rng = float(r["high"] - r["low"])
            f[name] = float(r["close"] - r["open"]) / rng if rng > 0 else 0.0
        else:
            f[name] = 0.0

    consec, sign0 = 0, 0
    for i in range(1, min(len(df), 20) + 1):
        r = df.iloc[-i]
        s = 1 if r["close"] > r["open"] else (-1 if r["close"] < r["open"] else 0)
        if i == 1:
            sign0 = s
        if s == 0 or s != sign0:
            break
        consec += 1
    f["consec_updown"] = float(consec * sign0)

    # Volume z-score vs the same minute-of-day over the trailing ~30 days.
    mod = last_ts % 86400
    same_min = df["volume"].to_numpy(dtype=float)[
        (df.index.to_numpy() % 86400) == mod][-31:-1]
    v_now = float(df.iloc[-1]["volume"])
    if len(same_min) >= 5 and np.std(same_min) > 0:
        f["vol_zscore"] = float((v_now - np.mean(same_min)) / np.std(same_min))
    else:
        f["vol_zscore"] = 0.0

    # Cross-asset: BTC leads.
    if asset == "BTC":
        f["btc_ret_5m"], f["btc_corr_1h"] = f["ret_5m"], 1.0
    else:
        bdf = _completed(btc_candles, at_ts) if btc_candles is not None else pd.DataFrame()
        if len(bdf) >= 61:
            bcl = bdf["close"].to_numpy(dtype=float)
            f["btc_ret_5m"] = _ret(bcl, 5)
            a = pd.Series(closes[-61:]).pct_change().dropna()
            b = pd.Series(bcl[-61:]).pct_change().dropna()
            n = min(len(a), len(b))
            if n >= 30 and a.tail(n).std() > 0 and b.tail(n).std() > 0:
                f["btc_corr_1h"] = float(np.corrcoef(a.tail(n), b.tail(n))[0, 1])
            else:
                f["btc_corr_1h"] = 0.0
        else:
            f["btc_ret_5m"], f["btc_corr_1h"] = 0.0, 0.0

    frac = (et_now.hour + et_now.minute / 60.0) / 24.0
    f["hour_sin"] = math.sin(2 * math.pi * frac)
    f["hour_cos"] = math.cos(2 * math.pi * frac)
    f["dow"] = float(et_now.weekday())
    f["us_open_prox"] = _minutes_to(at_ts, 9, 30)
    f["us_close_prox"] = _minutes_to(at_ts, 16, 0)

    fng = fng or {}
    f["fng_level"] = float(fng.get("value", 50))
    f["fng_change"] = float(fng.get("change", 0))

    news = news or {}
    f["news_count_60m"] = float(news.get("news_count_60m", 0.0))
    f["news_hi_count_60m"] = float(news.get("news_hi_count_60m", 0.0))
    f["news_sent_60m"] = float(news.get("news_sent_60m", 0.0))
    f["news_breaking"] = float(news.get("news_breaking", 0.0))

    f["kalshi_implied"] = float(kalshi_implied) if kalshi_implied is not None else 0.5
    if kalshi_implied is not None and kalshi_implied_2m_ago is not None:
        f["kalshi_drift_2m"] = float(kalshi_implied - kalshi_implied_2m_ago)
    else:
        f["kalshi_drift_2m"] = 0.0
    f["kalshi_spread"] = float(kalshi_spread) if kalshi_spread is not None else 0.02

    out = {}
    for c in FEATURE_COLUMNS:
        v = f.get(c, 0.0)
        out[c] = 0.0 if v is None or not math.isfinite(v) else round(float(v), 8)
    return out


def to_vector(feats: dict[str, float]) -> np.ndarray:
    return np.array([feats[c] for c in FEATURE_COLUMNS], dtype=float)
