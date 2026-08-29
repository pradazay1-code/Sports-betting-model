# MLB

The longest season, the most games, and the smallest per-game edges. Baseball
rewards volume and punishes overconfidence: a great MLB bettor is right 54% of
the time on moneylines and grinds. Anyone quoting you a "lock" in a sport where
the best team loses 60+ games a year is selling something.

---

## 1. Market structure — start here

**F5 (first five innings) lines strip bullpen variance.** This is the most useful
structural feature in baseball betting.

If your opinion is about the starting pitcher — and most good MLB opinions are —
bet F5. The full game drags in six relievers you have no read on, managed by
decisions that haven't been made yet. F5 isolates the thing you actually have an
edge on.

**Run line (±1.5) is not derivable from the moneyline.** The correlation between
"team wins" and "team wins by exactly one" is not what naive conversion implies —
roughly 30% of MLB games are decided by one run, and that concentration breaks
any formula-based conversion. **Quote the actual run line market.** Never derive
it.

Other structure:
- Totals commonly come with a half-run and a price (8.5 at -115). Compare both
  the number and the juice across books; the juice varies more than in other
  sports.
- First-inning and first-3-innings markets exist and are softer, but limits are
  low enough that they're rarely worth the effort.
- MLB has the lowest hold of any major US sport at the sharp books. That's a
  feature — it means the closing line is very good, and beating it is hard.

## 2. Pitching

```
python3 -m lib.fetch_stats mlb-pitcher --name "Tarik Skubal"
```

### The stats that predict

| Stat | Read |
|---|---|
| **CSW%** (called + swinging strike rate) | The best single pitcher stat. Above ~30% is strong, below ~27% is weak. Stabilizes fast. |
| **xFIP / SIERA** | ERA estimators that strip defense and HR/FB luck. |
| **Barrel rate allowed** | Contact quality. The thing ERA hides. |
| **Hard-hit rate allowed** | Above ~40% means the results are living on defense and will regress. |
| **Whiff rate** | Swings and misses per swing. Underlying skill for the K prop. |
| **Velocity trend** | A 1.5 mph drop over three starts is an injury tell before it's a news item. |

### The ERA-to-xFIP gap is the regression flag

A starter with a 2.40 ERA and a 4.10 xFIP is not a 2.40 pitcher. The market
usually knows this before the box-score public does, which means the *value* is
often on the "worse" pitcher whose ERA is ugly and whose peripherals aren't.

### Platoon splits

Real and large, especially for:
- Left-handed pitchers against right-heavy lineups
- Sidearm and submarine relievers (extreme splits)
- Rookies seeing a lineup the second and third time

Third time through the order is a genuine, well-documented penalty. A manager
with a quick hook changes the F5-vs-full-game calculus entirely.

## 3. Hitting

- **xwOBA over wOBA.** Expected outcomes based on exit velocity and launch
  angle, stripping out defense and park. wOBA tells you what happened; xwOBA
  tells you what should have.
- **Barrel rate** and **hard-hit rate** for power projection.
- **Lineup order matters** for props — batting second versus seventh is roughly
  0.7 plate appearances per game, which is a large fraction of any prop edge.
- Small-sample hot streaks are noise. A hitter "seeing it well" over 40 at-bats
  is telling you almost nothing.
- **Team-level:** wRC+ against the handedness of tonight's starter, not overall.

## 4. Park and weather — the multiplier

```
python3 -m lib.fetch_stats mlb-parks
python3 -m lib.fetch_news weather --venue "Wrigley Field" --at 2026-08-30T19:20
```

**Wind vector matters more than temperature**, and at some parks it matters more
than the pitching matchup.

- **Wrigley** is the extreme case. 15 mph blowing out is a different ballpark
  from 15 mph blowing in — swing the total 1.5 runs or more.
- **Coors** is Coors regardless of weather. But note the *second-order* effect:
  breaking balls break less at altitude, which hurts pitchers who rely on them
  beyond what the run environment alone implies.
- **Oracle Park** and **Petco** suppress right-handed power specifically.
- **Fenway's** Green Monster turns fly-ball outs into doubles for right-handed
  pull hitters.
- Retractable roofs: **confirm whether the roof is open.** The books know. If
  you don't, you're guessing, and `lib/fetch_news.py` will warn you.
- Temperature has a real but modest effect (~1% carry per 10°F). Wind dwarfs it.

## 5. Umpires

Home plate umpire strike zone tendencies are real, measurable, and mostly
unpriced by the public:

- Strike zone size varies meaningfully between umpires.
- A large-zone umpire favors pitchers and the under; a small zone the reverse.
- Effect is worth roughly 0.2-0.4 runs on the total at the extremes. Small, but
  it's free — the information is public at Umpire Scorecards and almost nobody
  uses it.
- Check it last, alongside weather.

## 6. Bullpens

- **Usage over the prior 3 days** is the key input. A bullpen that threw 5
  innings yesterday is a different bullpen tonight.
- Closer availability changes late-inning run expectancy materially.
- Bullpen quality is much noisier year-over-year than rotation quality. Be
  skeptical of a bullpen ranking based on 40 innings.
- **This is the entire argument for F5.** If you can't model tonight's bullpen —
  and usually you can't — don't bet a market that depends on it.

## 7. The real-time layer

- **Confirmed vs. probable starting pitcher.** "Probable" is doing real work in
  that name, and a late scratch voids some bets and not others depending on the
  book. Know your book's rule.
- ```
  python3 -m lib.fetch_news pitchers
  ```
- Lineups post 2-4 hours before first pitch. A star sitting is worth real money
  in a low-scoring sport.
- Weather within a few hours of first pitch — forecasts move.
- Rain delay risk, and how your book handles suspended games.

## 8. Checklist

- [ ] Sharp price on both the full game and F5
- [ ] Confirmed starters (not just probable)
- [ ] CSW%, xFIP/SIERA, barrel and hard-hit allowed, both starters
- [ ] ERA vs. xFIP gap — who's due to regress, which way?
- [ ] Platoon matchup vs. tonight's lineups
- [ ] Park factor
- [ ] **Wind speed and direction relative to the field**
- [ ] Umpire assignment
- [ ] Bullpen usage, last 3 days, both sides
- [ ] Is my opinion about the starter? Then bet F5, not the full game.
