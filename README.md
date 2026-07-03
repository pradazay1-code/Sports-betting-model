# Edge Engine

Autonomous sports betting research & prop analysis system for **Soccer (World Cup priority), MLB, NBA, and NFL**. Hunts for mispriced player props and main markets, validates edges with research, and delivers a daily rundown. Full specification: [`CLAUDE.md`](CLAUDE.md).

## Operating principles (non-negotiable)

1. **+EV over win rate** — every pick shows model probability, market implied probability, and the EV gap.
2. **CLV is the true scoreboard** — every recommendation is tracked against the closing line.
3. **No pick without an edge** — 4% EV minimum for props, 3% for main markets. "NO PLAYS TODAY" is a valid output.
4. **Honesty layer** — every stat traces to a fetched, timestamped source.
5. **Bankroll discipline is code** — quarter-Kelly, 2%/play, 6%/day caps, enforced by `src/engine/staking.py`.
6. **Paper mode gate** — 200 tracked picks with positive CLV before real-money sizing is ever displayed.

## Build status

| Phase | Scope | Status |
|---|---|---|
| **1** | Scaffold, config system, SQLite ledger, odds ingestion + line-movement logging | ✅ built |
| **2** | MLB end-to-end (ingest → K-prop model → value scanner → rundown) | ✅ built |
| **3** | Staking, CLV tracker, daily rundown, cron automation, paper period starts | ✅ built |
| **4** | NBA + NFL modules, correlation engine, PrizePicks/Underdog slips | ✅ built |
| **5** | Soccer/World Cup module, deep research pipeline, Discord/email | ✅ built |
| **6** | Weekly review loop, calibration shrinkage, category suspend/promote | ✅ built (runs Mondays) |

The system is now in its **mandatory paper period**: every stake displays as
"units (paper)" until 200 tracked picks with positive CLV clear the gate.

Key entry points beyond the quick start:

```bash
python -m src.run_daily --props                  # full daily pipeline
python -m src.engine.clv_tracker --nightly       # grade yesterday + closing lines
python -m src.report.weekly_review --run         # Monday audit
python -m src.research.deep_dive --generate      # research briefs for EV>6% picks
python -m src.research.deep_dive --validate 12 --memo "..." [--kill]
```

## Quick start (Phase 1)

```bash
pip install -r requirements.txt
cp .env.example .env          # add your free key from https://the-odds-api.com

# pull live lines for all enabled sports into data/db.sqlite
python -m src.ingest.odds --pull            # featured markets (1 request/sport)
python -m src.ingest.odds --pull --props    # + player props (1 request/event — watch the 500/mo budget)

# no API key yet? exercise the full pipeline on the bundled sample payload
python -m src.run_daily --sample tests/fixtures/odds_api_sample.json

# what moved in the last 24h
python -m src.ingest.odds --movement --hours 24

# line-shop a market across books (best price first)
python -m src.ingest.odds --shop <EVENT_ID> h2h

# run tests
python -m pytest
```

Every pull is cached raw under `data/raw/odds/<date>/` and appended to the `line_snapshots` table — that time series is what powers line movement, line shopping, and (Phase 3) CLV grading. API quota headers are logged to `api_usage` on every request.

## Layout

See `CLAUDE.md §1` for the full architecture. Phase 1 live code: `src/config.py`, `src/db.py`, `src/ingest/odds.py`, `src/run_daily.py`. Everything else under `src/` is scaffolded with its build phase noted in the module docstring.
