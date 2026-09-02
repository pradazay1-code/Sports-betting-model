# The Desk

A persistent sports betting analysis agent that lives in files, not in a
conversation. Run it through Claude Code every day.

**The Desk** is a professional bettor and former sportsbook trader: market-first,
allergic to fake precision, and willing to tell you the slate has no edge.
Most days that's the answer.

---

## Setup

```bash
# 1. Dependencies (uv is fastest; a plain venv works fine too)
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt

# or:  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 2. API key
cp .env.example .env
# then put your key from https://the-odds-api.com/ into ODDS_API_KEY

# 3. Create the bet log
.venv/bin/python -m lib.db init

# 4. Verify
.venv/bin/python smoke_test.py
```

The Odds API's free tier is **500 requests a month**. Everything is cached with
a TTL so a careless loop can't burn it in an afternoon. Check what's left:

```bash
.venv/bin/python -m lib.fetch_odds quota
```

## Daily use

Open Claude Code in this directory. `CLAUDE.md` loads automatically and is the
agent's operating manual — persona, discipline rules, and the analytical engine.

| Command | What it does |
|---|---|
| `/slate <sport> [date]` | Full card, devigged, top 3-5 priced edges. Says "no plays" when that's true. |
| `/best <sport>` | Ranked plays with **win probability and edge reported separately**. The honest answer to "give me your best picks." |
| `/analyze <game or fight>` | Deep dive: market read → model → stats → news → discrepancy → recommendation. |
| `/parlay <request>` | Builds it, prices it honestly, shows the hold. |
| `/props <player or game>` | Prop analysis with usage context and book-by-book shopping. |
| `/log <bet>` | Writes to `bets.db`. |
| `/clv` | Closing line value, ROI, expected vs. realized, calibration. |
| `/review` | Weekly self-audit. |

## The CLI, directly

Every calculation the agent makes is a command you can run yourself. The agent
is instructed to shell out to these rather than do arithmetic in its head —
arithmetic errors in a betting analysis are indistinguishable from lies.

```bash
# Devig a market and price an offer against it
python3 -m lib.odds devig -110 -110
python3 -m lib.odds devig 118 -128 --offered 132 --outcome 0

# Edge, Kelly, parlays, hold, CLV
python3 -m lib.odds ev --fair -105 --offered +100
python3 -m lib.odds kelly --prob 0.55 --odds +100
python3 -m lib.odds parlay -110 -110 -110 -110
python3 -m lib.odds parlay -110 -110 +150 --fair 0.50 0.52 0.38 --correlation 0.12 --rr 2
python3 -m lib.odds clv --taken +100 --closed -110

# Is my edge real, or am I lucky?
python3 -m lib.backtest breakeven --odds -110
python3 -m lib.backtest sample-size --roi 0.05      # ~2,200 bets to prove it
python3 -m lib.backtest drawdown --prob 0.55 --bets 500
python3 -m lib.backtest streak --prob 0.55 --bets 500
python3 -m lib.backtest reality-check --record 12-3
.venv/bin/python -m lib.backtest evaluate           # backtests your own bets.db

# The board
.venv/bin/python -m lib.fetch_odds sports
.venv/bin/python -m lib.fetch_odds best --sport nfl --min-win-prob 0.65
.venv/bin/python -m lib.fetch_odds board --sport nfl
.venv/bin/python -m lib.fetch_odds edges --sport nfl --min-ev 0.02

# Real-time layer
.venv/bin/python -m lib.fetch_news weather --venue "Wrigley Field"
.venv/bin/python -m lib.fetch_news injuries --sport nba
.venv/bin/python -m lib.fetch_news pitchers

# Stats
.venv/bin/python -m lib.fetch_stats check          # what's installed
.venv/bin/python -m lib.fetch_stats nfl-team --season 2025
.venv/bin/python -m lib.fetch_stats mlb-pitcher --name "Tarik Skubal"

# The log
.venv/bin/python -m lib.db log --sport NFL --event "KC @ BUF" --market h2h \
    --side KC --price 132 --book draftkings --stake 0.76 --fair-prob 0.4482
.venv/bin/python -m lib.db close --id 1 --closing -110
.venv/bin/python -m lib.db grade --id 1 --result win
.venv/bin/python -m lib.db report
.venv/bin/python -m lib.db calibration
```

`lib/odds.py` is stdlib-only, so the price math runs with no venv and no
network.

## Layout

```
CLAUDE.md                 persona + operating rules — the core file
.claude/commands/         the seven slash commands
skills/
  devig.md                no-vig / fair-odds math reference
  parlay-construction.md  correlation + SGP pricing
  probability-reality.md  why no pick is guaranteed, and what to say instead
  book-behavior.md        how each sportsbook actually operates
  sport-{nfl,nba,mlb,ufc,bkfc,generic}.md
lib/
  odds.py                 conversions, 4 devig methods, EV, Kelly, parlays, CLV
  backtest.py             edge-detection stats: sample size, drawdown, significance
  cache.py                TTL JSON cache
  fetch_odds.py           The Odds API + line shopping + edge finding
  fetch_stats.py          per-sport stat pulls
  fetch_news.py           injuries / lineups / weather
  db.py                   SQLite bet log + CLV tracking
tests/                    138 tests, all offline
data/cache/               gitignored
bets.db                   gitignored
```

## How it actually works

**Devig the sharp book. Bet the soft book. Never the same price for both.**

The anchor order is Pinnacle → Circa → BetOnline/Bookmaker tier → market median.
Soft books (DraftKings, FanDuel, ESPN Bet, Fanatics) are where you *place* the
bet, never where you *estimate* the probability. Odds pulls include the `eu`
region because that's where Pinnacle lives; a US-only pull leaves you devigging
noise against noise.

Two-way markets devig with **power**, multiway with **multiplicative**. When the
methods disagree by more than ~1.5 points of probability, the desk quotes a
range instead of a point estimate and lowers confidence.

Staking is **quarter Kelly with a hard 2u ceiling**. Anything under ~2% EV after
devig is inside the error bars of the devig method itself — that's not a thin
edge, it's no edge.

## On "guaranteed picks"

There aren't any. If a guaranteed pick existed the market would price it away —
that's the mechanism, not a disclaimer. What the agent gives you instead is the
genuinely useful version: plays ranked by edge, with **win probability and EV
reported as the separate things they are.**

A -800 favorite wins ~89% of the time and is a terrible bet if its true
probability is 85%. High win rate and good bet are different axes, and `/best`
never lets one stand in for the other.

`lib/backtest.py` is there so you can check any claim, including the agent's:

```
$ python3 -m lib.backtest drawdown --prob 0.55 --bets 500
  chance of LOSING money anyway : 11.4%
  median longest losing streak  : 7 bets

$ python3 -m lib.backtest sample-size --roi 0.05
  BETS REQUIRED   : 2,231

$ python3 -m lib.backtest reality-check --record 12-3
  95% CI on true  : 54.8% to 93.0%
```

A bettor with a real 5% edge still loses money 11% of the time over 500 bets,
hits a 7-bet losing streak more often than not, and needs ~2,200 bets before the
record itself proves anything. That's what a genuine edge looks like from the
inside.

## Answering normal questions

The betting persona applies to betting questions. Ask it to debug a script or
explain something and it answers like Claude Code normally would — no epistemic
tags, no market metaphors, no steering back to the card.

## The rules the agent won't break

1. Never fabricate data. Missing → say so and lower confidence.
2. Never recommend under ~2% EV.
3. Never more than 2u.
4. Never chase. Asking for a bigger play after a loss gets refused.
5. Tilt gets flagged.
6. Every recommendation carries a confidence level and a "what would change my
   mind."
7. `[FACT]` / `[MODEL]` / `[READ]` are labeled and never blurred.
8. Track everything.
9. No locks. Ever.

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

All offline — they use fixtures, so they never touch the network or burn quota.

## Notes

- `.env` is gitignored. Never commit a key.
- `bets.db` and `data/cache/` are gitignored.
- Closing lines have to be recorded after the fact (`db close`). Without them
  there is no scoreboard — CLV is the only honest measure of whether this is
  working, and results over a short sample are noise.
