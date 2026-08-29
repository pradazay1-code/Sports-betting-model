---
description: Log a bet to bets.db
argument-hint: <bet details>
---

Log: **$ARGUMENTS**

An untracked bet is an unlearned lesson.

## Steps

1. **Parse what you were given.** Required: sport, event, market, side, price,
   book, stake. Ask only for what's genuinely missing — don't interrogate.

2. **Include the fair probability** if this was a bet you analyzed. Without it
   the bet can't feed the calibration check, which is the most valuable thing
   the log produces. If you devigged this bet earlier in the conversation, use
   that number.

3. **Write it.**
   ```
   .venv/bin/python -m lib.db log \
     --sport NFL --event "KC @ BUF" --market spread --side "BUF -2.5" \
     --price -108 --book draftkings --stake 1.0 \
     --fair-prob 0.545 --devig-method power --confidence medium \
     --notes "reverse line movement, Pinnacle anchor"
   ```

4. **Confirm** the row and the EV it computed.

5. **Remind about the closing line.** CLV is the scoreboard and it can only be
   recorded after the fact:
   ```
   .venv/bin/python -m lib.db close --id <id> --closing <american>
   ```

## Grading

```
.venv/bin/python -m lib.db grade --id <id> --result win|loss|push|void
.venv/bin/python -m lib.db open      # what's still ungraded
```

## If the stake looks wrong

If the user logs a bet well above what Kelly supports, or well above 2u, note it
in one sentence. Don't refuse — it's already placed, and the log's job is to
record what happened, not to editorialize. But record the discrepancy, because
that pattern is what `/review` is going to need.
