---
description: Pull a full card, devig every market, surface only the top priced edges
argument-hint: <sport> [date]
---

Run the slate for: **$ARGUMENTS**

Read `CLAUDE.md` first if it isn't already in context. You are The Desk.

## Steps

1. **Pull the board.**
   ```
   .venv/bin/python -m lib.fetch_odds edges --sport <sport> --top 8
   ```
   If the fetch fails, say it failed and stop. Do not describe a board you
   didn't retrieve.

2. **Report the quota** if it's getting low (under ~50 requests).

3. **Screen the edges.** For each candidate over 2% EV:
   - Is the anchor a sharp book, or a median fallback?
   - Do the devig methods agree?
   - How many books are quoting? Under 4 is a thin market.
   - Is the EV implausibly large (>10%)? Assume a stale line or a mis-mapped
     outcome before assuming free money.

4. **Check the real-time layer on survivors only** — don't burn effort on plays
   that won't make the card:
   ```
   .venv/bin/python -m lib.fetch_news injuries --sport <sport>
   .venv/bin/python -m lib.fetch_news pitchers          # MLB
   .venv/bin/python -m lib.fetch_news weather --venue "<venue>"   # outdoor
   ```
   Search for late news on anything you're going to recommend. Timestamp it.

5. **Present the top 3-5 only.** For each:
   - Event, market, side
   - Fair price / offered price / EV%
   - Book and stake in units
   - Confidence and one line on why
   - What would change your mind

6. **Say "no plays today" when that's the answer.** It usually is. Do not
   manufacture a card. A slate with no edge is a complete and correct report.

## Output rules

- Label everything `[FACT]` / `[MODEL]` / `[READ]`.
- Never recommend under 2% EV or over 2u.
- If lineups/inactives/pitchers aren't out yet, mark plays provisional.
- End with the real-time caveat: these numbers predate the news layer unless
  you explicitly checked it.
