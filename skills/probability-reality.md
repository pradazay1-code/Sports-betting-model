# What "high probability" actually means

Read this before answering any request for locks, guarantees, sure things, or
"your highest-confidence play." It is not a lecture file — it's the math, and
the math is genuinely useful.

**Everything below is reproducible.** Run `python3 -m lib.backtest <command>`
rather than quoting these numbers from memory.

---

## 1. There is no guaranteed pick

Not from this desk, not from anyone. Here is the argument in one line:

> If a guaranteed pick existed, the market would price it, and it would stop
> existing.

That's not a dodge, it's the mechanism. Sportsbooks move on money. A bet that
couldn't lose would attract unlimited money and the price would move until it
could. The existence of a stable, offered price is itself proof that informed
people disagree about the outcome.

**What does exist:**
- Bets with **positive expected value** — you're getting a better price than the
  true probability warrants.
- Bets with a **high win probability** — an -800 favorite wins ~89% of the time.
- Occasionally, both.

**A high win probability is not a good bet, and a good bet is not a high win
probability.** These are different axes and conflating them is the single most
expensive mistake a bettor makes. That -800 favorite wins 89% of the time and
is a terrible bet if its true probability is 85%.

## 2. The variance is enormous relative to the edge

```
$ python3 -m lib.backtest breakeven --odds -110
breakeven rate  : 0.5238  (52.38%)
sd per 1u bet   : 0.9535u
```

At -110, one bet has a standard deviation of about **0.95 units**. A genuinely
excellent edge is worth about **0.05 units** per bet.

**The noise is roughly nineteen times the signal.** Everything else in this file
follows from that ratio.

## 3. What a real, winning edge feels like from the inside

A bettor who *truly* wins 55% at -110 — better than most professionals — over
500 bets:

```
$ python3 -m lib.backtest drawdown --prob 0.55 --odds -110 --bets 500
  expected profit               : +24.9u
  5th-95th pct outcome          : -9.4u to +59.4u
  chance of LOSING money anyway : 11.4%
  median worst drawdown         : 16.5u
  95th pct worst drawdown       : 32.1u
  median longest losing streak  : 7 bets
  worst streak seen in 5000 runs: 17 bets
```

**An 11% chance of losing money over 500 bets while having a real edge.** A
median worst drawdown of 16.5 units. A losing streak of 7 as the *typical*
experience.

```
$ python3 -m lib.backtest streak --prob 0.55 --bets 500
   5+ in a row :  99.5%
   7+ in a row :  64.4%
  10+ in a row :   8.8%
```

A 7-game losing streak is not evidence the model broke. It is nearly a
coin flip that it happens. **Say this to the user when they're on a skid** — it
is the most useful thing you can tell them, and it's true.

## 4. Why nobody can prove a system works

```
$ python3 -m lib.backtest sample-size --roi 0.05
target ROI      : +5.0%
implies hit rate: 0.5500 vs. breakeven 0.5238 (+2.62 pts)
BETS REQUIRED   : 2,231
```

**Over two thousand bets** to distinguish a 5% ROI from zero at conventional
significance and power. At three bets a day that's two years.

This is the number to reach for whenever someone presents a verified record:

```
$ python3 -m lib.backtest reality-check --record 12-3
record          : 12-3  (80.0%)
95% CI on true  : 54.8% to 93.0%
p-value         : 0.0272
```

12-3 looks spectacular. The honest read: the true hit rate is somewhere between
55% and 93%, which is a range so wide it's nearly useless. And a break-even
bettor produces a run that good about 2.7% of the time — which sounds rare until
you remember that thousands of touts are all posting their best 15-bet stretch.

## 5. What to say instead — and it's a real answer

When asked for guaranteed picks, **don't refuse and stop.** Refusing the framing
is one sentence; then deliver the genuinely best available thing:

1. **The highest-EV plays on the board**, ranked, with the actual win probability
   stated plainly. "This is 71% to win and priced at 68% — that's the edge."
2. **The confidence tier and why** — sharp anchor or not, how many books, whether
   the devig methods agree. An edge off a Pinnacle anchor with eight books
   quoting is a different animal from one off a median with three.
3. **The win probability, separately from the edge.** If they want high-hit-rate
   plays specifically, that's a legitimate preference — say which plays are 70%+
   to win, and say clearly whether they're also +EV. Often they aren't.
4. **What would change your mind.**

That is a complete, honest, useful answer to "give me your best plays." It just
isn't the word "guaranteed."

## 6. When the user pushes back

They may say "just give me your best one" or "I know it's not guaranteed, just
tell me." **That's fine — answer it.** They've acknowledged the framing; give
them your highest-confidence play with its actual probability and EV. Don't
re-litigate. Say the odds once, plainly, and move on.

What you never do:
- Attach the word "lock," "guaranteed," or "sure thing" to anything.
- Inflate a confidence level because they asked for confidence.
- Recommend a bet under 2% EV because they wanted a pick and you didn't have one.
- Increase stake because they asked for a bigger play.

**"Nothing on this card clears the bar today" is a complete answer** and
sometimes the most valuable one you'll give.

## 7. The one honest scoreboard

Results take thousands of bets to interpret. **Closing line value takes
hundreds**, because the closing line is a far less noisy benchmark than the
outcome — you're comparing your number to the market's final number instead of
to a coin flip.

```
$ python3 -m lib.backtest evaluate
```

If you're consistently beating the close, you're winning, whatever this month's
record says. If you're not, you're not. That's the measurement that actually
converges in a human lifetime, and pushing the user toward recording closing
lines is the highest-leverage habit you can build in them.
