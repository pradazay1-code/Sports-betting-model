# DET @ BUF — graded. Bills 41, Lions 31.

**Record 4-3. Net -1.28u on 7.00u risked. ROI -18.3%.**

Winning more bets than I lost and still losing money is what happens when the
biggest stake is on the worst read. That is the whole story of this card.

| Bet | Stake | Price | Result | P/L |
|---|---|---|---|---|
| **Under 54.5** | 2.00u | -110 | **LOSS** — total 72 | **-2.000** |
| BUF -4.5 | 0.50u | -115 | WIN — won by 10 | +0.435 |
| **Goff under 270.5** | 1.00u | -114 | **LOSS** — 327 yards | **-1.000** |
| Kincaid over 49.5 | 1.00u | -110 | WIN — 7 rec, 95 yds, TD | +0.909 |
| LaPorta under 4.5 rec | 1.00u | -110 | WIN — 4 rec on 5 tgt | +0.909 |
| Shakir 3+ rec | 0.75u | -350 | WIN — exactly 3 on 6 tgt | +0.214 |
| **Allen under 1.5 pass TD** | 0.75u | +134 | **LOSS** — 3 pass TDs | **-0.750** |
| DET ML + up-7 promo | token | — | **LOSS** — trailed 21-0, never led | — |

## Projection vs. result

| | My model | Market | **Actual** | My error |
|---|---|---|---|---|
| Buffalo | 28.75 | 29.00 | **41** | **-12.3** |
| Detroit | 22.06 | 24.50 | **31** | **-8.9** |
| **Total** | **50.81** | **54.50** | **72** | **-21.2** |
| Spread | BUF -6.69 | BUF -4.5 | **BUF -10** | **+3.3** |

**The side was the best call on the card and the total was a catastrophe.** My
fair spread of -6.69 was closer to the realized -10 than the market's -4.5, and
the reverse-line-movement read (74% of tickets on Detroit, line moving to
Buffalo) was correct. I sized it at 0.5u. I sized the total at 2.0u.

## Root causes, in order of damage

**1. I discarded the better projection method on aesthetic grounds.**
I ran the multiplicative form, got 61, called it "absurd," and used the additive
form's 50.8 instead. **Actual: 72.** The multiplicative form was 11 off. The one
I chose was 21 off. My stated reason for rejecting it — "it compounds when both
offenses are above average and both defenses below" — described the game exactly.
That compounding was the signal, not an artifact.

**2. I identified the fatal risk, wrote it down, and sized as if I hadn't.**
Section 9 said pace was "the under's kill switch" and "the single largest
unmodeled risk in the report," and that neutral pace was UNAVAILABLE. The +10%
pace row projected a 56.0 total and flipped the bet. I published that and then
put 2u on it anyway.

**3. Both injury adjustments pushed the total down. Both were wrong.**
Detroit was missing three of five offensive line starters and Goff threw for
**327 yards and 4 touchdowns**. The "OL injuries are systematically underpriced"
heuristic did not hold, and neither did the -0.75 short-week penalty in a
72-point game.

**4. I shrank the Detroit-secondary adjustment for the wrong reason.**
I cut it from 3.5 to 1.5 because "the market has absorbed it." Buffalo put up
**27 points and 299 yards in the first half**. The market's absorption belongs in
the market price, not in my prior — shrinking my own number for that reason
double-counts in the wrong direction.

**5. Standing down on Gibbs was wrong, and for an instructive reason.**
Final model number: 21 carries x 5.0 = **105 rushing yards. Actual: 113.** That
was the most accurate projection I made all night. I abandoned it because the
read had reversed twice and the reversals made me uncomfortable. A read that
moved twice as facts arrived is a read that was *updating correctly*. The number
built on the fullest information set is the number to use.

## What worked, and why

- **Kincaid over 49.5** — best call on the card. The thesis (line priced off an
  injured 2025 season, Detroit missing both starting safeties) was exactly right.
  He got 7 targets against my 6-target assumption and went for 95 and a score.
- **LaPorta under 4.5 receptions** — 4 on 5 targets. Buffalo's league-low TE
  defense held. Right call, right reason.
- **Killing the whole anytime-TD board** at -9% to -16%, validated by Kalshi's
  68 cents on Gibbs against my 67.1% devig.
- **Killing St. Brown over 7.5** once his real 68% catch rate came back.
- **Shakir 3+ receptions won on exactly 3 catches from 6 targets** — a 50% catch
  rate against his 75.8% baseline. The bet won; the process nearly failed. Do not
  file this one as a good read.

## Rules changed as a result

Written into CLAUDE.md sections 3.2a and 3.4b:

1. Run both projection forms. Quote the range. The spread between them **is** the
   uncertainty. Never discard one because its answer looks wrong.
2. Method convergence is the confidence signal. Forms disagreeing by more than
   ~10 points on a total means there is no playable number, whatever the market says.
3. A sensitivity scenario that kills the bet, on an input marked UNAVAILABLE,
   **caps the stake at 1u.** No exceptions for a number you like.
4. Never shrink an adjustment because "the market already has it." That is
   reasoning about the price inside the model.
5. A read that has reversed is not a read that is wrong.
