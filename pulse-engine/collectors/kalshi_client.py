"""Kalshi API client: RSA-signed auth, 15-min crypto market discovery, quote polling.

Auth (Kalshi trade-api v2): each request carries
    KALSHI-ACCESS-KEY:       API key id
    KALSHI-ACCESS-TIMESTAMP: unix epoch milliseconds
    KALSHI-ACCESS-SIGNATURE: base64( RSA-PSS-SHA256( ts + METHOD + path ) )
where `path` includes the /trade-api/v2 prefix but no query string. Market
data endpoints also work unauthenticated (lower rate limits), so the client
degrades gracefully when no key is configured.

Series tickers for the 15-minute up/down markets change occasionally, so
discovery tries config.KALSHI_SERIES_CANDIDATES first, then scans the series
list for crypto series whose open markets have 15-minute durations. If an
asset has no 15-min series (possible for XRP/SOL), it is marked
`no_market` and the engine still predicts — the dashboard says so.
"""
from __future__ import annotations

import asyncio
import base64
import datetime as dt
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
import storage
from engine import window as win

log = logging.getLogger("pulse.kalshi")

_ASSET_KEYWORDS = {
    "BTC": ["BTC", "BITCOIN"], "ETH": ["ETH", "ETHEREUM"],
    "XRP": ["XRP", "RIPPLE"], "SOL": ["SOL", "SOLANA"],
}


def _parse_iso(s: str | None) -> int | None:
    if not s:
        return None
    try:
        return int(dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


@dataclass
class MarketQuote:
    asset: str
    ticker: str
    window_start: int | None
    window_close: int | None
    yes_bid: float | None   # cents
    yes_ask: float | None   # cents
    no_bid: float | None = None
    no_ask: float | None = None
    last_price: float | None = None
    strike_type: str | None = None
    fetched_at: float = 0.0

    @property
    def implied_up(self) -> float | None:
        from engine.edge import implied_from_quotes
        return implied_from_quotes(self.yes_bid, self.yes_ask)


@dataclass
class KalshiCache:
    """Latest quote per asset, read by predictor and dashboard."""
    quotes: dict[str, MarketQuote] = field(default_factory=dict)
    history: dict[str, list[tuple[float, float]]] = field(default_factory=dict)  # asset -> [(ts, implied)]
    status: str = "starting"     # ok | degraded | down | disabled | starting
    no_market: set[str] = field(default_factory=set)
    last_ok: float = 0.0

    def record(self, q: MarketQuote) -> None:
        self.quotes[q.asset] = q
        imp = q.implied_up
        if imp is not None:
            h = self.history.setdefault(q.asset, [])
            h.append((q.fetched_at, imp))
            del h[:-60]
        self.last_ok = time.time()

    def implied_at(self, asset: str, ts: float) -> float | None:
        """Implied prob closest to (and no newer than) `ts` — for drift features."""
        best = None
        for t, p in self.history.get(asset, []):
            if t <= ts:
                best = p
        return best

    def healthy(self) -> bool:
        return self.status == "ok" and time.time() - self.last_ok < 120


class KalshiClient:
    def __init__(self) -> None:
        self.base = config.KALSHI_BASE_URL.rstrip("/")
        self.key_id = config.KALSHI_API_KEY_ID
        self._pkey = None
        if self.key_id and config.KALSHI_PRIVATE_KEY_PATH:
            try:
                from cryptography.hazmat.primitives.serialization import load_pem_private_key
                pem = Path(config.KALSHI_PRIVATE_KEY_PATH).expanduser().read_bytes()
                self._pkey = load_pem_private_key(pem, password=None)
                log.info("Kalshi API key loaded (%s...)", self.key_id[:8])
            except Exception as e:  # noqa: BLE001
                log.error("failed to load Kalshi private key: %s — using unauthenticated access", e)
        self._series: dict[str, str | None] = {}  # asset -> series ticker (None = none found)
        self._session: aiohttp.ClientSession | None = None

    # ------------------------------------------------------------- auth ----

    def _headers(self, method: str, path: str) -> dict[str, str]:
        if not self._pkey:
            return {}
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        ts = str(int(time.time() * 1000))
        msg = f"{ts}{method.upper()}{path.split('?')[0]}".encode()
        sig = self._pkey.sign(
            msg,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
        }

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15))
        url = self.base + path
        full_path = "/trade-api/v2" + path
        async with self._session.get(url, params=params,
                                     headers=self._headers("GET", full_path)) as r:
            if r.status == 429:
                await asyncio.sleep(2)
                raise RuntimeError("rate limited")
            r.raise_for_status()
            return await r.json()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # -------------------------------------------------------- discovery ----

    async def _series_has_15m_markets(self, series_ticker: str) -> bool:
        try:
            data = await self._get("/markets", {
                "series_ticker": series_ticker, "status": "open", "limit": 20})
        except Exception:  # noqa: BLE001
            return False
        for m in data.get("markets", []):
            o, c = _parse_iso(m.get("open_time")), _parse_iso(m.get("close_time"))
            if o and c and c - o <= 20 * 60 and c % 900 == 0:
                return True
        return False

    async def discover_series(self, asset: str) -> str | None:
        """Find the 15-min up/down series ticker for an asset (cached)."""
        if asset in self._series:
            return self._series[asset]
        for cand in config.KALSHI_SERIES_CANDIDATES.get(asset, []):
            if await self._series_has_15m_markets(cand):
                self._series[asset] = cand
                log.info("%s: using Kalshi series %s", asset, cand)
                return cand
        # Fall back to scanning the series catalog for crypto series.
        try:
            data = await self._get("/series", {"category": "Crypto"})
            for s in data.get("series", []):
                tick = s.get("ticker", "")
                title = (s.get("title") or "").upper()
                if not any(k in tick.upper() or k in title
                           for k in _ASSET_KEYWORDS[asset]):
                    continue
                if await self._series_has_15m_markets(tick):
                    self._series[asset] = tick
                    log.info("%s: discovered Kalshi series %s (%s)", asset, tick, title)
                    return tick
        except Exception as e:  # noqa: BLE001
            log.warning("series catalog scan failed: %s", e)
        log.warning("%s: no 15-minute Kalshi series found — predictions will "
                    "run without market prices", asset)
        self._series[asset] = None
        return None

    def forget_series(self, asset: str) -> None:
        self._series.pop(asset, None)

    # ---------------------------------------------------------- markets ----

    async def current_market(self, asset: str, window_close: int) -> MarketQuote | None:
        """The open market for `asset` closing nearest `window_close`.

        Tolerant matching (±150s) instead of exact equality: Kalshi's
        close_time can carry seconds-level offsets from the nominal quarter
        hour, and an exact-match miss silently kills all edge math.
        """
        series = await self.discover_series(asset)
        if not series:
            return None
        data = await self._get("/markets", {
            "series_ticker": series, "status": "open", "limit": 100})
        markets = data.get("markets", [])
        best, best_gap = None, 10 ** 9
        for m in markets:
            c = _parse_iso(m.get("close_time"))
            if c is None:
                continue
            gap = abs(c - window_close)
            if gap < best_gap:
                best, best_gap = m, gap
        if best is None or best_gap > 150:
            closes = sorted(_parse_iso(m.get("close_time")) or 0 for m in markets)[:4]
            log.info("%s: no market near window close %d (nearest closes: %s)",
                     asset, window_close, closes)
            return None
        if best_gap > 0:
            log.debug("%s: matched %s with %ds close offset",
                      asset, best.get("ticker"), best_gap)
        o = _parse_iso(best.get("open_time"))
        return MarketQuote(
            asset=asset, ticker=best.get("ticker", ""),
            window_start=o, window_close=window_close,  # normalized to our window
            yes_bid=best.get("yes_bid"), yes_ask=best.get("yes_ask"),
            no_bid=best.get("no_bid"), no_ask=best.get("no_ask"),
            last_price=best.get("last_price"),
            strike_type=best.get("strike_type") or best.get("market_type"),
            fetched_at=time.time(),
        )


class KalshiPoller:
    """Polls quotes for the current window every KALSHI_POLL_SECONDS."""

    def __init__(self, client: KalshiClient | None = None,
                 cache: KalshiCache | None = None) -> None:
        self.client = client or KalshiClient()
        self.cache = cache or KalshiCache()
        self._stop = asyncio.Event()

    async def poll_once(self) -> None:
        _, close_ts = win.current_window()
        got_any, err_any = False, False
        for asset in config.ASSETS:
            try:
                q = await self.client.current_market(asset, close_ts)
            except Exception as e:  # noqa: BLE001
                err_any = True
                log.warning("%s quote fetch failed: %s", asset, e)
                continue
            if q is None:
                if self.client._series.get(asset) is None:
                    self.cache.no_market.add(asset)
                continue
            self.cache.no_market.discard(asset)
            got_any = True
            self.cache.record(q)
            storage.insert_kalshi_snapshot({
                "ticker": q.ticker, "asset": asset,
                "window_start": q.window_start, "window_close": q.window_close,
                "strike_type": q.strike_type, "yes_bid": q.yes_bid,
                "yes_ask": q.yes_ask, "last_price": q.last_price,
                "fetched_at": int(q.fetched_at),
            })
        self.cache.status = ("ok" if got_any and not err_any
                             else "degraded" if got_any else "down")

    async def run(self) -> None:
        # Re-run discovery each hour in case Kalshi lists/renames series.
        last_discovery_reset = time.time()
        try:
            while not self._stop.is_set():
                try:
                    if time.time() - last_discovery_reset > 3600:
                        self.client._series.clear()
                        last_discovery_reset = time.time()
                    await self.poll_once()
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001
                    self.cache.status = "down"
                    log.warning("kalshi poll error: %s", e)
                try:
                    await asyncio.wait_for(self._stop.wait(), config.KALSHI_POLL_SECONDS)
                except asyncio.TimeoutError:
                    pass
        finally:
            await self.client.close()

    def stop(self) -> None:
        self._stop.set()


async def _verify() -> None:
    """Phase 3 verification: live ticker + quotes + implied prob per asset."""
    storage.init_db()
    poller = KalshiPoller()
    await poller.poll_once()
    for asset in config.ASSETS:
        q = poller.cache.quotes.get(asset)
        if q:
            print(f"{asset}: {q.ticker}  yes {q.yes_bid}/{q.yes_ask}c  "
                  f"implied P(up)={q.implied_up}")
        else:
            print(f"{asset}: no 15-min Kalshi market found")
    await poller.client.close()


if __name__ == "__main__":
    logging.basicConfig(level=config.LOG_LEVEL,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    asyncio.run(_verify())
