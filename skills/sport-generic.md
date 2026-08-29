# Generic sport framework

Fallback for soccer, CFB, CBB, NHL, tennis, esports, and anything else without a
dedicated file. The method is the same everywhere; only the rate stats change.

**The core discipline: be market-anchored and honest about model thinness.**
In a sport you don't have a real model for, the price is carrying almost all the
weight. That's not a failure — it's the correct posture. What you're looking for
is a *specific, articulable* reason the market is wrong, not a general feeling
that a number looks off.

---

## 1. The universal method

1. **Read the sharp price first.** Pinnacle where available. In these sports it
   often isn't, and market median is your anchor — say so and drop confidence.
2. **Devig it.** Power for two-way, multiplicative for multiway (which is most
   soccer, since the draw makes it three-way).
3. **Find a rate stat that predicts better than results do.** Every sport has
   one. See below.
4. **Check the real-time layer** — availability, lineups, weather, motivation.
5. **Ask what you're seeing that the market isn't.** If you can't name it
   specifically, there's no bet. "The number looks off" is not a reason.
6. **Size down.** Model thinness is a real cost. Cap at 1u in sports without a
   dedicated file.

## 2. Rate stats by sport

### Soccer
- **xG and xGA**, per match and rolling over ~10 matches. The single best
  predictor in the sport, and far better than goals scored.
- **Non-penalty xG** — penalties are noisy and don't repeat.
- Shot volume and shot quality separately.
- **Three-way markets: devig multiplicative.** The draw makes power unstable.
- Asian handicap markets have the lowest hold and the sharpest prices — use them
  as the anchor even if you bet the 1X2.
- Fixture congestion and rotation risk, especially in European competition weeks.
- Motivation is real and underpriced: a mid-table team with nothing to play for
  in May is a different team.

### College football
- **SP+, FEI, or a similar opponent-adjusted efficiency metric.** Raw stats are
  meaningless given the schedule disparity — nobody plays a comparable slate.
- Talent gap (recruiting composite) predicts blowouts better than efficiency
  does, because depth shows up late.
- **Huge variance in the spread distribution.** Big numbers are common and
  the key-number logic of the NFL barely applies.
- Key numbers still cluster on 3 and 7, but far more weakly than in NFL.
- Backup QB drop-off is more severe than in NFL.
- Motivation, rivalry, and coaching changes matter far more than in the pros.
- Weather matters more — many stadiums, wide geography, less climate control.

### College basketball
- **KenPom-style adjusted efficiency** (AdjO, AdjD, AdjT) is the standard, and
  the market uses it too — so it's priced.
- Tempo drives totals even harder than in the NBA.
- **Home court is worth more than the NBA** — 3-4 points at real environments,
  and much more at a few specific venues.
- Small samples early in the season make everything noisy through December.
- Foul trouble is a bigger swing than in the NBA (shorter rotations, fewer
  minutes to absorb it).
- Conference tournament motivation and bubble situations are real.

### NHL
- **Expected goals (xG), Corsi, and Fenwick** at 5-on-5. Score-adjusted.
- **Goaltending is the dominant variable and the noisiest.** A hot goalie beats
  every other factor, and you can't predict a hot goalie.
- **Confirmed starting goalie is the highest-value piece of information** in the
  sport. Never bet a puck line before the goalie is confirmed.
- Special teams (PP%, PK%) are noisy over short samples — be careful.
- **Puck line ±1.5 carries the same warning as the MLB run line.** Empty-net
  goals distort it badly late, and one-goal games are extremely common. Quote
  the actual market; never derive it.
- Back-to-backs matter, especially for the goalie.

### Tennis
- **Serve and return points won** are the fundamental units. Everything else
  derives from them.
- **Surface splits are enormous** and the single biggest factor. A clay
  specialist on grass is a different player.
- Head-to-head is mostly overrated narrative, *except* where there's a genuine
  style clash (big server vs. elite returner).
- Fatigue: matches played in the last 7 days, and whether they went five sets.
- Retirement risk is a live concern in-tournament and affects how books settle —
  know your book's rule.
- Rankings lag current form badly, especially post-injury.

### Esports
- **Map pool and side-selection** matter enormously and are frequently unpriced.
- Roster changes and stand-ins can be very recent — verify the roster for *this
  match*, not the org's roster.
- Patch changes reset the meta and invalidate historical data. A pull from
  before a major patch may be worthless.
- Small samples, high variance, low limits.
- **Match-fixing risk is non-trivial in lower-tier events.** Stay in tier-1.

## 3. What to say about confidence

Be explicit about the thinness:

> "I don't have a real model for this sport. I'm anchored on the market price
> and adjusting for [specific factor]. Confidence is low and the stake reflects
> that."

That's a complete and honest analysis. It's much better than dressing up a
market price as a model output.

## 4. Checklist

- [ ] Sharp price, or an explicit note that there isn't one
- [ ] Devig with the right method (multiplicative for anything three-way)
- [ ] The sport's core rate stat, from a source you actually pulled
- [ ] Availability / lineup / roster confirmed for *this* match
- [ ] A **specific, nameable** reason the market is wrong — or no bet
- [ ] Confidence stated honestly, stake capped at 1u
