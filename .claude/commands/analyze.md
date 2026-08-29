---
description: Deep dive on one game or fight — market read through recommendation
argument-hint: <game or fight>
---

Deep dive: **$ARGUMENTS**

Read `CLAUDE.md`, then load the relevant sport file from `/skills/` before you
start. Don't work from memory when the checklist is on disk.

## Required output order

Follow this exactly. The market read comes first on purpose — you anchor on the
price, then look for a reason to disagree, not the other way around.

### MARKET READ
Sharp price (Pinnacle → Circa → BetOnline tier → median). Where it opened, where
it is now, which way it moved, and against what ticket percentage. What is the
market telling you?
```
.venv/bin/python -m lib.fetch_odds board --sport <sport>
.venv/bin/python -m lib.odds devig <price_a> <price_b>
```

### MODEL NUMBER
Your number and the method that produced it. Tag `[MODEL]`. If you don't have a
real model for this sport, say so plainly and lean harder on the market.

### KEY STATS
From the sport's skill file checklist. Every stat gets a source and a timestamp.
Tag `[FACT]`. Anything you couldn't retrieve gets stated as not retrieved — never
filled in.

### NEWS LAYER
Injuries, lineups, starting pitcher/goalie, weather, late-breaking anything.
Timestamped, sourced, and preferably under 24 hours old.

### DISCREPANCY
Where your number differs from the market — **and your honest read on why the
market might be right instead.** This section is not optional. If you can't
articulate the market's case, you don't understand the game well enough to bet it.

### RECOMMENDATION
Or "no bet," which is a complete answer.

If there is a bet:
- Side and the exact number
- **Fair price / offered price / EV%**
- Book, and the best available price across books
- Stake in units (¼ Kelly, capped at 2u)
- Confidence: low / medium / high, with the reason
- Devig method used, and the range if methods disagreed

### WHAT WOULD CHANGE MY MIND
Specific and falsifiable. "If the line moves to X." "If Player Y is downgraded
to out." "If the wind forecast drops under 10 mph." Not "if things change."

## Rules

- No fabricated stats, lines, injuries, or records. Ever.
- Under 2% EV is not a bet. Say so.
- Never over 2u.
- Key numbers: check what number you're actually getting, not just the price.
