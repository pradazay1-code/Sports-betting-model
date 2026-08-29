# BKFC (Bare Knuckle Fighting Championship)

**Start here: the data is thin, and you say so out loud on every BKFC analysis.**

There is no UFCStats for bare knuckle. No strike accuracy tables, no control
time logs, no reliable round-by-round anything. Anyone presenting a precise BKFC
model is presenting a fabrication, and that includes you if you're not careful.

Confidence on any BKFC play starts at **low** and has to earn its way up.

---

## 1. What actually predicts, in order

### 1. Cut susceptibility — the single most predictive factor, and underpriced

This is the thing to lead with. Bare knuckle fights are stopped on cuts far more
often than gloved fights, and cut susceptibility is:

- **Highly individual** — brow structure, scar tissue, skin type
- **Highly persistent** — a fighter who cuts, keeps cutting; scar tissue never
  gets stronger
- **Systematically underpriced** — the market prices striking and record, and
  under-prices "this guy opens up in round 2 every time"

A fighter with heavy scar tissue around the eyes against a sharp puncher is in
much more trouble than any striking metric suggests. Check fight photos and
recent-fight reports specifically for this. If a fighter has been stopped on
cuts before, that is the most important thing you know about them.

### 2. Chin durability

Bare fists mean less padding and more knockdowns, but also — counterintuitively
— fewer concussive knockouts than gloved boxing, because a bare fist transfers
differently and breaks more easily. What matters is **whether this fighter has
been dropped**, and how recently. Prior KO losses compound fast in this sport.

### 3. Hand speed and boxing pedigree

Bare knuckle rewards **short, sharp, accurate punching**. It punishes wide,
looping power shots — they break hands.

- **Boxing pedigree beats MMA-convert**, consistently. This is the most reliable
  style read in the sport.
- MMA fighters coming over struggle with the lack of a jab-behind-a-glove, the
  clinch rules, and the pace.
- Hand injuries are common and change fights mid-bout. A fighter who has broken
  hands before is a live risk to break them again.

### 4. Cardio in 2-minute rounds

BKFC rounds are **2 minutes**, not 3 or 5. That changes everything:

- It rewards explosive starters over grinders.
- Cardio matters less than in MMA, but the pace is higher.
- Fighters used to 5-minute MMA rounds pace wrong in their first BKFC fight —
  they wait, and the round is over.

### 5. Prior BKFC experience vs. debut

**A BKFC debut is a genuine unknown**, even for an accomplished fighter. The
adjustment to no gloves is real: hand placement, defensive shell, and the
willingness to throw all change. Fade or downgrade debutants against experienced
bare-knuckle fighters, especially decorated MMA fighters who "should" win.

## 2. Structural facts about the sport

- **Finishes come early and often.** The distribution is heavily front-loaded.
  Round 1 and 2 finishes dominate.
- **Unders on round totals are usually the wrong side** — the market knows the
  finish rate. Check the actual number before assuming.
- Doctor stoppages on cuts are a large share of finishes. This is why cut
  susceptibility leads the analysis.
- The talent pool is uneven. Records include a lot of regional MMA and amateur
  boxing that means very little.

## 3. Data sources — use them, cite them

- **BKFC official site** — results, records, event pages
- **Tapology** — the best available fight history, including regional bouts
- **BKFC results archives** — for prior-fight method and round
- **YouTube / press coverage** — for the film read on cuts, hand speed, and chin

**Every number you cite must come from a source you actually fetched.** Film
reads are `[READ]`, never `[FACT]`, and must be labeled that way.

## 4. How to write a BKFC analysis

1. **Lead with the data limitation.** One sentence, up front, no hedging around
   it: the data here is thin and this is a low-confidence sport.
2. Anchor on the market. In a sport where you have this little, the price is
   carrying more of the weight than usual — respect it.
3. Cut susceptibility first, then chin, then style (boxing vs. MMA), then
   experience.
4. Size down. A BKFC play is a smaller play than the equivalent EV in a sport
   you can actually model. **Cap at 1u regardless of what Kelly says** — Kelly
   assumes you know `p`, and here you don't.
5. Say explicitly what you couldn't find.

## 5. Checklist

- [ ] Stated the data limitation up front
- [ ] Sharp price if one exists — BKFC often has only soft books, which is
      itself a reason to lower confidence
- [ ] Cut history, both fighters, from a named source
- [ ] Knockdown / KO loss history
- [ ] Boxing pedigree vs. MMA convert
- [ ] BKFC experience vs. debut
- [ ] Hand injury history
- [ ] Round total: does the market already price the high finish rate?
- [ ] Confidence: low unless something exceptional justifies otherwise
- [ ] Stake capped at 1u
