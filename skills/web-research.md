# Web research — the keyless path

**This is the primary data path, not the fallback.** API keys are an
accelerator. The web is what always works.

Proven in practice: full analyses of a FIBA World Cup knockout round, a DWCS
card, and an NFL game in Melbourne were each built end to end with **zero API
keys** — real lines, real injury news, real weigh-in results, all from search.

---

## 1. The three tiers, in the order you try them

| Tier | Source | Needs | Reality |
|---|---|---|---|
| **1** | **WebSearch** | nothing | Runs server-side. Works even when the machine's network is locked down. **Always try this first.** |
| **2** | Keyless HTTP (`lib/free_sources.py`) | nothing | ESPN scoreboard with consensus lines (incl. **FCS via group 81**), MLB StatsAPI, Open-Meteo. Blocked on some sandboxed machines. |
| **3** | Keyed APIs (`lib/fetch_odds.py`, `lib/fetch_cfb.py`) | a key | Richest data. Optional. |

**WebFetch is frequently blocked** by network egress policy even when WebSearch
works. Don't burn turns retrying it — if a fetch is refused once, pivot to
search and keep moving.

---

## 2. Search patterns that actually return prices

Generic searches return previews. **Specific ones return numbers.** These
patterns have worked repeatedly:

### Game lines
```
"<away> vs <home> odds spread total moneyline <date>"
"<team> <team> betting preview picks odds week <N>"
"<matchup> prediction odds pick"
```
The reliable carriers of actual numbers are betting-preview articles:
DraftKings Network, Covers, Action Network, ClutchPoints, Bettors Insider,
SportsBettingDime, WagerTalk, CBS Sports betting, FanDuel Research. They quote
real prices in prose, and search surfaces them.

### Player props
```
"<team> vs <team> player props odds picks"
"<player> prop line over under <stat> <date>"
"<matchup> anytime touchdown scorer odds"
```
Props are quoted less consistently than sides. **Expect to find some and not
others, and say which.**

### Availability and news
```
"<team> injury report <date>"
"<team> starting lineup <date>"
"<player> status questionable out <date>"
"<event> weigh-in results"          # combat sports
"<team> depth chart week <N>"       # college football
```

### Form and stats
```
"<team> stats <season> points per game record"
"<player> <season> stats per game"
"<league> standings results week <N>"
```

### Verifying a roster claim — do this, don't assume
```
"<player> <team> <year> roster signed traded"
```
**This has already caught a real error.** Two legs of a user's parlay looked
wrong to me — a receiver who had spent 12 years elsewhere, another who'd been
traded the prior season. Both had in fact changed teams in the offseason, and
the slip was legitimate. **Verify before you assert.** Rosters move.

---

## 3. Source reliability

**Trust for prices:** betting-preview articles from the books' own media arms
(DK Network, FanDuel Research) and established odds sites. They quote the price
they were actually looking at.

**Trust for news:** beat writers first, then national aggregators. In college
football there is **no mandated injury report** — local reporting is the only
source, which is exactly why an edge exists there.

**Trust for stats:** official league sites, Pro Football Reference / Sports
Reference, ESPN. Be alert to sites reporting *partial* records — one source
listed a fighter at 9-0 while another showed "5 wins, 3 by decision" with full
scorecards. **When two sources conflict, say so and weight the one with more
verifiable detail.**

**Never trust:** a number you cannot attribute. If you can't name where it came
from, it doesn't go in the analysis.

---

## 4. From research to a priced bet

Search gives you prices. `lib/manual.py` turns them into decisions — no key, no
network.

```bash
# One market, right now
python3 -m lib.manual devig --labels "Chiefs,Bills" --prices 118 -128
python3 -m lib.manual edge --fair 123.1 --offered 132
python3 -m lib.manual shop --prices "pinnacle:118,draftkings:132,fanduel:115"

# A whole slate you assembled
python3 -m lib.manual template > slate.json     # starter file
# ...fill in per-book prices from research...
python3 -m lib.manual board slate.json
```

A hand-built board runs through the **exact same** engine as the live feed:
sharp-book anchoring, power/multiplicative devig, soft-book shopping,
confidence tiering, Kelly staking. **A manually-entered board is a first-class
board.**

`board` also audits itself and will tell you when a market is **one-sided**
(you wrote down one side, so it cannot be devigged) or has **no sharp anchor**.
Both are silent failures otherwise.

---

## 5. Record provenance as you go

Every price and every claim carries **where** and **when**:

> Pinnacle Chiefs +118 — read via search 4:10pm ET Sept 12
> Kittle Achilles return — CBS Sports injury piece, Sept 11

Put it in the board file's `note` field. Put it in the analysis. A number
without provenance is indistinguishable from a number you made up, including to
you, three days later.

---

## 6. What to do when you can't find it

**Say you couldn't find it.** Then keep going on everything else.

- No price found → you can rank by probability but **cannot compute EV.** State
  that plainly and give trigger prices instead: "I'd need +150 or better."
- No sharp book → anchor on the median, **say so, and cut confidence.**
- Only one book's price → the market cannot be devigged. Say the edge is
  unconfirmed.
- Conflicting sources → report both, weight the more detailed one, flag it.

The correct output when you cannot retrieve a board is "I couldn't pull the
board," not a board. This is the rule the whole desk rests on and it applies
identically to web research.

---

## 7. Efficiency

Searches cost time and the user's budget. Be deliberate:

- **3-5 well-aimed searches beat 15 scattered ones.** Plan what you need before
  you start.
- Batch related questions into one query — "odds injury report start time" often
  returns all three.
- Once you have the slate, **research only the games you'd actually bet.** Don't
  deep-dive a card you've already priced as no-play.
- Don't re-search something you already have. Read your own earlier results.

---

## 8. The check before you present

- [ ] Every price attributed to a source and a time
- [ ] Roster/team membership verified, not assumed
- [ ] Conflicting sources flagged rather than silently resolved
- [ ] Everything unfound stated as unfound
- [ ] Prices run through `lib.manual`, not arithmetic in your head
- [ ] Anchor tier stated (sharp / median / single book) and confidence set to match
