---
description: Player prop analysis with usage context and book-by-book shopping
argument-hint: <player or game>
---

Props: **$ARGUMENTS**

Props are the softest major market — books can't sharpen hundreds of lines a
night. They're also where fabrication is most tempting, because the stats are
granular and plausible-sounding. Retrieve everything or say you couldn't.

## Steps

1. **Find the event id, then pull the props.** Props use the per-event endpoint
   and **cost quota per market group** — don't sweep a whole slate.
   ```
   .venv/bin/python -m lib.fetch_odds quota
   ```
   Then use `lib.fetch_odds.get_events()` and `get_event_odds()` for the
   specific event and market you need.

2. **Usage context first — this is the whole analysis.**
   - **NFL**: snap share, target share, route participation, red zone usage.
     Volume before efficiency, always.
   - **NBA**: **projected minutes** above everything else. Then usage rate, then
     pace. Get minutes wrong and nothing else matters.
   - **MLB**: lineup slot (batting 2nd vs. 7th is ~0.7 PA/game), platoon
     matchup, park, and the opposing starter's handedness.
   - **NHL**: line assignment, power play unit, ice time.

3. **Project the number**, then compare to the line. Tag the projection
   `[MODEL]` and the inputs `[FACT]`.

4. **Devig the prop's two-way market** (over/under) with power. Props carry much
   higher hold than sides — 6-8% is normal, and some are worse. That hold eats
   most apparent edges, which is exactly why devigging matters more here.

5. **Shop every book.** Prop lines vary more across books than any other market.
   A half-yard or half-point difference is common and material. **Check
   alternate lines too** — they're frequently mispriced relative to the main.

6. **Check the real-time layer.** A prop on a player whose usage is about to
   change is a different bet entirely. Injuries to teammates *ahead* of your
   player are the most valuable and least priced information in props.

## Output per prop

- Player, market, line
- Fair price / offered price / EV%
- Best book, and the spread of prices across books
- Usage context in one or two lines
- Stake and confidence
- What would change your mind

**If you couldn't retrieve the usage data, say so and don't bet the prop.** A
prop projection without usage data is a guess with a decimal point on it.
