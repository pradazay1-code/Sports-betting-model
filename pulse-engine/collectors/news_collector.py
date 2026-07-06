"""Crypto news collector: CryptoPanic + RSS fallback, dedup, lexicon sentiment.

News is a secondary signal at the 15-minute horizon; this stays deliberately
simple. feedparser is used when installed; otherwise a small stdlib XML
parser handles the RSS fallback so the system still runs.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
import storage

try:
    import feedparser  # type: ignore
except ImportError:
    feedparser = None

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _vader = SentimentIntensityAnalyzer()
except ImportError:
    _vader = None

log = logging.getLogger("pulse.news")

_ASSET_WORDS = {
    "BTC": ["btc", "bitcoin"],
    "ETH": ["eth", "ethereum", "ether "],
    "XRP": ["xrp", "ripple"],
    "SOL": ["sol ", "solana", "$sol"],
}
_BREAKING_WORDS = ("breaking", "urgent", "hack", "exploit", "sec ", "etf",
                   "halt", "bankrupt", "liquidat", "crash", "flash")


def _hash_id(url: str, title: str) -> str:
    return hashlib.sha1((url or title).encode()).hexdigest()


def tag_assets(text: str) -> list[str]:
    t = f" {text.lower()} "
    return [a for a, words in _ASSET_WORDS.items() if any(w in t for w in words)]


def score_sentiment(title: str) -> float:
    if _vader is None:
        return 0.0
    return float(_vader.polarity_scores(title)["compound"])


def importance(source_weight: float, ts: int, votes: float = 0.0) -> float:
    age_h = max((time.time() - ts) / 3600.0, 0.0)
    recency = max(0.0, 1.0 - age_h / 24.0)
    return round(source_weight * recency * (1.0 + min(votes, 50) / 25.0), 3)


@dataclass
class NewsCache:
    status: str = "starting"      # ok | degraded | down | starting
    last_ok: float = 0.0
    fng: dict = field(default_factory=dict)   # {"value": int, "change": int}

    def healthy(self) -> bool:
        return self.status in ("ok", "degraded") and time.time() - self.last_ok < 900


class NewsCollector:
    def __init__(self, cache: NewsCache | None = None) -> None:
        self.cache = cache or NewsCache()
        self._stop = asyncio.Event()

    async def _fetch(self, session: aiohttp.ClientSession, url: str) -> str:
        async with session.get(url, headers={"User-Agent": "pulse-engine/1.0"}) as r:
            r.raise_for_status()
            return await r.text()

    # -------------------------------------------------------- cryptopanic --

    async def poll_cryptopanic(self, session: aiohttp.ClientSession) -> int | None:
        if not config.CRYPTOPANIC_KEY:
            return None  # not configured — doesn't count for feed health
        url = ("https://cryptopanic.com/api/v1/posts/"
               f"?auth_token={config.CRYPTOPANIC_KEY}"
               "&currencies=BTC,ETH,XRP,SOL&public=true")
        async with session.get(url) as r:
            r.raise_for_status()
            data = await r.json()
        rows = []
        for p in data.get("results", []):
            title = p.get("title") or ""
            purl = p.get("url") or ""
            ts = int(parsedate_to_datetime(p["published_at"]).timestamp()) \
                if "," in str(p.get("published_at")) else _iso_ts(p.get("published_at"))
            votes = sum((p.get("votes") or {}).get(k, 0)
                        for k in ("positive", "important", "liked"))
            assets = [c.get("code") for c in (p.get("currencies") or [])
                      if c.get("code") in config.ASSETS] or tag_assets(title)
            rows.append({
                "id": _hash_id(purl, title), "ts": ts or int(time.time()),
                "source": "cryptopanic", "title": title[:500], "url": purl,
                "assets_mentioned": ",".join(assets),
                "sentiment_score": score_sentiment(title),
                "importance": importance(1.2, ts or int(time.time()), votes),
            })
        return storage.insert_news(rows)

    # ---------------------------------------------------------------- rss --

    def _parse_rss(self, source: str, weight: float, xml_text: str) -> list[dict]:
        items: list[tuple[str, str, int]] = []  # (title, url, ts)
        if feedparser is not None:
            parsed = feedparser.parse(xml_text)
            for e in parsed.entries[:40]:
                ts = int(time.mktime(e.published_parsed)) if getattr(
                    e, "published_parsed", None) else int(time.time())
                items.append((e.get("title", ""), e.get("link", ""), ts))
        else:  # stdlib fallback
            try:
                root = ET.fromstring(xml_text)
            except ET.ParseError:
                return []
            for item in root.iter("item"):
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub = item.findtext("pubDate")
                try:
                    ts = int(parsedate_to_datetime(pub).timestamp()) if pub else int(time.time())
                except (TypeError, ValueError):
                    ts = int(time.time())
                items.append((title, link, ts))
        rows = []
        for title, url, ts in items:
            if not title:
                continue
            rows.append({
                "id": _hash_id(url, title), "ts": ts, "source": source,
                "title": title[:500], "url": url,
                "assets_mentioned": ",".join(tag_assets(title)),
                "sentiment_score": score_sentiment(title),
                "importance": importance(weight, ts),
            })
        return rows

    async def poll_rss(self, session: aiohttp.ClientSession) -> tuple[int, int]:
        """(feeds fetched successfully, feeds attempted)."""
        ok = 0
        for source, url, weight in config.RSS_FEEDS:
            try:
                xml_text = await self._fetch(session, url)
                storage.insert_news(self._parse_rss(source, weight, xml_text))
                ok += 1
            except Exception as e:  # noqa: BLE001
                log.debug("rss %s failed: %s", source, e)
        return ok, len(config.RSS_FEEDS)

    # --------------------------------------------------------- fear/greed --

    async def poll_fear_greed(self, session: aiohttp.ClientSession) -> None:
        try:
            async with session.get(config.FEAR_GREED_URL) as r:
                data = await r.json()
            vals = data.get("data", [])
            if vals:
                today = int(vals[0]["value"])
                prev = int(vals[1]["value"]) if len(vals) > 1 else today
                self.cache.fng = {"value": today, "change": today - prev}
                day_ts = int(vals[0].get("timestamp") or time.time())
                storage.set_fear_greed(day_ts - day_ts % 86400, today)
        except Exception as e:  # noqa: BLE001
            log.debug("fear&greed fetch failed: %s", e)

    # -------------------------------------------------------------- main ---

    async def poll_once(self) -> None:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            results = await asyncio.gather(
                self.poll_cryptopanic(session), self.poll_rss(session),
                self.poll_fear_greed(session), return_exceptions=True)
        cp, rss = results[0], results[1]
        cp_ok = isinstance(cp, int)                    # None/exception = not ok
        rss_ok, rss_tried = rss if isinstance(rss, tuple) else (0, 1)
        if cp_ok or rss_ok:
            self.cache.status = "ok" if (rss_ok == rss_tried and
                                         (cp_ok or not config.CRYPTOPANIC_KEY)) \
                else "degraded"
            self.cache.last_ok = time.time()
        else:
            self.cache.status = "down"

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.cache.status = "down"
                log.warning("news poll error: %s", e)
            try:
                await asyncio.wait_for(self._stop.wait(), config.NEWS_POLL_SECONDS)
            except asyncio.TimeoutError:
                pass

    def stop(self) -> None:
        self._stop.set()


def news_features(asset: str, at_ts: int) -> dict[str, float]:
    """Aggregates for the feature builder: last-60-min stats before `at_ts`."""
    items = storage.recent_news(limit=200, since_ts=at_ts - 3600, asset=asset)
    items = [i for i in items if i["ts"] <= at_ts]
    hi = [i for i in items if (i.get("importance") or 0) >= 0.8]
    sents = [i["sentiment_score"] for i in items if i.get("sentiment_score") is not None]
    breaking = any(
        any(w in (i["title"] or "").lower() for w in _BREAKING_WORDS) for i in hi)
    return {
        "news_count_60m": float(len(items)),
        "news_hi_count_60m": float(len(hi)),
        "news_sent_60m": float(sum(sents) / len(sents)) if sents else 0.0,
        "news_breaking": 1.0 if breaking else 0.0,
    }


def _iso_ts(s: str | None) -> int | None:
    import datetime as dt
    if not s:
        return None
    try:
        return int(dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


if __name__ == "__main__":
    logging.basicConfig(level=config.LOG_LEVEL,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    storage.init_db()
    asyncio.run(NewsCollector().poll_once())
    print(f"{'when':<18} {'src':<13} {'assets':<12} {'sent':>6} {'imp':>5}  title")
    for item in storage.recent_news(limit=10):
        when = time.strftime("%m-%d %H:%M", time.gmtime(item["ts"]))
        print(f"{when:<18} {item['source']:<13} {item['assets_mentioned'] or '-':<12} "
              f"{item['sentiment_score']:>6.2f} {item['importance']:>5.2f}  "
              f"{item['title'][:70]}")
