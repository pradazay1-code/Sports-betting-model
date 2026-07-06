# CLAUDE.md — "Pulse Engine" — Kalshi 15-Minute Crypto Prediction System

## What This Is

A complete, local, self-improving research and prediction system for
Kalshi's short-duration (15-minute) crypto up/down markets. It tracks BTC,
ETH, XRP and SOL in real time, ingests historical price data and crypto
news, generates a probability that each asset closes UP or DOWN for the
current 15-minute Kalshi window, compares that probability against Kalshi's
live market price to find edge, logs every prediction, grades itself after
each window resolves, and retrains/recalibrates from its own mistakes.

Everything is surfaced in a single local dashboard (`python run.py`, then
http://localhost:8777).

## Non-Negotiable Ground Rules

1. **Research tool, not an auto-trader.** No automated order placement
   exists in this codebase. The system flags picks; the user decides. An
   optional trading module would be a separate Phase 9, OFF by default.
2. **Paper-trade first.** Every pick is logged as a paper trade with the
   Kalshi price at signal time. The dashboard shows paper P&L including
   Kalshi fees. No pick is ever presented as a guaranteed winner.
3. **Honesty in the UI.** 15-minute crypto direction is extremely close to
   50/50 and Kalshi prices these markets efficiently. The model displays
   calibrated probabilities, never "locks". If there is no edge after fees,
   the output is NO PLAY — a first-class output and the most common one.
4. **Fees are part of every edge calculation.** Kalshi trading fee
   ≈ `ceil(0.07 × contracts × P × (1−P))` per side (see `config.py:FEE_RATE`;
   verify against Kalshi's current fee schedule). A pick is only flagged
   when `model_prob − price_paid > fee + MIN_EDGE_BUFFER` (default 3 pts)
   and the model probability is outside 45–55%.
5. **Never fabricate data.** If a feed is down, the dashboard shows a stale
   warning and the engine suppresses picks rather than guessing.

## Architecture Map

```
pulse-engine/
├── config.py                  # ALL tunables (env-overridable via .env)
├── storage.py                 # SQLite schema + query helpers (SQLAlchemy Core)
├── run.py                     # entry point: collectors + scheduler + dashboard
├── collectors/
│   ├── price_collector.py     # Binance(.us) WS klines, coinbase fallback, gap-fill
│   ├── history_backfill.py    # ccxt REST 1m backfill + 15m resample/labels
│   ├── kalshi_client.py       # RSA-PSS auth, series discovery, quote polling
│   └── news_collector.py      # CryptoPanic + RSS, dedup, VADER sentiment, F&G
├── engine/
│   ├── window.py              # 15-min window boundary math (UTC/ET aligned)
│   ├── features.py            # single feature code path (no-lookahead enforced)
│   ├── model.py               # logistic baseline + LightGBM + isotonic calibration
│   ├── edge.py                # fee math + UP/DOWN/NO PLAY decision
│   ├── predictor.py           # per-window prediction loop
│   ├── learner.py             # grading, error analysis, retrain, adaptive buffer
│   └── backtest.py            # out-of-sample replay (simulated Kalshi quotes)
├── dashboard/
│   ├── server.py              # FastAPI: /api/state /api/history /api/performance /api/news /health
│   └── static/index.html      # self-contained UI (vanilla JS + canvas charts, no CDN)
└── tests/                     # window/fee/edge/no-lookahead/grading tests
```

## Key Invariants (do not break these)

- **All timestamps are UTC epoch seconds** in storage; display converts to
  ET. Window boundaries are `ts - ts % 900` (exact through DST because ET
  offsets are whole hours).
- **Candle `ts` is minute start**: candle `ts` covers `[ts, ts+60)` and is
  only complete once `now >= ts + 60`. `features._completed()` is the
  single no-lookahead gate — training, backtest and live all go through
  `build_features`.
- **Live-only features default to neutral constants** (Kalshi 0.5, news 0,
  F&G 50) so historical training rows are computed identically.
- **Walk-forward validation only** (expanding window, 7-day chunks) — never
  shuffled splits. Calibration (isotonic) is fit on pooled out-of-fold
  predictions.
- **Model promotion**: a retrained model replaces the old one only if its
  validation Brier improves; otherwise the old bundle is restored.
- **predictions UNIQUE(asset, window_start)** makes the prediction loop
  idempotent; grading joins predictions→outcomes.

## Scheduling (run.py, apscheduler, UTC)

- Predict: minutes 1,16,31,46 at :15s (= 75s into each window,
  `PREDICTION_DELAY_SECONDS`).
- Grade: minutes 0,15,30,45 at :30s (`GRADE_DELAY_SECONDS` after close).
- Adaptive buffer check: minutes 7,22,37,52. Error analysis: 10:05 UTC
  daily. Retrain check: hourly at :11.

## Things to Verify With Network Access

Built/tested offline against synthetic data; these need one pass with real
connectivity:

1. **Kalshi 15-min series tickers** — `KALSHI_SERIES_CANDIDATES` in
   config.py are candidates; discovery scans `/series?category=Crypto` and
   filters for 15-minute market durations. Run
   `python collectors/kalshi_client.py` and pin the right tickers via
   `KALSHI_SERIES_<ASSET>` in `.env` if discovery picks wrong.
2. **Fee schedule** — confirm 0.07 general rate still applies to crypto
   15-min series (`KALSHI_FEE_RATE` env override).
3. **Exchange choice** — binanceus default; `EXCHANGE_ID=coinbase` if
   binance.us is unavailable in the user's region (the collector falls back
   automatically at runtime).

## Run Commands

- `python run.py` — everything (collectors, scheduler, dashboard)
- `python collectors/history_backfill.py` — backfill + Phase 1 report
- `python engine/model.py --train` — retrain + metrics table
- `python engine/backtest.py` — out-of-sample backtest report
- `pytest tests/` — window/fee/edge/no-lookahead/grading tests

## Coding Standards

Async where it matters (collectors), simple sync elsewhere. Type hints.
One rotating logger (`logs/pulse.log`). No hardcoded keys. Small, testable
functions. When Kalshi or exchange APIs are ambiguous, check their current
docs rather than guessing.
