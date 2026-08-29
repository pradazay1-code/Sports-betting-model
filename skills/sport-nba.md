# NBA

High-scoring, high-possession, and driven almost entirely by **who is actually on
the floor.** The single biggest edge in NBA betting is being faster and more
accurate on availability than the market. Nothing in the box score competes with
knowing a starter is out before the line moves.

---

## 1. Model layer

### Net rating per 100, with on/off

Season-long team ratings are the starting point and the least useful part:

```
python3 -m lib.fetch_stats nba-team --season 2025-26
```

What actually predicts is the **injury-adjusted lineup projection** — net rating
for the specific group expected to play, not the team's season average. A team
with a +4.0 net rating that's missing its two best players is not a +4.0 team,
and the season number will never tell you that.

### Four factors, in order of weight

1. **eFG%** — roughly 40% of the explanation. Shooting is the game.
2. **Turnover rate** — ~25%.
3. **Offensive rebound rate** — ~20%.
4. **Free throw rate** — ~15%.

Applied both offensively and defensively. Opponent eFG% is largely a function of
shot *location* defense (rim and three-point prevention), not contest quality —
and three-point defense in particular is much noisier than people treat it.

### Player impact metrics

EPM, DARKO, RAPTOR-style. Use them for **lineup-level projection**, which is
their actual job: sum the impacts of who's playing, adjust for minutes, get a
team number for tonight.

Caveats you state out loud: these are noisy for low-minute players, they lag
role changes badly, and they can't see a player being used differently than
their history implies.

### Pace

Pace drives totals directly. Project the game's pace as roughly the average of
the two teams' paces, then adjust:
- Both teams top-10 pace → the total is already high, and the market knows.
- A big favorite → garbage time *lowers* the effective pace late.
- Playoff or high-stakes games run slower. Late-season tanking games run faster.

## 2. Spreads, totals, and key numbers

**NBA has no sharp key numbers.** This is the big structural difference from NFL.
Margins are spread across a wide, smooth distribution.

- 4, 5, and 6 matter marginally; 7 slightly (three-plus-foul sequences).
- A half point is worth ~8-10 cents, not the 25-30 you'd pay in NFL.
- **Consequence:** in NBA, take the better *price* over the better *number* far
  more often than you would in NFL. The reverse of the NFL instinct.
- Totals move on pace and rest more than on shooting talent.

## 3. Situational — this is where NBA edges live

- **Back-to-backs.** Worth roughly 2-3 points, and more for older teams and
  teams on the road leg. The second night of a road back-to-back is the classic
  fade spot, and it's priced — but not always fully.
- **Rest advantage.** 2+ days versus 0 days is the biggest schedule edge in the
  sport. Check both teams' rest, not just one.
- **Travel**, especially cross-country plus altitude (Denver, Utah). Compounds
  with back-to-backs badly.
- **Minutes restrictions.** A star "playing" on a 24-minute cap is close to a
  star sitting, and the line frequently doesn't reflect it. This is a genuine
  soft spot.
- **Load management.** Increasingly announced late and increasingly cynical.
  Watch the pattern by organization, not by player.
- **Schedule spots**: 4-in-6, the third game of a road trip, a trap game before
  a marquee opponent. Real but small, and mostly priced.
- **Blowout risk cuts both ways on totals.** A big favorite means starters sit
  in the fourth, which suppresses the total — a factor totals bettors routinely
  forget.

## 4. The real-time layer — this is the sport where it matters most

- **Starting lineups drop ~30 minutes before tip.** Lines move violently. If you
  bet before lineups, say the bet is provisional.
- Status flips inside the last hour more than any other sport.
- ```
  python3 -m lib.fetch_news injuries --sport nba
  ```
  is a floor, not a ceiling — the ESPN feed lags Shams and Woj by many minutes,
  and many minutes is the entire edge.
- **Who replaces the out player matters as much as who's out.** A star sitting
  with a competent backup is worth much less than a star sitting with nothing
  behind them.
- Second-unit minutes redistribution is where the props edge is. When a starter
  sits, the usage doesn't spread evenly — it concentrates.

## 5. Props

NBA props are the softest major market, because there are hundreds per night and
books can't sharpen them all.

- **Minutes projection is the whole game.** Get minutes right and the rest is
  rate stats. Get minutes wrong and nothing else matters.
- Usage rate for points props; pace for everything counting-stat.
- Rebounds correlate with pace *and* with the opponent's missed shots — a bad
  shooting opponent means more defensive rebounds available.
- Assists depend heavily on teammate shooting, which is the noisiest input in
  the sport. Be humble on assist props.
- PRA (points+rebounds+assists) combos are usually softer than the individual
  legs, because the book's model compounds its errors and its correlation
  handling is coarse.
- **Alternate lines are frequently mispriced** relative to the main line. Always
  check the alternates before taking the main.

## 6. Checklist

- [ ] Sharp price, movement, ticket % vs. handle %
- [ ] Confirmed lineups — or an explicit note that they aren't out yet
- [ ] Injury-adjusted lineup net rating, both sides
- [ ] Four factors matchup, especially eFG% and its drivers
- [ ] Pace projection → total
- [ ] Rest, back-to-back, travel, altitude
- [ ] Minutes restrictions and load-management risk
- [ ] Blowout risk if it's a total
- [ ] Line shop — price matters more than the half point here
