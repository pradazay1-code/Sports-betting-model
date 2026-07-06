"""Live price collector: websocket 1m klines -> candles table + tick cache.

Primary source is the Binance(.us) combined kline stream; fallback is the
Coinbase matches feed aggregated into 1m candles locally. Reconnects with
exponential backoff and gap-fills missed minutes via ccxt REST on reconnect.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
import storage

log = logging.getLogger("pulse.prices")

_STALE_AFTER = 60  # seconds without a message before the watchdog reconnects


@dataclass
class Tick:
    price: float = 0.0
    ts: float = 0.0


@dataclass
class LatestCache:
    """In-memory latest-tick cache the dashboard and predictor read."""
    ticks: dict[str, Tick] = field(default_factory=dict)
    source: str = ""
    connected: bool = False

    def update(self, asset: str, price: float, ts: float | None = None) -> None:
        self.ticks[asset] = Tick(price=price, ts=ts or time.time())

    def get(self, asset: str) -> Tick | None:
        return self.ticks.get(asset)

    def stale_seconds(self) -> float:
        if not self.ticks:
            return float("inf")
        return time.time() - max(t.ts for t in self.ticks.values())

    def healthy(self) -> bool:
        return self.connected and self.stale_seconds() < config.MAX_DATA_STALENESS_SECONDS


class PriceCollector:
    def __init__(self, cache: LatestCache | None = None):
        self.cache = cache or LatestCache()
        self._stop = asyncio.Event()
        self._last_msg = 0.0

    # ------------------------------------------------------------ binance --

    def _binance_url(self, host_key: str) -> str:
        streams = "/".join(
            config.SYMBOLS[host_key][a].replace("/", "").lower() + "@kline_1m"
            for a in config.ASSETS)
        return f"{config.BINANCE_WS_HOSTS[host_key]}/stream?streams={streams}"

    def _binance_asset(self, host_key: str, stream_symbol: str) -> str | None:
        for a in config.ASSETS:
            if config.SYMBOLS[host_key][a].replace("/", "").lower() == stream_symbol:
                return a
        return None

    async def _run_binance(self, host_key: str) -> None:
        url = self._binance_url(host_key)
        async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
            self.cache.source, self.cache.connected = host_key, True
            log.info("connected to %s kline stream", host_key)
            async for raw in ws:
                self._last_msg = time.time()
                msg = json.loads(raw)
                k = msg.get("data", {}).get("k")
                if not k:
                    continue
                asset = self._binance_asset(host_key, k["s"].lower())
                if not asset:
                    continue
                self.cache.update(asset, float(k["c"]))
                if k.get("x"):  # candle closed — persist it
                    storage.upsert_candles([{
                        "asset": asset, "ts": int(k["t"] // 1000),
                        "open": float(k["o"]), "high": float(k["h"]),
                        "low": float(k["l"]), "close": float(k["c"]),
                        "volume": float(k["v"]), "source": host_key,
                    }])
                if self._stop.is_set():
                    return

    # ----------------------------------------------------------- coinbase --

    async def _run_coinbase(self) -> None:
        product_by_asset = {a: config.SYMBOLS["coinbase"][a].replace("/", "-")
                            for a in config.ASSETS}
        asset_by_product = {v: k for k, v in product_by_asset.items()}
        sub = {"type": "subscribe", "product_ids": list(product_by_asset.values()),
               "channels": ["matches", "heartbeat"]}
        # local 1m aggregation: asset -> [minute_ts, o, h, l, c, vol]
        building: dict[str, list] = {}

        def flush(asset: str) -> None:
            b = building.pop(asset, None)
            if b:
                storage.upsert_candles([{
                    "asset": asset, "ts": b[0], "open": b[1], "high": b[2],
                    "low": b[3], "close": b[4], "volume": b[5], "source": "coinbase"}])

        async with websockets.connect(config.COINBASE_WS_URL, ping_interval=20) as ws:
            await ws.send(json.dumps(sub))
            self.cache.source, self.cache.connected = "coinbase", True
            log.info("connected to coinbase matches feed")
            async for raw in ws:
                self._last_msg = time.time()
                msg = json.loads(raw)
                if msg.get("type") != "match":
                    continue
                asset = asset_by_product.get(msg.get("product_id", ""))
                if not asset:
                    continue
                price, size = float(msg["price"]), float(msg["size"])
                self.cache.update(asset, price)
                minute = int(time.time()) // 60 * 60
                b = building.get(asset)
                if b is None or b[0] != minute:
                    flush(asset)
                    building[asset] = [minute, price, price, price, price, size]
                else:
                    b[2] = max(b[2], price)
                    b[3] = min(b[3], price)
                    b[4] = price
                    b[5] += size
                if self._stop.is_set():
                    for a in list(building):
                        flush(a)
                    return

    # ---------------------------------------------------------- gap fill ---

    def _gap_fill(self) -> None:
        """REST-fetch any minutes missed while disconnected (sync, small)."""
        try:
            from collectors.history_backfill import backfill_asset, working_exchange
            ex = working_exchange()
            for asset in config.ASSETS:
                last = storage.latest_candle_ts(asset)
                gap_days = (time.time() - last) / 86400 if last else 1
                backfill_asset(ex, asset, days=min(max(gap_days + 0.01, 0.02), 2))
        except Exception as e:  # noqa: BLE001 — gap fill is best-effort
            log.warning("gap fill failed: %s", e)

    # -------------------------------------------------------------- main ---

    async def run(self) -> None:
        """Connect, stream, reconnect forever with exponential backoff."""
        sources = []
        if config.EXCHANGE_ID in config.BINANCE_WS_HOSTS:
            sources.append(config.EXCHANGE_ID)
        sources += [s for s in ("binanceus", "binance") if s not in sources]
        sources.append("coinbase")

        backoff = 1.0
        while not self._stop.is_set():
            for src in sources:
                if self._stop.is_set():
                    return
                try:
                    await asyncio.to_thread(self._gap_fill)
                    self._last_msg = time.time()
                    runner = (self._run_coinbase() if src == "coinbase"
                              else self._run_binance(src))
                    watchdog = asyncio.create_task(self._watchdog())
                    try:
                        await runner
                    finally:
                        watchdog.cancel()
                    backoff = 1.0
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001 — reconnect loop
                    self.cache.connected = False
                    log.warning("%s stream dropped (%s); retry in %.0fs", src, e, backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60)

    async def _watchdog(self) -> None:
        while True:
            await asyncio.sleep(10)
            if self._last_msg and time.time() - self._last_msg > _STALE_AFTER:
                log.warning("no ws messages for %ds — forcing reconnect", _STALE_AFTER)
                raise RuntimeError("stale websocket")

    def stop(self) -> None:
        self._stop.set()


async def _verify(minutes: int = 3) -> None:
    """Phase 2 verification: run for N minutes, then check for gaps."""
    storage.init_db()
    col = PriceCollector()
    task = asyncio.create_task(col.run())
    t0 = int(time.time())
    await asyncio.sleep(minutes * 60)
    col.stop()
    task.cancel()
    for asset in config.ASSETS:
        df = storage.get_candles(asset, t0 - 60, int(time.time()))
        gaps = 0
        ts = list(df.index)
        for a, b in zip(ts, ts[1:]):
            gaps += (b - a) // 60 - 1
        tick = col.cache.get(asset)
        print(f"{asset}: {len(df)} new candles, {gaps} gaps, last tick "
              f"{tick.price if tick else 'n/a'}")


if __name__ == "__main__":
    logging.basicConfig(level=config.LOG_LEVEL,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    asyncio.run(_verify())
