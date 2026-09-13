# Week 1 and the early season

**The defining fact: there is no current-season data.** Every metric in
`skills/sport-nfl.md` — EPA/play, success rate, pressure rate, DVOA — requires
snaps that have not been played. In Week 1 the entire analytical apparatus you
normally lean on is unavailable, and pretending otherwise is how people lose
money in September.

This file is what to use instead, and what to refuse to use.

---

## 1. What does NOT predict Week 1

Say these out loud when a user cites them:

- **Last season's record.** NFL rosters turn over roughly 25-30% a year. A
  12-5 team that lost its left tackle, both coordinators and three starters on
  defense is not a 12-5 team.
- **Preseason results.** Starters play a quarter at most, schemes are
  deliberately vanilla, and the players deciding those games are cut by
  September. Preseason record has essentially zero predictive value.
- **Last season's EPA, unregressed.** Useful only heavily regressed toward the
  mean and adjusted for personnel change. Raw carryover overrates last year's
  outliers in both directions.
- **"Momentum" from a playoff run.** There are eight months in between.
- **Beat-writer camp optimism.** Every team looks good in August. Every
  quarterback is in the best shape of his life.

## 2. What actually predicts

In rough order of usefulness:

1. **Roster continuity / returning production.** The best available signal.
   Snap-weighted share of last year's production that returns, on each side of
   the ball. Continuity beats talent in September because execution requires
   reps together.
2. **Vegas season win totals.** These encode the market's entire offseason of
   work — free agency, draft, coaching, schedule. They are the single best
   公开 prior on team strength before a snap is played. Use them as your
   baseline, not as something to disagree with casually.
3. **Coaching and coordinator changes.** A new head coach or a new coordinator
   invalidates a large share of your historical data. This does not tell you
   which way to bet — it tells you to **widen your error bars and size down.**
4. **Quarterback continuity specifically.** A returning starter in the same
   system is a different proposition from a new QB, a rookie, or a veteran in
   a new scheme. The largest single Week 1 uncertainty.
5. **Offensive line continuity.** The unit most dependent on playing together.
   Cohesion shows up immediately and is systematically underpriced.
6. **Prior-season EPA, regressed ~35-50% toward league average**, then adjusted
   for the personnel actually on the field.

## 3. The structural edge: offenses lag defenses

**This is the most reliable Week 1 angle and it has a real mechanism.**

Offense requires timing, chemistry, and communication built over reps. Defense
is more reactive and more athletic-instinct-driven. In September:

- Offensive execution is behind where it will be in November.
- Playcalling is deliberately vanilla — nobody shows scheme in Week 1.
- New skill-position players and new linemen have not built timing.
- Penalties and pre-snap errors run high.

**Practical consequence: Week 1 totals lean under.** Treat it as a genuine
prior, not a lock — it is a modest historical edge, not a large one, and it is
partly priced. Reach for it hardest where:
- Either offense has a new QB, new OC, or a rebuilt line
- The total is inflated by last year's scoring reputation
- Weather is a factor

Second-half unders and team-total unders carry the same logic with less vig
exposure than the full game.

## 4. Variance is at its maximum

Less information on both sides — yours *and* the market's. Two consequences
that pull in opposite directions, and you have to hold both:

- **The market is softer.** Books have less to price on, so numbers are more
  beatable than in Week 10.
- **Your read is softer too.** You also have nothing. A soft line you cannot
  evaluate is not an edge.

**The resolution is sizing, not selection.** Week 1 is the week to bet *smaller*
than your usual number, not bigger. Cap at 1u regardless of what Kelly says —
Kelly assumes you know the probability, and in Week 1 nobody does.

Corollaries:
- **Favor underdogs taking points.** Maximum variance compresses outcomes toward
  the dog. Big Week 1 favorites are a poor bet.
- **Divisional games run tighter** than the model says. Familiarity plus
  maximum uncertainty.
- **Do not lay large numbers.** A 9.5-point Week 1 favorite is asking you to
  trust a projection built on nothing.

## 5. The news layer matters more, not less

With no performance data, **availability and personnel ARE the analysis**:

- Final 53 and practice-squad moves reshape depth charts right up to kickoff.
- **Week 1 inactives (90 minutes pre-kick) are the highest-value information
  of the week**, because nothing else is available to offset a surprise.
- Rookie starters, new-scheme veterans, and returning-from-injury players are
  all unpriced unknowns.
- Holdouts and late contract situations affect conditioning.

Run `skills/situational-context.md` in full. In Week 1 it is not the last
layer — it is close to the only layer.

## 6. How to write a Week 1 analysis

1. **State the data limitation up front.** One sentence: no current-season data
   exists, so this is built on continuity, the win-total prior, and news.
2. **Anchor hard on the market.** With no model of your own, the price is
   carrying nearly all the weight. That is the correct posture, not a failure.
3. **Name the specific reason you disagree**, or take no position. "The number
   looks off" is not a reason in Week 1 — it is a guess.
4. **Size at 1u maximum.** Say why.
5. **State what you could not retrieve.** In September that list is long.

## 7. Checklist

- [ ] Stated that no current-season data exists
- [ ] Returning production / continuity for both teams
- [ ] QB situation: returning starter, new veteran, or rookie?
- [ ] Offensive line continuity
- [ ] New head coach or coordinator on either side?
- [ ] Vegas season win total as the strength prior
- [ ] Total: does the offense-lags-defense logic apply here specifically?
- [ ] Weather for outdoor venues
- [ ] Inactives checked — or the play explicitly marked provisional
- [ ] Stake capped at 1u
