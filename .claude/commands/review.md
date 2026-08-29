---
description: Weekly self-audit — what the model got wrong and what to adjust
---

Weekly audit. Be hard on the desk. The point is to find errors, not to defend
past calls.

## Steps

1. **Pull the week.**
   ```
   .venv/bin/python -m lib.db report --since <YYYY-MM-DD>
   .venv/bin/python -m lib.db calibration
   .venv/bin/python -m lib.db open
   .venv/bin/python -m lib.db tilt
   ```

2. **CLV first.** Which bets beat the close, which didn't, and is there a
   pattern? Pattern candidates worth checking:
   - By sport — is one sport dragging?
   - By market type — sides vs. totals vs. props?
   - By timing — are early-week bets beating the close and late ones not, or
     the reverse?
   - By book — is one book's price consistently the one that moves against you?

3. **Where was the model wrong, specifically?** Not "we lost the Chiefs game" —
   that's variance. Look for:
   - Bets where the *reasoning* was wrong even though it won
   - Bets where a fetch failed and the desk proceeded anyway (this is the
     serious one — flag it hard)
   - Bets where confidence was stated high and the process didn't support it
   - Places where the market moved against us immediately, which usually means
     we were working from a stale number

4. **Calibration.** Where is the desk systematically over- or under-confident?
   Name the bucket and the size of the gap. Ignore buckets under ~20 bets.

5. **Discipline audit.** Honestly:
   - Any bets under 2% EV?
   - Any over 2u?
   - Any chasing after a loss?
   - Any bets placed before the news layer was checked?
   - Any recommendation that cited a stat without a source?

6. **What to adjust.** Concrete and specific:
   - A number to change in a skill file
   - A source that's unreliable and should be dropped or double-checked
   - A market type to stop betting
   - A step in the process that keeps getting skipped

   If a skill file needs a correction, **edit the file** — that's the point of
   keeping the persona on disk. Say which file and what changed.

7. **What NOT to change.** Say this out loud. Most week-to-week results are
   noise, and the strongest instinct after a losing week is to change something
   that was working. Resist it, and name what you're deliberately leaving alone.

## Tone

This is a self-audit, not a performance review for the user. Criticize the
desk's process, not their luck.
