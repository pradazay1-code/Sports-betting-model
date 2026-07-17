# ⚡ Pulse Engine — Kalshi 15-Minute Crypto Prediction System

A local, self-improving **research tool** for Kalshi's 15-minute crypto
up/down markets (BTC, ETH, XRP, SOL). It ingests live prices and news,
predicts the probability each asset closes UP for the current window,
compares that against Kalshi's live pricing to find fee-adjusted edge, logs
every prediction as a paper trade, grades itself after every window, and
retrains from its own mistakes.

**This is not an auto-trader.** No order placement exists in this codebase.
Every pick is a paper trade; the dashboard shows paper P&L including Kalshi
fees. NO PLAY is a first-class (and the most common) output.

## Quick start

```bash
cd pulse-engine
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # optional: add Kalshi + CryptoPanic keys

python collectors/history_backfill.py   # ≥90 days of 1m candles (one-time, ~10 min)
python engine/model.py --train          # walk-forward train + calibrate (per asset)
python run.py                           # collectors + engine + dashboard
```

Open **http://localhost:8777**.

Other commands:

```bash
python collectors/kalshi_client.py   # verify Kalshi markets/quotes discovery
python collectors/news_collector.py  # verify news ingest
python engine/backtest.py --days 30  # out-of-sample backtest (simulated quotes)
pytest tests/                        # window/fee/edge/no-lookahead tests
```

## How a pick happens

The engine **scans continuously** through every window (every 20s, from 60s
after open until 45s before close) — the way the practitioner ecosystem
trades these markets, where edge appears mid-window when Kalshi quotes lag
spot moves:

1. Features are built from 1-minute candles + the live tick (returns,
   EMA/RSI/MACD, realized vol, VWAP distance, candle anatomy, volume
   z-score, BTC lead/correlation, time-of-day, Fear & Greed, news
   sentiment, Kalshi microstructure) with a strict no-lookahead gate.
2. The **Brownian fair value** is computed:
   `P(up) = Φ(move ÷ (σ√seconds_remaining))` — the standard pricing model
   for these binaries. It is both a feature and the fallback predictor.
3. A calibrated LightGBM model per asset (trained at five elapsed-time
   offsets per window so it learns the move/time-remaining interaction)
   refines that into the final `P(up)`.
4. The decision probability **shrinks the model toward the market**
   (`p = implied + 0.5 × (model − implied)`, `MODEL_MARKET_SHRINK`) — a
   winner's-curse correction, because large model-vs-market gaps are where
   the model is most often the one that's wrong. A pick is committed once
   `edge > fee + buffer` (buffer starts at 3 points and auto-raises if the
   last 50 picks lose on paper) **and** the shrunk probability is outside
   45–55% **and** the signal survives two consecutive scans
   (`SCAN_CONFIRMATIONS`) — at most one pick per asset per window. If the
   window ends without a trigger: **NO PLAY**.
5. Each pick carries a **quarter-Kelly stake suggestion** (display only),
   and the scanner flags **dual-side arbitrage** whenever YES + NO asks sum
   below $1.
6. 30 seconds after the window closes, the outcome is graded (correctness,
   Brier score, fee-inclusive paper P&L). Daily error analysis groups losses
   by regime into `logs/error_analysis.md`; retrains trigger weekly, on
   Brier degradation, or every 200 resolved windows — and a new model is
   promoted only if its validation Brier improves.

Each asset card also shows:

- **NEXT WINDOW** — an early UP/DOWN lean on the upcoming market (computed
  from at-the-open features the model was explicitly trained on), appearing
  during the final ~2½ minutes of the current window and firming up once
  the new window opens;
- **AI breakdown** — a per-read deep dive: the fair-value chain (Brownian
  fair value → ML probability → market-shrunk decision prob → Kalshi's
  price → the fee+buffer hurdle), the top weighted factors behind the lean
  (signed, in probability points, from LightGBM per-prediction
  contributions), historical analogs (how windows in this time-of-day and
  vol regime resolved), and the system's own recent graded record;
- the **Learning** panel tracks whether it's improving: 7-day vs 14-day
  accuracy and Brier with trend arrows, total windows graded, model
  versions, and the current adaptive edge buffer.

## Honesty notes

- 15-minute crypto direction is nearly a coin flip and Kalshi prices these
  markets efficiently. Expect walk-forward accuracy near ~52% on real data;
  the dashboard says this out loud. Any edge comes from calibrated
  disagreement with Kalshi's price on *specific* windows.
- Backtest P&L is approximate: historical Kalshi quotes aren't available, so
  the backtest simulates an efficient market (50%±2 mid). It validates
  plumbing and calibration more than alpha.
- If a feed dies, the dashboard shows stale badges and the engine suppresses
  picks rather than guessing.

## Configuration

Everything tunable lives in `config.py` (overridable via `.env`): asset
list, exchange (binanceus default, binance/coinbase/kraken fallbacks), edge
buffer, fee rate, Kalshi series ticker candidates (`KALSHI_SERIES_BTC=...`
to pin one), dashboard port (8777), retrain cadence.

Verify the Kalshi fee schedule and 15-minute series tickers against the
live docs (https://docs.kalshi.com) the first time you run with network
access — `KALSHI_FEE_RATE` and `KALSHI_SERIES_*` in `.env` are the knobs.

The dashboard UI is fully self-contained (hand-rolled canvas charts, no CDN).

## Trade execution (Phase 9)

Deliberately **not implemented**. If, after reviewing at least two weeks of
paper results, you want it, that is a separate explicit build — and it stays
off without `I_UNDERSTAND_THE_RISK=true`.
