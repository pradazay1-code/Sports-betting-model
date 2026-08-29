---
description: Closing line value, ROI, expected vs. realized, and a calibration check
---

## Steps

1. **Pull the numbers.**
   ```
   .venv/bin/python -m lib.db report
   .venv/bin/python -m lib.db calibration
   .venv/bin/python -m lib.db tilt
   ```

2. **Lead with CLV, not with the record.** Results are the thing the user wants
   to see and the thing that means least over a short sample. Say that once,
   then give them both.

   - **Beating the close consistently = winning**, whatever this week's record
     says.
   - **Losing to the close consistently = losing**, whatever this week's record
     says.
   - A losing record with positive CLV is a variance problem, and variance
     resolves. A winning record with negative CLV is a luck problem, and luck
     doesn't.

3. **Report expected vs. realized.** The gap is variance. Quantify it rather
   than narrating it — "you're 3.2u below expectation over 41 bets" is useful;
   "you've been unlucky" is not.

4. **Calibration check.** When the desk said 60%, did it hit ~60%?
   - **Buckets under ~20 bets tell you nothing.** Say so explicitly rather than
     reading tea leaves in a 4-bet bucket.
   - Systematic overconfidence (predicted consistently above actual across
     several well-populated buckets) means the devig or the model is off, and
     it's worth naming which.

5. **Flag missing closing lines.** Bets without a recorded close can't be
   scored. If a lot are missing, the scoreboard is broken and fixing that is
   more valuable than any analysis in this report.

6. **Tilt check.** If `db tilt` flags something, say it plainly and once. These
   are prompts to look, not a verdict — ask before you accuse.

## Tone

Blunt and specific. If the sample is too small to conclude anything, say that
first and don't dress up noise as a finding. Most CLV reports on fewer than 50
bets should end with "this is too small to tell us much yet."
