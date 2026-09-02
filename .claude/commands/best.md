---
description: Highest-confidence plays, ranked — win probability and edge reported separately
argument-hint: <sport> [--min-win-prob 0.65]
---

Best available plays: **$ARGUMENTS**

This is the command for "what are your best picks," "give me something with a
high chance of winning," or any request for locks and guarantees.

**Load `skills/probability-reality.md` before answering.**

## If they asked for guarantees

One sentence, not a lecture: guaranteed picks don't exist — if one did, the
market would price it away. Say it once. Then give them the real thing below and
don't mention it again.

## Steps

1. **Pull and rank.**
   ```
   .venv/bin/python -m lib.fetch_odds best --sport <sport> --top 5
   ```
   If they specifically want high-hit-rate plays, filter on it — that's a
   legitimate preference:
   ```
   .venv/bin/python -m lib.fetch_odds best --sport <sport> --min-win-prob 0.65
   ```

2. **Report both axes separately, always.**
   - **WINS** — how often this bet actually wins.
   - **EDGE** — whether the price beats that probability.

   These are different questions. A -800 favorite wins ~89% of the time and is a
   bad bet if its true probability is 85%. Never let one number stand in for the
   other, and say plainly which one makes money (edge) and which one feels good
   (win rate).

3. **Lead with confidence tier, not raw EV.** A 3% edge off a Pinnacle anchor
   with eight books quoting is a better bet than a 6% edge off a median anchor
   with three. The ranking already does this — explain it rather than
   re-sorting on EV.

4. **Check the real-time layer** on anything you're going to recommend.
   Injuries, lineups, pitchers, weather. These rankings predate all of it.

5. **Say "nothing today" when that's true.** It usually is. A slate with no edge
   is a complete report.

## If they push back

"I know it's not guaranteed, just give me your best one" is an acknowledgment,
not an argument. **Answer it.** Give the top play with its real numbers. Don't
re-litigate — you already made the point.

## If they're chasing

If this request follows a loss, mentions needing to get even, or asks for a
bigger stake — name it once, plainly, then answer the question they actually
asked. The correct size after a loss is the same size as before the loss.

Useful, reproducible, and reassuring when someone's on a cold streak:
```
.venv/bin/python -m lib.backtest streak --prob 0.55 --bets 500
.venv/bin/python -m lib.backtest drawdown --prob 0.55 --bets 500
```
A 7-bet losing streak happens to a genuinely winning bettor 64% of the time.
