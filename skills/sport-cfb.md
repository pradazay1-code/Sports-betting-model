# College football (FBS)

The softest major betting market in American sports, and the reason is
structural: there are **134 FBS teams**, books price every one of them every
week, and they cannot sharpen them all. The edge is not in knowing Alabama is
good. It is in the games nobody at the book had time to look at twice.

Load `skills/sport-fcs.md` for FCS and for FBS-vs-FCS money games.
Load `skills/situational-context.md` before any recommendation — in this sport
the situational layer outweighs the ratings layer more often than in any other.

---

## 1. Why raw stats are worthless here

**Nobody plays a comparable schedule.** An SEC team's 380 yards allowed and a
Sun Belt team's 380 yards allowed are not the same number and are not close.
Every stat you use must be opponent-adjusted, and every stat you see quoted on
television is not.

Second, and nearly as important: **garbage time is everywhere.** College
football produces 40-point blowouts weekly. Unfiltered stats let a bad team's
fourth-quarter yardage against walk-ons masquerade as competence, and let a good
team's defense look worse than it is. Always filter.

```
python3 -m lib.fetch_cfb advanced --team Oregon     # garbage time excluded by default
```

---

## 2. The rating spine

### SP+ — start here
Bill Connelly's opponent-adjusted efficiency rating, expressed as points per game
above average against an average schedule.

**The difference between two teams' SP+ ratings, plus a venue-specific home
edge, is a defensible first-pass spread.**

```
python3 -m lib.fetch_cfb sp
python3 -m lib.fetch_cfb spread --home Wyoming --away Hawaii
```

That projection knows nothing about injuries, weather, motivation, or who is
taking snaps. It is a starting point for disagreement with the market, not a
projection to act on.

### Cross-checks
- **FEI** — drive-based rather than play-based. Useful when the two disagree:
  a big SP+/FEI split usually means a team is winning on explosive plays rather
  than on consistency, which is the more fragile profile.
- **SRS / Elo** — margin-based. Quick sanity checks, not primary.
- **FPI** — ESPN's. Public, and therefore already in the price.

### Talent composite — the blowout predictor
```
python3 -m lib.fetch_cfb talent
```
Aggregated recruiting ratings. **Talent predicts blowouts better than efficiency
does**, because depth shows up in the fourth quarter: a talent chasm means the
backups are also better. Reach for this on large spreads, on money games, and
whenever you are deciding between a side and a large alternate number.

The **blue-chip ratio** (share of roster rated 4- or 5-star) is the cleanest
version of this idea. Historically, no team has won a national title with a
blue-chip ratio below ~50%.

### Returning production — the year-over-year predictor
```
python3 -m lib.fetch_cfb returning --team Georgia
```
The share of last season's usage that returns. The single best predictor of
year-over-year change, and **systematically mispriced in the portal era**
because the public anchors on last year's record and the recruiting-class
headline instead of on who is actually back. A team returning 75% of production
off a 7-5 season is a very different bet than a team returning 30%.

---

## 3. The stats that matter, in order

1. **Success rate** — the down-to-down consistency metric. 50% of needed yards
   on 1st down, 70% on 2nd, 100% on 3rd/4th. More predictive than yards.
2. **Explosiveness (PPA / IsoPPP)** — points added on successful plays. A team
   high in explosiveness and low in success rate is living on big plays, which
   **regresses hard and is much more volatile week to week.** Fade them against
   the number when the market has priced last week's blowup.
3. **Havoc rate** — TFLs + forced fumbles + interceptions + pass breakups, over
   total plays. The best single defensive disruption metric, and it travels
   better than yards allowed.
4. **Finishing drives** — points per scoring opportunity (drive reaching the
   opponent's 40). Separates offenses that move the ball from offenses that
   score. A team with good yardage and bad finishing is a regression candidate
   **upward**, and the market usually has them cheap.
5. **Field position / average starting field position** — massively
   under-discussed. Special teams and punting create real point swings in a
   sport with enormous special-teams variance.
6. **Line yards / stuff rate** — the trenches. Predicts short-yardage and
   goal-line conversion, which drives the total.

---

## 4. Key numbers — NOT the NFL's

This is where NFL bettors lose money in college football.

**The margin distribution is much flatter.** Scoring is higher, variance is
higher, and the concentration on 3 and 7 that dominates NFL pricing is far
weaker here.

- **3 and 7 still matter most**, but they carry meaningfully less weight than in
  the NFL. Buying a half point onto 3 is worth much less.
- **10, 14, 17, 21** matter for the large spreads this sport actually produces.
- Above about 14 points, key-number logic is largely noise — the distribution is
  smooth out there. **Do not pay a premium for a half point on a 24.5.**
- Totals key numbers are weak. Scores are high and spread out.

**Practical consequence:** in college football, take the better *price* more
often than the better *number*. The reverse of the NFL instinct.

---

## 5. Large spreads — a different game

College football produces spreads the NFL never sees. They behave differently:

- **Big favorites cover less often than the number implies**, because winning
  coaches empty the bench. A 35-point favorite up 42-7 in the fourth is running
  dive plays with the third string.
- That same dynamic makes **second-half unders** and **team-total unders on the
  favorite** live in blowout spots.
- Conversely, a favorite whose backup QB is a genuine prospect may keep scoring.
  Know the depth chart, not just the starter.
- **Alternate spreads are frequently mispriced** relative to the main line, more
  so than in the NFL, because the books' derivative pricing is coarser out at
  the tails.

---

## 6. Quarterbacks

**Backup QB drop-off is far more severe than in the NFL.** In the NFL a backup
is a professional. In college football he may be a true freshman who has taken
no meaningful snaps.

- QB injury news is the highest-value information in the sport. A starting QB
  ruling out is routinely worth **7-14 points** in the smaller conferences.
- **Portal-era QB movement** means a Week 1 depth chart can be unrecognizable.
  Verify who is starting, every week, not once a season.
- Dual-threat vs pocket matters against specific defensive structures — a
  contain-weak defense is a completely different matchup for a running QB.
- Freshman QBs on the road, in a hostile environment, in their first start is
  one of the genuinely reliable fade spots.

---

## 7. Pace and totals

- **Plays per game** varies enormously — tempo offenses run 80+ snaps, ball
  control teams run 58. That is a 35% swing in possessions, dwarfing anything in
  the NFL.
- Project the total from **possessions x efficiency**, not from season scoring
  averages, which conflate pace and quality.
- Clock rules matter: the running-clock-after-first-down rule change compressed
  totals league-wide. Make sure your baseline reflects the current rules, not a
  historical average.
- A tempo team paired with a bad defense is the classic over profile; two ball
  control teams with good defenses is the classic under.

---

## 8. Market structure — where the softness is

- **The Group of 5 and the bottom of the Power 4 are where edges live.** Nobody
  at the book spends their Tuesday on a MACtion Wednesday-nighter.
- Lines open **Sunday with low limits**. Sharp money hits early, the number
  moves toward the public through the week, and Saturday morning brings the
  largest limits.
- Smaller markets move on less money. A single significant bet moves a Sun Belt
  number in a way it never moves an NFL number — which means **line movement is
  a noisier signal here**, and you should weight limit changes over move size.
- **Weekday games (Tue/Wed/Fri) are the softest cards of the week.** They also
  have the lowest limits, which is not a coincidence.
- Injury information is far less standardized than the NFL — there is no
  mandatory league-wide report. **Beat writers and local radio are the edge.**

---

## 9. Checklist for a full write-up

- [ ] Market read: opener vs current, direction, ticket % vs handle if available
- [ ] SP+ both sides, and the first-pass projected spread
- [ ] FEI or SRS cross-check — do they disagree, and why?
- [ ] Success rate and explosiveness — consistent team or big-play team?
- [ ] Havoc rate matchup vs the opposing line
- [ ] Finishing drives — anyone due to regress up or down?
- [ ] Talent composite gap, especially on large spreads
- [ ] Returning production
- [ ] **QB status confirmed** — starter, and who the backup actually is
- [ ] Venue-specific home edge (`python3 -m lib.venues edge --home X --away Y`)
- [ ] Altitude differential if relevant
- [ ] Weather at kickoff hour, wind specifically
- [ ] Situational layer — see `skills/situational-context.md`
- [ ] Pace projection for the total
- [ ] Line shop every book
