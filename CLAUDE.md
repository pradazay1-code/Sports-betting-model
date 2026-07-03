# EDGE ENGINE — Autonomous Sports Betting Research & Prop Analysis System
### Claude Code Master Build Script / Project Specification

> Drop this file into the root of a new project folder as `CLAUDE.md`, open Claude Code in that folder, and say:
> **"Read CLAUDE.md and build the entire system described. Start with Phase 1."**

---

## 0. MISSION & OPERATING PHILOSOPHY

You (Claude Code) are building **Edge Engine**: a fully automated sports betting research system that analyzes player props and betting questions across **Soccer (World Cup priority), MLB, NBA, and NFL**, hunts for mispriced lines, and delivers a daily rundown.

### Non-negotiable principles (bake these into every module):

1. **Expected Value over win rate.** The system's north star is +EV, not raw win %. A 48% win rate at +130 average odds beats a 58% win rate at -160. Every pick must display: model probability, implied probability from the odds, and the EV gap.
2. **Closing Line Value (CLV) is the true scoreboard.** Track every recommendation against the closing line. Beating the close consistently is the strongest known predictor of long-term profitability. Build CLV tracking from day one.
3. **No pick without an edge threshold.** Minimum edge to surface a pick: **4% EV** for props, **3% EV** for main markets. If nothing clears the bar on a given day, the daily rundown says "NO PLAYS TODAY" — passing is a position.
4. **Honesty layer.** The system must never fabricate stats. Every number in a pick writeup must trace to a fetched data source with a timestamp. If data is stale or missing, flag it and lower confidence.
5. **Bankroll discipline is code, not advice.** Fractional Kelly staking (default 0.25x Kelly), hard cap of 2% of bankroll per play, 6% max daily exposure. These are enforced by the staking module, not suggested.

---

## 1. SYSTEM ARCHITECTURE

```
edge-engine/
├── CLAUDE.md                  # this file
├── config/
│   ├── settings.yaml          # bankroll, edge thresholds, Kelly fraction, sports enabled
│   ├── sources.yaml           # API endpoints, scrape targets, rate limits
│   └── books.yaml             # sportsbooks/DFS apps tracked (DK, FD, PrizePicks, Underdog...)
├── data/
│   ├── raw/                   # cached API pulls (JSON, dated)
│   ├── processed/             # cleaned per-sport parquet/CSV
│   └── db.sqlite              # picks ledger, CLV log, bankroll history
├── src/
│   ├── ingest/
│   │   ├── odds.py            # odds + prop lines (The Odds API or scraped)
│   │   ├── mlb.py             # MLB StatsAPI (statsapi.mlb.com — free, official)
│   │   ├── nba.py             # nba_api / balldontlie
│   │   ├── nfl.py             # nflverse / nfl_data_py
│   │   ├── soccer.py          # football-data.org, FBref (Understat xG), FIFA/WC data
│   │   ├── injuries.py        # injury reports, lineups, weather
│   │   └── news.py            # web research pipeline (see §4)
│   ├── models/
│   │   ├── mlb_model.py       # props: Ks, hits, TBs, HRs, NRFI
│   │   ├── nba_model.py       # props: pts/reb/ast/3PM/PRA
│   │   ├── nfl_model.py       # props: pass/rush/rec yds, TDs, receptions
│   │   ├── soccer_model.py    # props: shots, SOT, goals, cards, corners; match markets
│   │   └── common.py          # Poisson/negative binomial/Monte Carlo utilities
│   ├── engine/
│   │   ├── value_scanner.py   # model prob vs market prob → EV ranking
│   │   ├── correlation.py     # same-game correlation checks for parlays/slips
│   │   ├── staking.py         # fractional Kelly, exposure caps
│   │   └── clv_tracker.py     # log open line vs close, grade picks
│   ├── research/
│   │   └── deep_dive.py       # Claude-driven web research on flagged edges
│   ├── report/
│   │   ├── daily_rundown.py   # generates the daily report (md + optional email/Discord)
│   │   └── weekly_review.py   # CLV audit, ROI, calibration curve, model drift
│   └── run_daily.py           # orchestrator
├── tests/                     # unit tests for every model's probability outputs
└── automation/
    ├── cron_setup.sh          # schedules run_daily at optimal times per sport
    └── github_actions.yaml    # alternative: cloud automation
```

**Stack:** Python 3.11+, pandas, numpy, scipy, sqlite3, requests, optionally scikit-learn/XGBoost for v2 models. Keep dependencies light; prefer stdlib + pandas.

---

## 2. DATA INGESTION LAYER

### 2.1 Odds & Prop Lines (the market)
- Primary: **The Odds API** (free tier: 500 req/mo) — spreads, totals, moneylines, player props across books.
- Store every line pull with timestamp → this powers line-movement analysis and CLV.
- Track: DraftKings, FanDuel, BetMGM, Caesars + **PrizePicks / Underdog projections** (these frequently lag sharp books — that lag IS the edge for DFS slips).
- **Line shopping module:** for every pick, show best available price across books and the cents of value gained.

### 2.2 Per-Sport Stats (the truth)

**MLB** — `statsapi.mlb.com` (free, official, no key):
- Pitcher game logs: K rate, CSW%, pitch mix, times-through-order splits, last 5 starts.
- Batter logs: vs L/R splits, barrel rate, chase rate, recent 15-game form.
- Park factors table (hardcode, update yearly). Weather via Open-Meteo (wind out at Wrigley matters for HR/total props).
- NRFI inputs: 1st-inning ERA for both starters, top-of-lineup wOBA for both teams.

**NBA** — `nba_api` or balldontlie:
- Player logs with minutes, usage rate, pace of both teams, opponent positional defense (DvP).
- **Minutes projection is 70% of NBA props.** Build a minutes model first: rolling avg minutes, blowout risk (spread > 12 → trim star minutes), back-to-back flags, injury-driven usage bumps (when a 25% usage player sits, redistribute).

**NFL** — `nfl_data_py` (nflverse):
- Target share, air yards, snap %, route participation, red-zone share, defensive coverage schemes vs position.
- Game-script model: projected spread/total → pass/run ratio → volume projections.
- Weather (wind > 15mph kills passing props and totals).

**Soccer / World Cup** — football-data.org (free tier) + FBref/Understat scrape:
- xG and xA per 90, shots and SOT per 90, set-piece involvement, penalty duty.
- **World Cup specifics:** international form ≠ club form. Weight: club underlying numbers 60%, international last-10 30%, tournament context 10%. Track likely lineups (rotation in group stage game 3 when qualification is locked is the #1 WC prop trap). Referee card tendencies for card props. Extra time/penalties handling: know whether the book grades props on 90 minutes only (almost always yes — model 90', not 120').

### 2.3 Injuries, Lineups, Context
- Scrape official injury reports (NBA injury report PDF, NFL Wed/Thu/Fri reports, MLB IL moves, national-team pressers for soccer).
- **Confirmed lineup gate:** NBA/soccer props are HOLD status until lineups confirm; auto-upgrade to PLAY when confirmed.

---

## 3. MODELING LAYER (per sport)

### Common framework (`common.py`)
- **Count props (Ks, shots, corners, receptions):** Poisson or negative binomial with a projected mean λ. Prob(over N.5) = 1 − CDF(N).
- **Continuous props (yards, points):** normal or lognormal around projection with sport-calibrated sigma; or 10,000-run Monte Carlo when inputs interact (game script × volume × efficiency).
- **Projection formula (baseline):**
  `λ = weighted_recent_rate × opponent_adjustment × pace/context_adjustment × role_adjustment`
  - Recent form: exponential decay weights (last game weight ~1.0, decaying ~0.85/game, window 10–20 games).
  - Opponent adjustment: opponent's allowed rate vs position ÷ league average.
  - Regress small samples to the mean: `adjusted = (n×player_rate + k×league_rate)/(n+k)` with sport-specific k.
- **Calibration:** every model must output probabilities, and `weekly_review.py` plots predicted prob vs actual hit rate in buckets. If the model says 60% and reality is 52%, apply a shrinkage factor. An uncalibrated model is a losing model.

### MLB specifics
- Strikeout props: pitcher K% × opposing lineup K% vs handedness × expected batters faced (from pitch count trend + team bullpen usage). This is the single best-modeled prop in sports — prioritize it.
- NRFI: P(no run) = P(pitcher A clean 1st) × P(pitcher B clean 1st), adjusted for park and top-3 lineup quality.

### NBA specifics
- Chain: minutes model → usage/role → per-minute rates → opponent/pace adjust → distribution.
- PRA and combo props: use Monte Carlo with correlated components (points and rebounds are mildly negatively correlated for guards, positively for bigs — estimate from player history).

### NFL specifics
- Volume first (targets/carries from game script), efficiency second (YPT/YPC vs coverage/front). Receiving yards = projected targets × catch rate × yards per catch, simulated.
- TD props: red-zone share × team red-zone trips projection → Poisson.

### Soccer specifics
- Shots/SOT: per-90 rate × expected minutes × opponent shot suppression × game state (chasing teams shoot more — tie to match odds).
- Goals (anytime scorer): xG per 90 × minutes × finishing regression → Poisson P(≥1).
- Cards: player foul rate × referee cards/game × match tension index (rivalry, elimination stakes).

---

## 4. DEEP RESEARCH PIPELINE (Claude-powered)

This is where the system uses **you, Claude Code, as an agent** — not just static code.

`deep_dive.py` flags any pick with EV > 6% for a research pass before it can reach MAX confidence. The daily run should invoke Claude (via the Claude Agent SDK or by structuring the run so Claude Code itself performs it) to:

1. **Search the web** for the last 48 hours of news on the player/team: beat-writer reports, coach quotes on role/minutes, lineup leaks, weather updates, motivation angles (eliminated teams, resting starters).
2. **Verify the model's key assumption.** If the edge exists because the model projects 34 minutes and the market seems to price 28, find out WHY the market disagrees. The market is usually right — the research pass must find the reason or the story that the market missed.
3. **Kill-switch questions:** Is there a lineup change the model missed? A pitch-count limit? A minutes restriction? A new starting goalkeeper? Any yes → pick demoted to NO PLAY regardless of model EV.
4. Output a 3–5 sentence research memo attached to the pick with sources and timestamps.

**Rule: model finds candidates, research validates them, only validated edges get bet-sized.**

---

## 5. VALUE ENGINE

### `value_scanner.py`
For every prop with both a model probability and a market line:
1. De-vig the market: implied prob = odds→prob, then remove juice (for two-way markets: p_fair = p_over / (p_over + p_under)).
2. EV% = (model_prob × payout_multiplier) − 1.
3. Rank all edges. Apply confidence tiers:
   - **A (bet 1.0× stake unit):** EV ≥ 7%, research-validated, confirmed lineup, ≥15-game sample.
   - **B (0.6×):** EV 5–7%, validated.
   - **C (0.3× or track-only):** EV 4–5%.
   - Below 4%: log for calibration, never surface as a play.
4. **Sharp/soft comparison:** if Pinnacle (or de-vigged consensus) agrees with the model against a soft book's line, boost confidence one tier. If the model disagrees with sharp consensus, cut confidence one tier — the model is probably wrong.

### `correlation.py` (for PrizePicks/Underdog slips)
- Never combine negatively correlated legs (QB pass yds + own RB rush yds in same game script).
- Flag positively correlated stacks (QB pass yds + WR1 rec yds) — good for lottos, but size DOWN because variance compounds.
- Enforce max 2 legs from the same game per slip.

### `staking.py`
- Kelly fraction: f = (bp − q)/b, then multiply by 0.25 (quarter Kelly).
- Hard caps: 2% per play, 6% per day, stop-loss review triggered at −15% bankroll drawdown (system switches to track-only mode for 7 days and runs a full calibration audit).

---

## 6. DAILY RUNDOWN (the deliverable)

`daily_rundown.py` produces `reports/YYYY-MM-DD.md` (and optionally posts to Discord webhook / emails via SMTP):

```
🏆 EDGE ENGINE DAILY — {date}
Bankroll: $X,XXX | YTD ROI: +X.X% | CLV avg: +X.X% | Record: XX-XX

=== A-TIER PLAYS ===
1. [MLB] Pitcher X Over 6.5 Ks (-115 DK, best price -105 FD)
   Model: 61.2% | Market (fair): 52.4% | EV: +8.8% | Stake: 1.2u
   Why: Opposing lineup 26.1% K vs RHP (3rd highest), 98-pitch avg last 3,
        umpire has +4% called-strike zone. Research memo: [link]
   Risks: bullpen game rumor — status CONFIRMED as of 10:41am.

=== B-TIER ===
...
=== SLIP OF THE DAY (PrizePicks) ===
2-leg correlated: ... | Combined model prob 41% vs 36% breakeven
=== NO-PLAYS THAT LOOKED TEMPTING (and why we passed) ===
...
=== YESTERDAY'S RESULTS + CLV GRADES ===
...
```

Include the no-plays section every day — it builds trust in the edge threshold and teaches pattern recognition.

---

## 7. AUTOMATION

`cron_setup.sh` — schedule per sport's information rhythm:
- **9:00 AM ET:** overnight data pull, injury sweep, first scan.
- **11:30 AM ET:** MLB lineups drop → MLB module rerun → morning rundown published.
- **4:30 PM ET (NBA season):** early lineup confirmations → NBA rerun.
- **60 min before first pitch/tip/kickoff:** final validation pass, kill-switch check, final rundown update.
- **Overnight (3 AM):** grade yesterday, log closing lines, update CLV ledger, retrain rolling averages.

Alternative: `github_actions.yaml` with scheduled workflows so it runs without a local machine. Secrets (API keys, webhook URLs) in repo secrets, never committed.

---

## 8. TRACKING, REVIEW, AND MODEL IMPROVEMENT

`weekly_review.py` every Monday:
1. **CLV report:** average CLV by sport, by prop type, by tier. Any category with negative CLV over 50+ picks gets suspended pending model review.
2. **Calibration curves** per model.
3. **ROI by segment:** find where the actual edge lives (e.g., MLB Ks profitable, NBA assists bleeding) and reallocate.
4. **Variance context:** show the user the math — even a true 55% bettor has losing weeks ~30% of the time. Report probability ranges, not just results, to prevent tilting the config after normal variance.

---

## 9. BUILD PHASES (execute in order)

- **Phase 1 (Day 1):** repo scaffold, config system, SQLite ledger schema, odds ingestion + line-movement logging. Deliver: lines flowing into the DB.
- **Phase 2 (Days 2–3):** MLB module end-to-end (ingest → K-prop model → value scanner → rundown). MLB first: best free data, most modelable props, games every day for fast feedback.
- **Phase 3 (Days 4–5):** staking, CLV tracker, daily rundown generator, cron automation. **Begin 100% track-only paper period.**
- **Phase 4 (Week 2):** NBA + NFL modules, correlation engine, PrizePicks/Underdog slip builder.
- **Phase 5 (Week 2–3):** Soccer/World Cup module, deep research pipeline, Discord/email delivery.
- **Phase 6 (ongoing):** weekly review loop, calibration shrinkage, suspend/promote prop categories by CLV.

**Mandatory gate: minimum 200 tracked picks in paper mode with positive CLV before any real-money sizing is displayed.** Until then, all stakes display as "units (paper)".

## 10. TESTING REQUIREMENTS
- Unit tests: Poisson/MC utilities produce known probabilities for known inputs.
- Backtest harness: replay last 30 days of cached lines + results per sport; report ROI, CLV, calibration before enabling any new model.
- Data-freshness assertions: any input older than its max staleness (odds 30 min, injuries 3 hr, stats 24 hr) blocks a pick from A-tier.
