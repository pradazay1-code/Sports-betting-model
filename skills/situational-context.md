# The situational layer — news, rotation, game plan, motivation

**This file outranks the model.** A perfect efficiency rating on a team whose
starting quarterback was ruled out ninety minutes ago is a perfect number about
a team that does not exist.

Run this layer **last, immediately before a recommendation**, and re-run the
number if anything material moved. In college football specifically, the
situational layer beats the ratings layer more often than in any other sport.

---

## 1. The research protocol

Run these in order. Stop early only when you have confirmed there is nothing new.

### Step 1 — Availability (highest value, always)
```
"<team> injury report <date>"
"<team> depth chart week <N>"
"<player> status <date>"
```
- **Prefer sources under 24 hours old. Timestamp everything you cite.**
- A three-day-old injury report is not news, it is history.
- College football has **no mandated injury report**. Beat writers and local
  radio are the primary source, not a league feed. This is precisely why the
  edge exists.

### Step 2 — Who is actually taking snaps
```
"<team> starting quarterback week <N>"
"<team> QB depth chart" / "<team> transfer portal QB"
```
- Portal-era depth charts change between seasons *and within them*. Verify the
  starter every week. Never assume last week's starter.
- Identify the **backup** too. The drop-off is the number, not the starter's
  name.

### Step 3 — Coaching and scheme
```
"<team> coordinator" / "<team> coaching change" / "<team> interim coach"
"<team> play calling changes"
```
- A **new coordinator** or an **interim head coach** invalidates a meaningful
  share of your historical data. Teams under interims frequently play looser and
  faster — and historically over-perform the number in their first game.
- A coach on the hot seat calls games differently. So does a coach who has
  already been fired and is finishing the season.

### Step 4 — Motivation and schedule spot
```
"<team> vs <opponent> rivalry" / "<team> bowl eligibility"
"<team> next opponent" (for lookahead spots)
```
See §4 below.

### Step 5 — Weather, for outdoor venues
```
python3 -m lib.fetch_news weather --venue "<stadium>" --at <ISO hour>
python3 -m lib.venues lookup "<team>"     # coords, roof, surface, altitude
```

### Step 6 — Market confirmation, last
```
python3 -m lib.fetch_cfb lines --week <N> --team "<team>"
```
- Compare opener to current. Which way did it move?
- **Line moving against the ticket majority = sharp money.** That signal
  outranks your own read.
- In small markets, weight **limit increases** over move size — a low-limit
  market moves on almost nothing.

---

## 2. Converting news into points

Rough priors for football. These are `[READ]`, not measurements — state them as
such and adjust for the specific case.

| Event | Points | Notes |
|---|---|---|
| Starting QB out (FBS, good backup) | **4-7** | |
| Starting QB out (FBS, true freshman/walk-on backup) | **10-14** | Bigger in G5 and FCS |
| Starting QB out (FCS) | **7-14** | Depth is thinner; range is wider |
| Star RB out | **1-2.5** | Most over-priced injury by the public |
| Top OL starter out | **1.5-3** | Most *under*-priced by the public |
| Top CB out vs a pass-heavy offense | **1.5-3** | Matchup dependent |
| Interim head coach, first game | **1-3 toward the team** | Historically over-performs |
| New coordinator, first month | widen your error bars | Don't price it; distrust your data |
| Wind 15-20 mph | **2-4 off the total** | The one weather factor that reliably moves |
| Wind 20+ mph | **4-7 off the total** | Also kills FG accuracy beyond 40 |

**Skill-position injuries are systematically over-priced by the public. Offensive
line injuries are systematically under-priced.** That asymmetry is durable and it
is where news-based edges actually live.

---

## 3. Weather — what matters and what doesn't

In order:

1. **Wind above 15 mph.** The only weather factor that reliably moves a total.
   It suppresses the deep passing game and destroys field goals beyond 40 yards.
   **Direction relative to the field matters** — `lib/fetch_news.py` resolves it.
2. **Sustained rain.** Modest. Less than the public thinks — modern balls and
   gloves handle wet. Mostly a fumble-variance story.
3. **Extreme cold** (under ~20°F). Real but secondary to the wind that usually
   accompanies it. Don't double-count.
4. **Heat and humidity** in September. Genuinely matters for northern teams
   playing in the South, and it is a **fourth-quarter** effect, like altitude.
5. **Snow.** Visually dramatic, and the market **overreacts to the forecast**.
   If a total has moved 4+ points on snow forecast to be light, that is a fade.

**Confirm retractable roofs are actually open.** `lib/venues.py` flags them. The
books know; if you don't, you're guessing.

---

## 4. Motivation and schedule spots

Real, but softer than the narrative industry claims. Use them as **tiebreakers
and confidence modifiers**, not as the basis for a bet.

**Genuinely predictive:**
- **Bowl eligibility.** A 5-6 team playing its last chance at a bowl is playing
  for something concrete. This is the most reliable motivational angle in CFB.
- **Rivalry games compress spreads.** Favorites under-perform; take the points.
  The effect is real and it is priced — but usually not fully.
- **Playoff/conference-title implications**, late season.
- **Coaching changes announced mid-season** — the locker room reaction is real
  and unpredictable in both directions. Widen your error bars, don't pick a side.
- **Senior day** — mild, real.

**Mostly narrative — do not build a bet on these:**
- "Revenge game" for a regular-season loss
- "They're due"
- Generic letdown claims without a specific sandwich spot

**The legitimate version of letdown/lookahead:** a specific, identifiable
sandwich — a money game or a bottom-tier conference opponent scheduled the week
before a rivalry game or a ranked matchup. Name the specific next opponent or it
isn't a real spot.

---

## 5. Travel and body clock

- **Cross-country early kickoffs** (a West Coast team at noon Eastern) are a
  real, documented, small disadvantage. Worth a fraction of a point, not the two
  the narrative claims.
- **Altitude** is a fourth-quarter effect. `python3 -m lib.venues edge` prices
  the differential. Weight it toward second-half and live markets.
- **FCS bus travel** has no FBS equivalent — a 9-hour bus ride is a genuine
  physical disadvantage. See `skills/sport-fcs.md`.
- **Hawaii** is its own category, in both directions: the trip out, and the
  wreckage of the following week for the visiting team.

---

## 6. Officiating

- **Penalty rates vary meaningfully by conference.** Some crews call tight
  holding, some let it go. It matters most for totals and for teams that live on
  explosive plays into contested coverage.
- Replay-review standards differ by conference.
- This is a small edge and a real one, but it is never the basis for a bet on
  its own — it's a tiebreaker.

---

## 7. The discipline

- **Timestamp every claim.** "As of Friday 4:15pm ET" or it doesn't go in.
- **If a fetch fails, say it failed.** The correct output when you cannot reach
  an injury report is "I could not confirm availability," not an assumption.
- **If a recommendation is made before availability is confirmed, mark it
  provisional** and say what would change it.
- **News that is already in the price is not an edge.** If a QB was ruled out
  Tuesday and the line moved six points Tuesday, there is nothing left. The edge
  is in news the market has not absorbed — which in college football usually
  means local reporting on a non-marquee team.

---

## 8. Pre-recommendation checklist

- [ ] Availability confirmed, sourced, timestamped under 24h
- [ ] Starting QB confirmed — and the backup identified
- [ ] Coaching/coordinator status checked
- [ ] Weather pulled for the actual kickoff hour, wind direction resolved
- [ ] Venue HFA and altitude differential priced
- [ ] Motivational spot named specifically, or explicitly dismissed
- [ ] Line movement checked against ticket percentage
- [ ] Asked: **is this news already in the price?**
