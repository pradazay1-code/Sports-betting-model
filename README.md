# Pradapicks

A 100% free, self-updating sports-betting model + dashboard for **NBA / MLB / NHL / NFL / Soccer (EPL + top leagues)** player props. No paid APIs, no servers to rent — everything runs on **GitHub Actions** and the dashboard is served by **GitHub Pages**.

## What it does

Every day, automatically, with no input from you:

1. **Pulls schedules + box scores** from MLB Stats API, stats.nba.com, api-web.nhle.com, and ESPN's public site API (NFL + soccer for the major leagues: Premier League, La Liga, Bundesliga, Serie A, Ligue 1, Champions League, MLS).
2. **Pulls live prop lines** from PrizePicks, DraftKings, FanDuel, Bovada, and Pinnacle — five free books for line-shopping and a sharp anchor.
3. **Pulls context**: ESPN injuries for every league, Open-Meteo weather for outdoor MLB parks, MLB confirmed lineups, MLB park factors.
4. **Trains a LightGBM regressor** per `(sport, market)` over rolling-window features (last 5/10/25 game means, opponent-allowed averages, days rest, home/away, season-to-date averages).
5. **Computes EV vs. the book**: de-vigs the two-way market with a multiplicative model, estimates a `P(over line)` via Poisson (count markets) or Normal (continuous), runs that through an isotonic calibrator, and prices Kelly stake + edge%.
6. **Picks the top plays** with a 0–100 rating that combines edge / confidence / disagreement / sample size / market depth.
7. **Predicts every game's score, total, spread, and home-win probability** from rolling team form, with park-factor adjustment for MLB.
8. **Builds recommended parlays** from today's top picks with a Gaussian-copula same-game-correlation adjustment.
9. **Grades yesterday's picks** against the actual box scores at 04:00 ET, records ROI in units, and **retrains every model** so the system gets better every day.
10. **Grades any bet you type in** — a single bet or a full parlay — and hands back a **letter grade (A+ → F)** with a deep breakdown: model probability, no-vig fair probability, EV edge, projected stat value vs. the line, recent form (last 5/10/25), Kelly stake, and an itemised list of strengths and concerns. Available both as a client-side analyzer on the dashboard and as a server-side CLI (`python -m app.analysis`).
11. **Writes `docs/picks.json`** which the static dashboard reads. GitHub Pages serves the dashboard, complete with the bet-analysis grader and letter-graded picks.

Everything lives in this repo — code, training data (`data/pradapicks.db`), trained model artifacts (`models/*.joblib`), and rendered dashboard (`docs/`). The GitHub Actions bot commits updates back so the whole history is versioned in git.

## How it runs itself

Three scheduled workflows do all the work:

| Workflow | When | What it does |
|---|---|---|
| `daily-picks.yml` | 13:00 UTC (~09:00 ET) | Pulls today's odds + context, regenerates the top-25 picks, refreshes the dashboard. |
| `refresh-odds.yml` | Every 2h during the slate | Re-pulls odds, regenerates picks for line moves. |
| `nightly.yml` | 08:00 UTC (~04:00 ET) | Ingests yesterday's finals, grades picks, retrains every model. |
| `bootstrap.yml` | Manual one-shot | Backfills 45 days of history, trains every model, generates the first picks. |
| `pages.yml` | On push to `docs/` | Re-deploys the GitHub Pages site. |
| `ci.yml` | On every push/PR | Runs unit tests. |

## Setup (one time, ~3 minutes)

1. **Make the repo public** (optional — only matters for unlimited free Actions minutes; private has 2,000/mo which is also plenty).
2. **Enable GitHub Pages**: Repo *Settings -> Pages -> Source = GitHub Actions*.
3. **Enable Actions write permissions**: Repo *Settings -> Actions -> General -> Workflow permissions -> Read and write permissions*.
4. Go to *Actions -> bootstrap -> Run workflow* and pick e.g. `45` days. This populates `data/pradapicks.db`, trains every model, and writes the first `docs/picks.json`.
5. Visit the GitHub Pages URL the *deploy-pages* workflow prints. That's your dashboard.

From that point on the daily / odds-refresh / nightly workflows take over and you never have to touch it.

## Architecture

```
app/
  config.py             env-driven config + sport/market registry
  utils.py              http client with retries, time helpers
  store.py              SQLite schema + read/write helpers
  features.py           rolling-window feature engineering (no leakage)
  ev.py                 de-vig, kelly, edge, 0-100 rating
  ingest.py             pulls schedules/box scores into the DB
  picks.py              picks generator
  analysis.py           deep bet-analysis grader (letter grade A+..F + breakdown)
  tracker.py            grading + ROI/Brier accumulation
  backtest.py           walk-forward backtest harness
  pipeline.py           CLI entry points used by the workflows
  models/
    prop_model.py       LightGBM regressor + isotonic + Poisson/Normal tail
    trainer.py          train every (sport, market) model
  sources/
    mlb.py nba.py nhl.py nfl.py soccer.py   schedule + box score scrapers
    prizepicks.py draftkings.py bovada.py   odds scrapers
    markets.py                  market-name normalisation
    odds.py                     parallel multi-book aggregator
    injuries.py weather.py lineups.py   context scrapers

data/pradapicks.db      SQLite — committed back by the workflows
models/*.joblib         Trained model bundles — committed back
docs/                   Static dashboard + picks.json (GitHub Pages)
.github/workflows/      CI + scheduled pipelines
```

## CLI

The pipeline is also runnable locally:

```bash
pip install -r requirements.txt
python -m app.pipeline bootstrap 30   # backfill 30 days, train, generate picks
python -m app.pipeline daily          # today's picks
python -m app.pipeline odds           # refresh just odds + regen picks
python -m app.pipeline nightly        # grade yesterday + retrain
python -m app.backtest                # walk-forward eval per (sport, market)

# Deep bet-analysis grade for a single bet:
python -m app.analysis '{"sport":"NBA","player_name":"Nikola Jokic","market":"player_points","side":"over","line":24.5,"price_american":-115}'

# ...or a parlay (pass a JSON array of legs):
python -m app.analysis '[{"sport":"NBA","player_name":"Nikola Jokic","market":"player_points","side":"over","line":24.5,"price_american":-115}, {"sport":"NBA","player_name":"Jamal Murray","market":"player_assists","side":"over","line":5.5,"price_american":-120}]'
```

## Bet-analysis grade

The grader (`app/analysis.py`) reuses the exact same modelling stack as the
picks generator, so the grade you get for a hand-entered bet is consistent
with the auto-generated picks. For each leg it returns:

- a **letter grade** (A+ … F) — a bet can never grade above a ceiling set by
  its EV edge, so a -EV play never gets an A no matter how confident the model;
- model probability, no-vig fair probability, EV edge%, Kelly stake;
- the model's **projected stat value** and its margin vs. the posted line;
- **recent form** (last 5/10/25 averages, volatility, days rest, opponent
  allowed) and a plain-English list of **strengths** and **concerns**.

For parlays it grades every leg, then assigns an overall grade that blends the
correlation-adjusted parlay edge with the weakest leg (a chain is only as
trustworthy as its shakiest link).

## How the model gets better every day

- The nightly job ingests yesterday's final box scores and appends them to the training table.
- The grader marks each pick win/loss/push and records ROI in units.
- The trainer retrains every `(sport, market)` model on the full updated history — including a fresh isotonic calibration, so calibration drift gets corrected daily.
- Per-model metrics (rows, MAE, Brier, log-loss) get inserted into `model_runs` and surfaced on the dashboard, so you can watch quality move over time.

## Honest reporting

The dashboard shows **calibrated probability, fair probability, edge%, Kelly stake, rating, and rolling ROI in units** — not made-up hit-rate marketing claims. Brier and log-loss are tracked per model so you can see calibration quality at a glance.

## License

MIT.
