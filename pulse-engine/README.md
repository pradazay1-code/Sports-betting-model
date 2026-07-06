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

Every window (:00/:15/:30/:45 ET), 75 seconds after open:

1. Features are built from 1-minute candles (returns, EMA/RSI/MACD, realized
   vol, VWAP distance, candle anatomy, volume z-score, BTC lead/correlation,
   time-of-day, Fear & Greed, news sentiment, Kalshi microstructure) with a
   strict no-lookahead gate.
2. A calibrated LightGBM model per asset produces `P(up)`.
3. Kalshi's yes/no quotes give the implied probability; the fill price for
   each side is the ask.
4. A pick is flagged only if `edge > fee + buffer` (buffer starts at 3 points
   and auto-raises if the last 50 picks lose on paper) **and** the model
   probability is outside 45–55%. Otherwise: **NO PLAY**.
5. 30 seconds after the window closes, the outcome is graded (correctness,
   Brier score, fee-inclusive paper P&L). Daily error analysis groups losses
   by regime into `logs/error_analysis.md`; retrains trigger weekly, on
   Brier degradation, or every 200 resolved windows — and a new model is
   promoted only if its validation Brier improves.

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
