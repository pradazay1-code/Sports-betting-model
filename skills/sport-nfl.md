# NFL

Sixteen games a week, the deepest market in American sports, and the hardest to
beat. Limits are highest, the closing line is sharpest, and the public money is
enormous — which is the only reason edges exist at all.

---

## 1. The number is everything: key numbers

NFL margins cluster. This is the single most important sport-specific fact.

| Margin | Approx. frequency | What a half point costs crossing it |
|---|---|---|
| **3** | ~9-10% | 25-30 cents |
| **7** | ~6-7% | 15-20 cents |
| **6** | ~4.5% | 10-12 cents |
| **10** | ~4% | 10 cents |
| **14** | ~3% | 8-10 cents |
| **4** | ~3.5% | 8-10 cents |

Consequences you apply without thinking:

- **-2.5 → -3.5 is not a small move.** It is the most expensive half point in
  sports betting. Never treat it as one line among many.
- +3 is worth materially more than +2.5. If you like a dog at +2.5 and can get
  +3 elsewhere for 10-15 cents of juice, **take the number**, not the price.
- Getting off 3 onto 3.5 as a favorite backer is usually worth paying for.
- Totals have soft key numbers at 41, 44, 47, 51 — real, but a fraction of the
  strength of the spread numbers.
- Buying the half point off 3 at standard 10-cent pricing is one of the few
  half-point buys that's actually correctly priced or better. Books that only
  charge 10 cents to move 2.5 → 3 are giving it away.

## 2. Model layer

### The core stat: EPA per play

Expected Points Added per play, offense and defense, **split by early-down pass
rate.** The split is what makes it useful.

Teams that pass on early downs generate more EPA per play than their talent
implies, because early-down passing is simply more efficient than early-down
running. A raw EPA ranking quietly encodes play-calling philosophy as if it were
team quality. Split it out or you'll systematically overrate pass-happy teams
and underrate run-heavy ones — and the market already knows the difference.

```
python3 -m lib.fetch_stats nfl-team --season 2025
python3 -m lib.fetch_stats nfl-team --season 2025 --weeks 6   # recent form
```

The pull filters to run/pass plays with win probability between 5% and 95%.
Garbage time inflates EPA against defenses that have stopped caring, and it is
the most common way a bad offense looks average in the aggregate.

### Supporting stats, in rough order of usefulness

1. **Success rate** — the consistency counterpart to EPA. A team with high EPA
   and low success rate is living on explosives, which is far more volatile
   week to week and regresses harder.
2. **Pressure rate and sack rate**, both generated and allowed. Pressure rate is
   stickier than sack rate — sacks are noisy, pressures aren't.
3. **Explosive play rate** (20+ yards). Drives the variance of the whole game.
4. **DVOA-style opponent adjustment.** Raw EPA off a soft schedule is a trap;
   this is the correction. The `nfl-team` pull does **not** apply it — do it
   yourself or note that it's missing.
5. **Special teams DVOA.** Small, real, and almost totally ignored by the
   public. Worth up to a point in the spread on the extremes.

### Regression flags — NOT predictors

These tell you a team's record is lying. They do **not** predict future
performance, and using them as predictors is a classic amateur error:

- **Red zone TD rate.** High RZ efficiency regresses hard. A team winning on a
  70% red zone TD rate is not that good.
- **Third down conversion rate.** Same. It's mostly a function of down-and-
  distance, which is a function of early-down efficiency you already counted.
- **Turnover margin.** The single noisiest thing in football. Fumble recovery
  rate is essentially a coin flip; interception rate is only somewhat sticky.
- **One-score game record.** A 6-1 record in one-score games is variance wearing
  a narrative.

When a team's record is much better than its EPA, the market usually has this
priced already. The edge is in the games where the *public* hasn't caught up,
not where the market hasn't.

## 3. Situational adjustments

- **Rest.** Bye week is worth roughly a point, less than folklore claims.
  Thursday games after a Sunday are worth more against the team that traveled.
- **Travel.** West-to-east 1pm starts are a real, small, well-documented
  disadvantage. Three time zones is worth a fraction of a point, not the two
  points people quote.
- **Division familiarity.** Division games run tighter than the model says.
  Compress your projected margin toward the mean, especially for road dogs.
- **Weather.** See below. It's the biggest situational factor by a wide margin.
- **Short week + travel + a good defense** is the combination that actually
  produces value on dogs, not any one of them alone.
- **Look-ahead and letdown spots** are mostly narrative. Don't build a bet on
  one; use it at most as a tiebreaker.

## 4. Weather

```
python3 -m lib.fetch_news weather --venue "Highmark Stadium" --at 2026-01-11T13:00
```

What actually matters, in order:

1. **Wind above 15 mph.** This is the one that moves totals. It suppresses the
   deep passing game and destroys field goal accuracy beyond 40 yards. Above
   20 mph, unders and favorites-in-run-heavy-scripts get real.
2. **Sustained rain.** Modest effect. Less than people think — modern footballs
   and modern gloves handle wet fine. Mostly a fumble-variance story.
3. **Temperature.** Almost irrelevant on its own. Cold-weather narratives are
   mostly noise once you control for wind.
4. **Snow.** Visually dramatic, and the market overreacts to the forecast. Often
   a *fade* opportunity on the under if the total has moved 4+ points on snow
   that's forecast to be light.

**Wind is the signal. Everything else is mostly noise.**

## 5. The real-time layer — check last

- **Inactives drop 90 minutes before kickoff.** This is the single highest-value
  moment in the NFL week. Lines move hard and fast.
- **QB status is worth 4-8 points** depending on the drop-off to the backup.
  Nothing else in the sport is close. A questionable QB tag is worth waiting on.
- Practice participation Wednesday→Friday is the leading indicator. DNP Friday
  usually means out.
- OL injuries are systematically underpriced by the public; skill-position
  injuries are systematically overpriced.
- **Reverse line movement matters more in NFL than anywhere**, because the
  public volume is so large. A line moving *toward* the side with a minority of
  tickets is the clearest sharp-money signal available.

## 6. Market structure

- Openers hit Sunday night / Monday at the offshore books and Circa. Those are
  the sharpest numbers of the week and also the lowest limits.
- The number moves toward the public through the week; the sharpest side is
  usually available early, the best *price* on a public side late.
- Sunday morning has the last real information (inactives, weather updates) and
  the largest limits.
- **Beating the close is the whole game in NFL.** If you're consistently getting
  a better number than the close, you're winning even during a losing stretch.

## 7. Checklist for a full write-up

- [ ] Sharp price (Pinnacle/Circa), open vs. current, direction of movement
- [ ] Ticket % vs. handle % — is there reverse line movement?
- [ ] EPA/play both sides, opponent-adjusted, with early-down pass rate split
- [ ] Success rate and explosive rate — is the EPA consistent or explosive-driven?
- [ ] Pressure rate matchup vs. the opposing OL
- [ ] Regression flags (RZ, 3rd down, turnovers, one-score record)
- [ ] Rest, travel, division
- [ ] Weather, wind specifically, at kickoff hour
- [ ] Injuries — QB first, then OL, then everyone else
- [ ] **Key number check**: what number am I actually getting, and at what price?
- [ ] Line shop every book before recommending
