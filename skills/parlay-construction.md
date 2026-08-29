# Parlay construction

Parlays get built here, but built correctly. This file is the argument, in
order, and you make it plainly every time rather than apologizing for it.

---

## 1. Why most parlays are terrible

**A parlay of independent legs multiplies the book's hold.**

Four independent legs at -110:

```
$ python3 -m lib.odds parlay -110 -110 -110 -110
true prob   : 0.0625      (0.5^4, using devigged legs)
payout      : +1228.3     (decimal 13.2833)
implied     : 0.0753
book hold   : 16.97%
EV          : -16.97%
straight    : same legs bet straight hold 4.54%
             parlaying multiplies that by 3.7x
```

You handed the book **17%** instead of 4.5%. Nothing about the legs changed. You
just agreed to pay the vig four times and collect once.

This gets worse with leg count, and it's why books advertise parlays, push
parlays, and hand out parlay boosts. **Never present a random independent parlay
as a good bet.** If the user wants one anyway, build it and show them this table.

## 2. The only structurally sound parlay

**Correlated legs that the book prices as if they were independent.**

The book multiplies the legs. If the legs are positively correlated, the true
joint probability is *higher* than the product — and the book has priced the
product. That gap is the entire edge, and it's the only honest reason to parlay.

Examples that genuinely correlate:

| Structure | Why it correlates |
|---|---|
| Team total over + that team's ML | Teams that score win. Very strong, and books know it — usually only priceable across two separate bets, not in an SGP. |
| QB passing yards over + team total over | Same drive-level engine. |
| Team total under + opponent ML | Getting shut down and losing are the same event. |
| UFC fighter ML + fight doesn't go to decision | Only when that fighter's finish rate is genuinely high — otherwise the correlation runs the *wrong* way, because the underdog's path is often the early finish. |
| MLB F5 under + full-game under | Strong SP pair. F5 strips bullpen variance from half the bet. |
| NFL favorite ML + under | Ground-and-pound game scripts. Weaker than people think; verify with actual pace and pass-rate data. |
| Player anytime TD + team total over | Same red-zone dependency. |

**Negative correlations to never combine:** a team's ML with their opponent's
player props going over; a heavy favorite ML with a game over (favorites in
control run clock); an F5 over with a full-game under.

## 3. Same Game Parlays

**SGPs are priced *with* correlation already baked in.** The book's model has
already applied the uplift and taken it back as margin. That makes the standard
SGP bad value by construction — you are being charged for the correlation you
were hoping to exploit.

The exception, and it is a real one: **when the book's correlation model is
coarser than reality.** Books apply correlation at the category level. Reality
is finer. Look for:

- Props on a player whose usage is about to spike for a reason the model can't
  see (an injury to the guy ahead of them on the depth chart).
- Correlations that route through game *script* rather than through the box
  score — the model links QB yards to team total, but not "this team trails all
  game, so pass volume rises and the RB's rush attempts fall."
- Cross-market links the SGP builder doesn't cover at all (many builders won't
  correlate a player prop with an alternate spread).
- Weather. Wind suppresses passing and scoring together; SGP models are usually
  weather-blind.

**Flag these specifically, and say why the book's model is coarse here.** If you
can't articulate the specific coarseness, there isn't one, and the SGP is just
an SGP.

## 4. Longshots and lottery tickets

When the user asks for a longshot, **build it.** Don't lecture, don't refuse,
don't water it down into a 2-leg parlay they didn't ask for.

Label it honestly:
- The true probability, in plain terms ("about 1 in 340")
- The expected hold — the book's, not yours
- The EV, which will be badly negative
- **Entertainment sizing: ≤0.25u.** This is not a bet, it's a ticket.

That's the whole treatment. Say it once, clearly, then hand it over.

## 5. What every parlay presentation must show

Non-negotiable:

1. Each leg's **fair probability** (devigged — never raw implied)
2. The **combined true probability**, and whether correlation was applied
3. The **offered payout**, decimal and American
4. The payout's **implied probability**
5. The **EV**
6. The **book's hold**, and what the same legs hold bet straight

```
python3 -m lib.odds parlay -110 -110 +150 --fair 0.50 0.52 0.38 --correlation 0.12
```

If you applied a correlation uplift, **it is a `[READ]`, not a `[MODEL]`.** You
estimated it. Say the number out loud and say it's an estimate — a made-up
correlation coefficient with two decimal places is exactly the fake precision
this desk refuses to trade in.

## 6. Round robins

A round robin bets every N-leg combination of your legs separately.

**It reduces variance. It does not improve EV.** One dead leg no longer kills
everything, but if the underlying legs are -EV then every combination is -EV and
you've just bought more of them.

```
python3 -m lib.odds parlay -110 -110 -110 +120 --fair 0.5 0.5 0.5 0.44 --rr 2
```

Offer a round robin when:
- The legs are genuinely +EV individually, and
- The user wants parlay-shaped payouts anyway, and
- Variance reduction is worth the reduced ceiling.

Show the math on total risk (`C(n,k)` combos × stake) — people routinely
underestimate how much a by-2 round robin of 5 legs actually risks. That's 10
bets, not one.

## 7. The script

When asked for a parlay, in this order:

1. Build what was asked for.
2. Show the six required numbers.
3. State the hold, and the hold if bet straight instead.
4. If the legs are correlated, say where the correlation comes from and whether
   the book already priced it.
5. If it's -EV, say so once, in one sentence, without moralizing.
6. If a correlated alternative exists that's actually sound, offer it.

Build the ticket. Price it honestly. Let them decide.
