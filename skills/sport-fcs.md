# FCS and FBS-vs-FCS money games

FCS is the least efficiently priced football market that a retail bettor can
legally access. It is also the one where fabricating a number is easiest and
most costly, because the data genuinely is thin.

**Say so, every time. Confidence starts low here and has to earn its way up.**

```
python3 -m lib.fetch_cfb games --week 3 --division fcs
```

CFBD carries FCS, which is the difference between having numbers and guessing.
Most mainstream feeds do not.

---

## 1. The structural fact that explains everything: 63 vs 85

FBS programs carry **85 full scholarships.** FCS programs carry the equivalent
of **63**, and — critically — FCS scholarships can be **split into partial
awards**, so a roster may spread 63 equivalencies across 80-plus players on
partial aid.

Consequences that matter for betting:

- **Depth is dramatically thinner.** Injuries compound faster, and the
  fourth quarter of a physical game looks very different.
- **Talent variance within FCS is enormous** — far wider than within FBS.
- Two subdivisions of FCS give **no athletic scholarships at all**: the **Ivy
  League** and the **Pioneer Football League**. Treat those teams as a separate
  tier entirely. An Ivy team and North Dakota State are not the same sport.

## 2. The FCS talent tiers — do not treat the division as one pool

| Tier | Examples | Read |
|---|---|---|
| **Elite** | South Dakota State, Montana, Montana State, Sacramento State | Would beat the bottom third of FBS on a neutral field. Genuinely. |
| **Strong** | Missouri State, Villanova, UIW, Idaho, Furman | Competitive with bad FBS teams. |
| **Mid** | Most of the CAA, Big Sky, Southern | The broad middle. |
| **Low** | Much of the SWAC, MEAC, NEC | Large gap even inside FCS. |
| **Non-scholarship** | Ivy League, Pioneer League | A different sport. Do not compare their stats to scholarship FCS. |

**Verify conference membership before you classify a team.** Realignment moves
programs between subdivisions and stale tier lists produce confidently wrong
analysis. **North Dakota State moved up to FBS (Mountain West) for the 2026
season** — a game against them is a conference game, not a money game, and any
framework that still files them under "elite FCS" will misprice it.

**The single most common FCS handicapping error is treating the division as one
talent pool.** The gap between NDSU and a bottom-tier SWAC team is wider than
the gap between Alabama and a bad MAC team.

---

## 3. Money games — the highest-value spot in college football

An FCS program takes a road game against an FBS team for a guarantee, typically
**$300,000 to $1.5 million**, which can fund a meaningful share of its athletic
budget. These games are scheduled for money, not competition.

Spreads usually land **24 to 45 points**. Here is what the market gets wrong:

**The FBS team's goal is to win and get out healthy. The FCS team's goal is
frequently to survive and collect the check.** That asymmetry drives everything:

- **Big favorites empty the bench early.** Up 38-3 in the third, the FBS starters
  are in headsets. That kills the cover and kills the total.
- **Second-half unders and favorite team-total unders** are the structurally
  sound plays in these spots, far more often than the side.
- **Elite FCS programs are routinely overpriced against bad FBS teams.** NDSU,
  Montana, SDSU and their tier beat FBS opponents regularly. When the number
  treats them like a generic FCS body-bag opponent, that is the mispricing.
- **Watch the FBS team's next opponent.** A money game sandwiched before a
  rivalry or a conference opener is a textbook letdown/lookahead spot, and the
  starters come out even earlier.
- Late-season money games (rare) are worse for the FCS team — their depth is
  already shredded.

**Conversely:** an FCS team coming off a physical conference game, traveling by
bus, playing at altitude or in heat, against a motivated FBS team, is a spot to
lay the number, not take it.

---

## 4. What data actually exists — and what doesn't

**Exists and is usable:**
- Schedule, scores, records (CFBD, `division=fcs`)
- Basic team stats
- Some advanced stats, with **thinner coverage than FBS**
- Conference standings and playoff positioning

**Does not reliably exist:**
- Full SP+ coverage comparable to FBS
- Reliable recruiting composites (FCS recruits are largely unrated)
- Consistent injury reporting — there is no mandated report, and many programs
  publish nothing
- Snap counts, advanced usage, most player-level tracking

**Therefore:** if you cannot retrieve it, say you could not. An FCS analysis
with confident player-usage numbers is almost certainly fabricated, because
those numbers are not published anywhere.

---

## 5. Situational factors that matter MORE in FCS

- **Weather.** Smaller stadiums, northern geography, no domes to speak of, and
  November playoff football in Fargo or Missoula. Wind is decisive.
- **Travel.** FCS teams frequently travel by **bus**, not charter. A 9-hour bus
  ride is a real, physical disadvantage that has no FBS equivalent.
- **Home field is worth more** — roughly a **3-point baseline** versus 2.5 in
  FBS. Crowds sit closer, are more partisan, and visiting teams arrive worse.
- **Playoff positioning late in the year** creates enormous motivational splits.
  A team locked into a seed versus a team on the bubble is a live angle in
  November.
- **Roster attrition compounds.** By Week 9 a thin FCS roster with injuries is a
  materially worse team, and season-long ratings lag that badly.

---

## 6. Market structure

- **Lines are soft. Limits are tiny.** Both are true, and the second one is why
  the first one persists. A $500 max means the number never gets corrected.
- Many FCS games get **no line at all**, or only a spread with no total.
- **Line movement is near-meaningless** — with limits that low, a single
  recreational bet moves the number. Do not read sharp money into an FCS move.
- Anchoring is a problem: **there is often no sharp book pricing FCS.** When
  your anchor is a median of two soft books, say so and cut confidence hard.

---

## 7. How to write an FCS analysis

1. **Lead with the data limitation.** One sentence, up front.
2. **Establish the tier** for both teams. Scholarship or non-scholarship? Elite,
   mid, or low? This does more work than any stat you will cite.
3. Anchor on the market, acknowledging there may be no sharp price.
4. Apply the structural factors — depth, travel, weather, home field at 3.0.
5. **Cap the stake at 1u**, regardless of what Kelly says. Kelly assumes you
   know the probability; in FCS you do not.
6. State explicitly what you could not retrieve.

## 8. Checklist

- [ ] Stated the data limitation up front
- [ ] Both teams' tier identified (scholarship status, elite/mid/low)
- [ ] Any line at all? From how many books? Any sharp price? (usually no)
- [ ] Money game? If so — bench-emptying, second-half under, team totals
- [ ] Travel method and distance (bus vs charter is real)
- [ ] Weather, wind specifically
- [ ] Home field at the 3.0 FCS baseline, not 2.5
- [ ] QB status — often unreported; if unknown, say so
- [ ] Playoff/motivational context if late season
- [ ] Stake capped at 1u
