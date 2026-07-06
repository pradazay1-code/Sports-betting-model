"""Historical 1-minute candle backfill via ccxt REST.

Pulls >= BACKFILL_DAYS days of 1m candles for every asset, paginating and
respecting the exchange rate limit. Resume-safe: restarts from the newest
stored candle, and the UNIQUE(asset, ts) constraint absorbs overlap.

Run directly for the Phase 1 verification report:
    python collectors/history_backfill.py
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import ccxt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
import storage
from engine import window as win

log = logging.getLogger("pulse.backfill")

_MS = 1000
_BATCH = 1000  # candles per REST page (most venues cap at 1000/720)


def make_exchange(exchange_id: str | None = None) -> ccxt.Exchange:
    ex_id = exchange_id or config.EXCHANGE_ID
    ex = getattr(ccxt, ex_id)({"enableRateLimit": True})
    ex.load_markets()
    return ex


def working_exchange() -> ccxt.Exchange:
    """First exchange (preferred, then fallbacks) that answers and lists BTC."""
    last_err: Exception | None = None
    for ex_id in [config.EXCHANGE_ID, *config.EXCHANGE_FALLBACKS]:
        if ex_id not in config.SYMBOLS:
            continue
        try:
            ex = make_exchange(ex_id)
            sym = config.SYMBOLS[ex_id]["BTC"]
            ex.fetch_ohlcv(sym, "1m", limit=2)
            log.info("using exchange %s", ex_id)
            return ex
        except Exception as e:  # noqa: BLE001 — try the next venue
            last_err = e
            log.warning("exchange %s unusable: %s", ex_id, e)
    raise RuntimeError(f"no usable exchange (last error: {last_err})")


def backfill_asset(ex: ccxt.Exchange, asset: str, days: int | None = None) -> int:
    """Fetch candles from max(newest stored, now - days) to now. Returns rows written."""
    days = days or config.BACKFILL_DAYS
    symbol = config.SYMBOLS[ex.id][asset]
    now_ms = ex.milliseconds()
    since_ms = now_ms - days * 86400 * _MS
    resume = storage.latest_candle_ts(asset)
    if resume is not None:
        since_ms = max(since_ms, (resume + 60) * _MS)

    written = 0
    while since_ms < now_ms:
        try:
            batch = ex.fetch_ohlcv(symbol, "1m", since=since_ms, limit=_BATCH)
        except (ccxt.NetworkError, ccxt.ExchangeNotAvailable) as e:
            log.warning("%s fetch error (%s); backing off 10s", asset, e)
            time.sleep(10)
            continue
        if not batch:
            break
        rows = [
            {"asset": asset, "ts": int(o[0] // _MS), "open": o[1], "high": o[2],
             "low": o[3], "close": o[4], "volume": o[5] or 0.0, "source": ex.id}
            for o in batch if o[1] is not None
        ]
        written += storage.upsert_candles(rows)
        last_ms = batch[-1][0]
        if last_ms <= since_ms - 60 * _MS:  # no forward progress
            break
        since_ms = last_ms + 60 * _MS
        time.sleep(max(ex.rateLimit, 100) / 1000.0)
    log.info("%s: wrote %d candles (total %d)", asset, written, storage.candle_count(asset))
    return written


def backfill_all(days: int | None = None) -> ccxt.Exchange:
    storage.init_db()
    ex = working_exchange()
    for asset in config.ASSETS:
        backfill_asset(ex, asset, days)
    return ex


# ---------------------------------------------------------------- labels ----

def resample_15m(asset: str, start_ts: int | None = None,
                 end_ts: int | None = None) -> pd.DataFrame:
    """15-minute windows aligned to Kalshi boundaries, built from 1m candles.

    Columns: open, close, high, low, volume, ret, direction (1 up / 0 down /
    NaN flat-or-missing). Index = window_start (UTC epoch s). Windows missing
    >5 of their 15 minutes are dropped rather than guessed at.
    """
    start_ts = start_ts or (int(time.time()) - config.BACKFILL_DAYS * 86400)
    df = storage.get_candles(asset, start_ts, end_ts)
    if df.empty:
        return pd.DataFrame()
    idx = pd.to_datetime(df.index, unit="s", utc=True)
    g = df.set_index(idx).resample("15min", label="left", closed="left")
    out = pd.DataFrame({
        "open": g["open"].first(), "close": g["close"].last(),
        "high": g["high"].max(), "low": g["low"].min(),
        "volume": g["volume"].sum(), "minutes": g["close"].count(),
    }).dropna(subset=["open", "close"])
    out = out[out["minutes"] >= 10]
    # unit-independent epoch-seconds conversion (datetime64 resolution varies)
    out.index = ((out.index - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(seconds=1)).astype("int64")
    out["ret"] = out["close"] / out["open"] - 1.0
    flat = out["ret"].abs() < config.FLAT_WINDOW_BPS / 10_000.0
    out["direction"] = (out["ret"] > 0).astype(float)
    out.loc[flat, "direction"] = float("nan")
    return out


def verification_report() -> None:
    print(f"{'asset':<6} {'1m rows':>9} {'15m wins':>9} {'%UP':>6}   last 5 windows (ET, dir)")
    for asset in config.ASSETS:
        wins = resample_15m(asset)
        n1 = storage.candle_count(asset)
        if wins.empty:
            print(f"{asset:<6} {n1:>9} {'-':>9} {'-':>6}   no data")
            continue
        labeled = wins.dropna(subset=["direction"])
        pct_up = 100.0 * labeled["direction"].mean() if len(labeled) else float("nan")
        tail = wins.tail(5)
        lbl = ", ".join(
            f"{win.et_label(int(ts))}={'UP' if r.direction == 1 else ('DOWN' if r.direction == 0 else 'FLAT')}"
            for ts, r in tail.iterrows())
        print(f"{asset:<6} {n1:>9} {len(wins):>9} {pct_up:>5.1f}%   {lbl}")


if __name__ == "__main__":
    logging.basicConfig(level=config.LOG_LEVEL, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    backfill_all()
    verification_report()
