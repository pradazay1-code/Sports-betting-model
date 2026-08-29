# UFC / MMA

Two-way markets, no ties (draws are rare enough to treat as a small void risk),
and heavy favorite-longshot bias. That last part is structural: casual money
loves live dogs and loves finishing narratives, so the market on the favorite is
usually tighter than the market on the dog.

Devig with **power** — this is exactly the market it was built for.

---

## 1. Striking

```
python3 -m lib.fetch_stats ufc-fighter --name "Islam Makhachev"
```

| Stat | What it tells you |
|---|---|
| **SLpM** (significant strikes landed per minute) | Volume. Alone it's a weak signal. |
| **SApM** (absorbed per minute) | Defensive leakage. |
| **Differential (SLpM − SApM)** | Much better than either alone. |
| **Significant strike accuracy** | Efficiency, and a proxy for shot selection. |
| **Significant strike defense** | The most underrated striking stat. Fighters who don't get hit age better and last longer in fights. |

**Volume without accuracy is a losing profile** against anyone who can counter.
A high-SLpM fighter with 38% accuracy and poor defense is a highlight reel and a
bad bet.

## 2. Grappling

| Stat | What it tells you |
|---|---|
| **Takedown attempts per 15** | Intent — does this fighter even want to wrestle? |
| **Takedown accuracy** | Whether the intent works. |
| **Takedown defense** | The single most important grappling stat for a striker. A striker with 85% TDD against a one-dimensional wrestler is a completely different bet than one with 55%. |
| **Control time per round** | Where decisions are actually won. Judges reward control heavily. |
| **Submission attempt rate** | Finishing threat from the ground, and a decent proxy for scramble activity. |

**Wrestling controls where the fight happens, and that's usually the whole
matchup.** The fighter who dictates position dictates the fight. Style matchup
beats raw record almost every time.

## 3. Cardio and the round profile

- Output by round. Many fighters have a clear decline curve — round 1 output
  versus round 3 output is the number to look at, not a general impression.
- Fighters coming up from 15 to 25 minutes (first main event, first title fight)
  are a genuine and repeatedly profitable question mark.
- **Weight cut history.** A brutal cut shows up in round 3, not round 1.
- **Missed weight is a major red flag** — it signals a bad camp, a bad cut, or
  both, and the fighter who missed is frequently compromised. The market
  underreacts to this, especially on short notice.

## 4. Physical and situational

- **Reach and height** matter most for strikers who use them (long jab, kick
  distance). A 4-inch reach edge for someone who fights in the pocket is worth
  nothing.
- **Stance matchup.** Orthodox vs. southpaw is a real edge for whoever has more
  experience in that matchup, and southpaws get more reps against orthodox by
  definition.
- **Layoff.** Over 18 months off is a real, measurable performance hit. Ring rust
  is not a myth in MMA the way it is in some sports.
- **Age curve.** 35+ decline is real and it is sharp. It arrives suddenly rather
  than gradually — a fighter looks fine and then doesn't. When in doubt, fade
  the older fighter, especially one with a long war-heavy career.
- **Damage taken over a career** matters more than fights taken. Chin durability
  degrades with accumulated damage, not with age alone.
- **Short-notice replacements** are usually bad bets regardless of talent — no
  camp, a rushed cut, and no game plan for this specific opponent.

## 5. Fight IQ and the method markets

- Finish rate versus decision rate for each fighter, and *how* they finish.
- **Judging tendencies by commission are real.** Some commissions reward
  aggression and forward pressure; some reward control time and octagon
  control. Nevada and a small regional commission do not score the same fight
  the same way.
- A grinder who wins on control time is a bad bet on "doesn't go to decision"
  and a good bet on the ML.
- **Method-of-victory markets are multiway** — devig with multiplicative, not
  power.
- ITD (inside the distance) props are usually overpriced for exciting fighters
  and underpriced for high-level wrestlers who ground-and-pound.

## 6. The correlated parlay that actually works

**Fighter ML + fight doesn't go to decision** — but only when that fighter's
finish rate is genuinely high and the opponent's durability is genuinely
questionable. Verify both halves before you build it.

The trap: for many fights the correlation runs the *wrong* way. If the favorite
is a decision-machine wrestler, the underdog's realistic path to victory is an
early finish — so "favorite ML + no decision" is negatively correlated and
you're paying a premium for a worse bet.

## 7. Data reality check

UFCStats gives **career** rates. That's a real limitation, and you say so:

- Career rates blend a fighter's prime with their decline. A 38-year-old's
  career SApM flatters them badly.
- **Weight the last 3 fights heavily** and say when you're doing it.
- Sample sizes are tiny. A fighter with 6 UFC fights has maybe 40 minutes of
  octagon time. Treat every rate as noisy.
- Tapology and Sherdog for the full record including regional fights; UFCStats
  only has UFC bouts, which for a newcomer means almost nothing.

## 8. Checklist

- [ ] Sharp price (Pinnacle is the anchor in MMA), line movement since open
- [ ] Striking differential and defense, both fighters
- [ ] TDD for the striker, TD accuracy for the wrestler — who controls position?
- [ ] Cardio profile by round; 25-minute experience if it's a main event
- [ ] Weigh-in result — **did anyone miss?**
- [ ] Layoff, age, accumulated damage
- [ ] Short-notice replacement?
- [ ] Stance and reach, and whether this fighter actually uses them
- [ ] Commission and judging tendencies if it's likely to go the distance
- [ ] Method markets: devig multiway with multiplicative
