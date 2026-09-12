---
description: College football slate or single game — FBS and FCS, with the full situational layer
argument-hint: <team/matchup/week> [--fcs]
---

College football: **$ARGUMENTS**

**Load these before you start:**
- `skills/sport-cfb.md` — FBS handicapping
- `skills/sport-fcs.md` — if any FCS team or money game is involved
- `skills/situational-context.md` — **always**, before any recommendation

## 1. Market read first

```
.venv/bin/python -m lib.fetch_cfb lines --week <N> --team "<team>"
```
Opener vs current, direction of movement, how many books. Remember: **CFB
markets move on less money than NFL markets**, so weight limit changes over
move size, and treat a single move as a noisier signal than you would in the NFL.

If CFBD isn't keyed, say so — don't substitute a guess.

## 2. Build the first-pass number

```
.venv/bin/python -m lib.fetch_cfb spread --home <home> --away <away>
.venv/bin/python -m lib.fetch_cfb sp --team <team>
.venv/bin/python -m lib.fetch_cfb advanced --team <team>    # garbage time excluded
```

Then ask the real question: **success rate or explosiveness?** A team living on
big plays regresses hard and is far more volatile week to week. If the market
has priced last week's blowup, that's the fade.

Cross-check with talent composite on large spreads and returning production on
any team whose record looks disconnected from its roster.

## 3. Home field — never a flat number

```
.venv/bin/python -m lib.venues edge --home <home> --away <away>
```

Report crowd and altitude **separately**. Altitude is a fourth-quarter effect —
weight it toward second-half and live markets.

## 4. Situational layer — this is where CFB is won

Work `skills/situational-context.md` in order: availability → who's actually
taking snaps → coaching/coordinator → motivation → weather → market confirmation.

**QB status is the single highest-value item in this sport.** A starter ruling
out is worth 4-7 points with a good backup and 10-14 with a freshman. There is
no mandated injury report — beat writers are the source.

```
.venv/bin/python -m lib.fetch_news weather --venue "<stadium>" --at <ISO hour>
```

## 5. FCS and money games

If an FCS team is involved, **lead with the data limitation**, establish both
teams' tier (scholarship status, elite/mid/low), and cap the stake at 1u.

For FBS-vs-FCS money games, the sound plays are usually **second-half unders and
favorite team-total unders**, not the side — big favorites empty the bench.

## 6. Output

Standard format from CLAUDE.md §5. Every recommendation carries fair price,
offered price, EV%, stake, confidence, and what would change your mind.

Ask before you finish: **is this news already in the price?** If a QB was ruled
out Tuesday and the line moved six points Tuesday, there's nothing left.
