"""Pulse Engine configuration — every tunable lives here.

Values can be overridden via environment variables / a .env file next to
this file. All timestamps in the system are stored as UTC epoch seconds;
the UI displays America/New_York (Kalshi windows are ET-aligned).
"""
from __future__ import annotations

import math
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- assets ----
ASSETS: list[str] = ["BTC", "ETH", "XRP", "SOL"]

# Preferred spot exchange for candles, with fallbacks tried in order.
# binanceus works from the US; binance has the deepest books elsewhere.
EXCHANGE_ID: str = _env("EXCHANGE_ID", "binanceus")
EXCHANGE_FALLBACKS: list[str] = ["binance", "coinbase", "kraken"]

# ccxt symbol per exchange family. Quote currency differs by venue.
SYMBOLS: dict[str, dict[str, str]] = {
    "binanceus": {"BTC": "BTC/USDT", "ETH": "ETH/USDT", "XRP": "XRP/USDT", "SOL": "SOL/USDT"},
    "binance":   {"BTC": "BTC/USDT", "ETH": "ETH/USDT", "XRP": "XRP/USDT", "SOL": "SOL/USDT"},
    "coinbase":  {"BTC": "BTC/USD",  "ETH": "ETH/USD",  "XRP": "XRP/USD",  "SOL": "SOL/USD"},
    "kraken":    {"BTC": "BTC/USD",  "ETH": "ETH/USD",  "XRP": "XRP/USD",  "SOL": "SOL/USD"},
}

# Raw websocket hosts for the live collector (kline streams).
BINANCE_WS_HOSTS: dict[str, str] = {
    "binanceus": "wss://stream.binance.us:9443",
    "binance": "wss://stream.binance.com:9443",
}
COINBASE_WS_URL: str = "wss://ws-feed.exchange.coinbase.com"

# ------------------------------------------------------------------ time ----
TZ = ZoneInfo("America/New_York")
WINDOW_SECONDS: int = 15 * 60          # Kalshi window length
PREDICTION_DELAY_SECONDS: int = _env_int("PREDICTION_DELAY_SECONDS", 75)
GRADE_DELAY_SECONDS: int = 30          # grade this long after window close

# In-window scanning (how practitioners actually trade these markets:
# evaluate continuously and act whenever quotes lag spot, instead of one
# prediction per window).
SCAN_INTERVAL_SECONDS: int = _env_int("SCAN_INTERVAL_SECONDS", 20)
SCAN_START_SECONDS: int = _env_int("SCAN_START_SECONDS", 60)    # no entries before
SCAN_STOP_SECONDS: int = _env_int("SCAN_STOP_SECONDS", 45)      # no entries after close-N
# A pick must clear the edge threshold on this many CONSECUTIVE scans before
# it is committed — debounces quote noise and single-tick model blips.
SCAN_CONFIRMATIONS: int = _env_int("SCAN_CONFIRMATIONS", 2)
# Elapsed-time offsets (s) at which training rows are sampled per window, so
# the model learns the move/time-remaining interaction the scanner sees live.
# Offset 0 = at-the-open rows, powering the next-window early projection.
TRAIN_SAMPLE_OFFSETS: list[int] = [0, 75, 240, 480, 720, 840]
# The dashboard shows an early read on the NEXT window during the final
# stretch of the current one (limited by the data-staleness gate).
NEXT_WINDOW_PREVIEW_SECONDS: int = _env_int("NEXT_WINDOW_PREVIEW_SECONDS", 150)

# --------------------------------------------------------------- storage ----
DATA_DIR = BASE_DIR / "data"
DB_PATH = Path(_env("DB_PATH", str(DATA_DIR / "pulse.db")))
MODELS_DIR = BASE_DIR / "models"
LOGS_DIR = BASE_DIR / "logs"
LOG_LEVEL = _env("LOG_LEVEL", "INFO")

# -------------------------------------------------------------- backfill ----
BACKFILL_DAYS: int = _env_int("BACKFILL_DAYS", 90)

# ---------------------------------------------------------------- kalshi ----
KALSHI_BASE_URL = _env("KALSHI_BASE_URL", "https://api.elections.kalshi.com/trade-api/v2")
KALSHI_API_KEY_ID = _env("KALSHI_API_KEY_ID", "")
KALSHI_PRIVATE_KEY_PATH = _env("KALSHI_PRIVATE_KEY_PATH", "")
KALSHI_POLL_SECONDS: int = _env_int("KALSHI_POLL_SECONDS", 12)

# Series tickers for the 15-minute up/down crypto markets. Kalshi renames
# series occasionally, so these are *candidates*: kalshi_client tries each,
# then falls back to scanning the series list for `<asset> ... 15`-style
# titles. Set KALSHI_SERIES_<ASSET> in .env to pin one explicitly.
KALSHI_SERIES_CANDIDATES: dict[str, list[str]] = {
    "BTC": ["KXBTC15M", "KXBTCUD15M", "KXBTC"],
    "ETH": ["KXETH15M", "KXETHUD15M", "KXETH"],
    "XRP": ["KXXRP15M", "KXXRPUD15M", "KXXRP"],
    "SOL": ["KXSOL15M", "KXSOLUD15M", "KXSOL"],
}
for _asset in ASSETS:
    _override = os.environ.get(f"KALSHI_SERIES_{_asset}")
    if _override:
        KALSHI_SERIES_CANDIDATES[_asset] = [_override.strip().upper()]

# ------------------------------------------------------------------ fees ----
# Kalshi general trading fee (2024–2026 schedule): per fill,
#   fee_dollars = ceil_to_cent(0.07 * contracts * price * (1 - price))
# where price is in dollars (0–1). Verify against the live fee schedule at
# https://kalshi.com/docs/kalshi-fee-schedule.pdf when you have network
# access — FEE_RATE is the only knob that should need changing.
FEE_RATE: float = _env_float("KALSHI_FEE_RATE", 0.07)
PAPER_CONTRACTS: int = _env_int("PAPER_CONTRACTS", 100)  # paper-trade lot size


def kalshi_fee_dollars(contracts: int, price: float, rate: float = FEE_RATE) -> float:
    """Total fee in dollars for a fill of `contracts` at `price` (0–1)."""
    if contracts <= 0:
        return 0.0
    price = min(max(price, 0.0), 1.0)
    raw = rate * contracts * price * (1.0 - price)
    return math.ceil(raw * 100.0 - 1e-9) / 100.0


def kalshi_fee_per_contract(price: float, contracts: int | None = None) -> float:
    """Fee per contract in dollars (== probability points) at `price`."""
    n = contracts or PAPER_CONTRACTS
    return kalshi_fee_dollars(n, price) / n


# ---------------------------------------------------------------- sizing ----
# Fractional Kelly stake suggestion shown with each pick (display only —
# paper P&L stays at PAPER_CONTRACTS flat lots for comparability).
PAPER_BANKROLL: float = _env_float("PAPER_BANKROLL", 1000.0)
KELLY_FRACTION: float = _env_float("KELLY_FRACTION", 0.25)

# --------------------------------------------------------------- signals ----
# Winner's-curse correction: the market is usually right, so the decision
# probability shrinks the model's estimate toward the Kalshi implied prob:
#   p_decision = implied + SHRINK * (model_prob - implied)
# 1.0 trusts the model fully; 0.0 never disagrees with the market.
MODEL_MARKET_SHRINK: float = _env_float("MODEL_MARKET_SHRINK", 0.5)

# A pick is flagged only when |decision_prob - price_paid| > fee + buffer.
MIN_EDGE_BUFFER: float = _env_float("MIN_EDGE_BUFFER", 0.03)
MAX_EDGE_BUFFER: float = 0.08          # adaptive-threshold ceiling
# Model probability must sit outside this band for a pick (else NO PLAY).
CONFIDENCE_BAND: tuple[float, float] = (0.45, 0.55)
# Suppress picks when the newest candle is older than this (stale feed).
MAX_DATA_STALENESS_SECONDS: int = _env_int("MAX_DATA_STALENESS_SECONDS", 180)

# ---------------------------------------------------------------- models ----
FLAT_WINDOW_BPS: float = 1.0           # drop |return| < 1bp windows from training
WALK_FORWARD_MIN_TRAIN_DAYS: int = 30
WALK_FORWARD_VAL_DAYS: int = 7
RETRAIN_EVERY_DAYS: int = 7
RETRAIN_BRIER_DEGRADATION: float = 0.10   # retrain if 7d Brier worsens >10% vs val
RETRAIN_NEW_OUTCOMES: int = 200           # ... or after this many new resolved windows
ADAPTIVE_LOOKBACK_PICKS: int = 50         # raise buffer if last N picks lose on paper

# ------------------------------------------------------------------ news ----
CRYPTOPANIC_KEY = _env("CRYPTOPANIC_KEY", "")
NEWS_POLL_SECONDS: int = _env_int("NEWS_POLL_SECONDS", 150)
RSS_FEEDS: list[tuple[str, str, float]] = [  # (source, url, weight)
    ("coindesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", 1.0),
    ("cointelegraph", "https://cointelegraph.com/rss", 0.8),
    ("theblock", "https://www.theblock.co/rss.xml", 1.0),
]
FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=2"

# ------------------------------------------------------------- dashboard ----
DASHBOARD_HOST = _env("DASHBOARD_HOST", "127.0.0.1")
DASHBOARD_PORT: int = _env_int("DASHBOARD_PORT", 8777)

# --------------------------------------------------------------- phase 9 ----
# Automated trading is intentionally NOT implemented. This flag exists only
# so the dashboard can state that execution is off.
TRADING_ENABLED: bool = (
    _env("I_UNDERSTAND_THE_RISK", "false").lower() == "true"
)  # and even then: no execution code ships in Phases 0–8.

for _d in (DATA_DIR, MODELS_DIR, LOGS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
