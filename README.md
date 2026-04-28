# Pradapicks

AI-driven player-prop scoring engine for **MLB**, **NBA**, and **NHL**. Pradapicks ingests schedules, box scores, and sportsbook prop markets daily, fits per-(sport, market) gradient-boosted models with isotonic calibration, and publishes the **top 25 props of the day** with a 0–100 rating. It also analyzes user-submitted bet slips, tracks results, and retrains itself nightly.

## What it does

- **Daily Top 25 Props** — best edges across MLB / NBA / NHL with a 0–100 rating, recommended Kelly stake, model probability, no-vig fair probability, and full rationale.
- **Bet Slip Analyzer** — drop in legs from DraftKings, FanDuel, BetMGM, Caesars, etc. Returns per-leg + parlay rating with verdict.
- **Results Tracker** — automatically grades picks against actual box scores and reports hit rate / ROI by sport and overall.
- **Self-Improvement** — nightly job retrains models on the new labeled data so the system keeps getting smarter.

## Architecture

```
pradapicks/
  config.py          settings (env-driven)
  db.py              SQLAlchemy models (Postgres or SQLite)
  data/              MLB, NBA, NHL, and Odds API providers
  features.py        rolling-window feature engineering
  models/            LightGBM regressor + Poisson/Normal P(over) + isotonic calibration
  scoring.py         0..100 rating engine (edge / confidence / disagreement / sample / depth)
  picks.py           daily top-N generator with consensus + de-vig
  betslip.py         per-leg + parlay analyzer
  tracker.py         grading + progress reports
  ingest.py          schedule / box / odds upserts
  scheduler.py       APScheduler jobs (morning picks, mid-day refresh, nightly grade + retrain)
  api.py             FastAPI app
```

### Rating components (weights)

| Component | Weight | What it measures |
|-----------|-------:|------------------|
| Edge      | 0.45 | Model EV vs. posted price |
| Confidence| 0.15 | Distance from 50/50 |
| Disagreement | 0.20 | Model probability minus no-vig fair prob |
| Sample size | 0.10 | Training rows for that (sport, market) |
| Market depth | 0.10 | Number of books offering the line |

## Zero-config: 100% free data, zero manual steps

Pradapicks ships with **free** data providers — no paid keys required:

| Source | What it gives | Auth |
|--------|---------------|------|
| MLB Stats API | Schedule + box scores | none |
| NBA stats.nba.com | Schedule + box scores | none |
| NHL api-web.nhle.com | Schedule + box scores | none |
| **PrizePicks** public projections | Player prop **lines** for MLB / NBA / NHL | none |
| **DraftKings** public sportsbook JSON | Player prop **lines + American odds** | none |

These two odds sources are aggregated into the same `PropOffer` schema so the model treats them as a single market with multiple "books." Optionally, if you set `ODDS_API_KEY`, the paid The Odds API is layered in on top — but it is not required.

## Running locally

```bash
cp .env.example .env
pip install -r requirements.txt
python main.py
# -> http://localhost:8000/docs
# On first boot the API kicks off a 30-day backfill + training in a background thread.
```

## Deploying to Render (one click)

1. Push this repo to GitHub.
2. In Render, click **New → Blueprint** and point at the repo. `render.yaml` provisions:
   - a managed Postgres 16 database
   - a Python web service running gunicorn + uvicorn
3. **That's it.** No API keys, no shell commands. On first boot the service:
   - creates all tables
   - kicks off a 30-day backfill of MLB/NBA/NHL box scores in a background thread
   - trains every (sport, market) model
   - pulls live PrizePicks + DraftKings odds and publishes today's top-25 picks

   You can watch progress in the Render logs or by polling `GET /progress`.

4. The scheduler runs inside the web process (`RUN_SCHEDULER=true`):
   - **09:00 ET** — pull odds, generate top-25 picks
   - **11:15 / 14:15 / 17:15 ET** — refresh odds for line moves
   - **04:00 ET** — ingest yesterday's box scores + grade yesterday's picks
   - **05:00 ET** — retrain all (sport, market) models

> For more reliable scheduling at scale, split the scheduler into a Render **Background Worker** running `python -c "from pradapicks.scheduler import start_scheduler; start_scheduler(); import time; time.sleep(10**9)"` and set `RUN_SCHEDULER=false` on the web service.

## Public endpoints

| Method | Path | Purpose |
|---|---|---|
| GET  | `/health` | Liveness |
| GET  | `/picks/today?sport=NBA` | Today's top picks (filterable) |
| GET  | `/picks?on=YYYY-MM-DD` | Picks for a specific date |
| POST | `/betslip/analyze` | Analyze a bet slip |
| GET  | `/progress?days=30` | Hit rate + ROI report |

## Admin endpoints (require `Authorization: Bearer $API_AUTH_TOKEN`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/picks/generate` | Force-regenerate today's picks |
| POST | `/admin/ingest/odds` | Pull latest props |
| POST | `/admin/ingest/box?on=YYYY-MM-DD` | Ingest a day's box scores |
| POST | `/admin/ingest/backfill?days=30` | Backfill historical box scores |
| POST | `/admin/train` | Retrain all models |
| POST | `/admin/grade?on=YYYY-MM-DD` | Grade a day's picks |
| POST | `/admin/bootstrap?days=30` | Re-run a full backfill + train + pick cycle |

### Bet slip request shape

```json
{
  "book": "DraftKings",
  "legs": [
    {"sport":"NBA","player_name":"Jayson Tatum","market":"player_points","line":27.5,"side":"over","price_american":-115},
    {"sport":"MLB","player_name":"Aaron Judge","market":"batter_total_bases","line":1.5,"side":"over","price_american":+105}
  ]
}
```

## Data sources (all free)

- **MLB** — [statsapi.mlb.com](https://statsapi.mlb.com) (public, no key)
- **NBA** — [stats.nba.com](https://stats.nba.com) (public, browser-style headers)
- **NHL** — [api-web.nhle.com](https://api-web.nhle.com) (public, no key)
- **PrizePicks** — `api.prizepicks.com/projections` (public, no key)
- **DraftKings** — `sportsbook-nash.draftkings.com/sites/US-SB/api/v5` (public, no key)
- *(optional)* **The Odds API** — only used if `ODDS_API_KEY` is set

Each source lives behind a single provider class — drop in SportsDataIO, OddsJam, FanDuel, etc. without touching the rest of the system.

## Notes on honesty

The popular "72% verified hit rate" framing in the prompt is marketing. Pradapicks reports **calibrated probabilities, edge%, ROI in units, and Brier score**, which are durable measures of model quality. Hit rate alone is meaningless without juice context.

## License

MIT (or your choice).
