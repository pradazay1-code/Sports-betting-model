---
description: Build a parlay correctly — with the hold, the true probability, and the EV
argument-hint: <what you want built>
---

Parlay request: **$ARGUMENTS**

Read `skills/parlay-construction.md` before you build. Then build what was
asked for — don't substitute something else because you think the request is
bad. Price it honestly and let them decide.

## Steps

1. **Get devigged fair probabilities for every leg.** Raw implied probability
   is not acceptable here — it prices the vig as if it were true probability and
   makes every parlay look like a coin flip against a fair payout.
   ```
   .venv/bin/python -m lib.odds devig <price_a> <price_b>
   ```

2. **Determine correlation honestly.**
   - Independent legs → no uplift. Say the hold multiplies.
   - Genuinely correlated → estimate the uplift, and **label it `[READ]`.**
     You estimated it; a correlation coefficient with two decimal places you
     didn't measure is fake precision.
   - SGP → the book already priced the correlation. Say so. The only exception
     is when you can name the specific coarseness in the book's model.

3. **Price it.**
   ```
   .venv/bin/python -m lib.odds parlay <prices...> --fair <probs...> --correlation <uplift>
   .venv/bin/python -m lib.odds parlay <prices...> --fair <probs...> --rr 2
   ```

4. **Show all six required numbers:**
   - Each leg's fair probability
   - Combined true probability
   - Offered payout (decimal and American)
   - Implied probability of that payout
   - EV
   - The book's hold, **and the hold if the same legs were bet straight**

5. **Say the verdict in one sentence.** If it's -EV, say it once, plainly, and
   move on. No lecture.

6. **Offer the sound alternative** if one exists — a genuinely correlated
   structure, or a round robin where variance reduction is actually worth it.

## Longshot requests

Build it. Then label it: true probability in plain terms ("about 1 in 340"),
expected hold, EV, and **entertainment sizing ≤0.25u.** That's the whole
treatment. Don't refuse, don't water it down, don't moralize.
