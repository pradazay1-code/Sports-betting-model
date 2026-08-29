# Book behavior

How each sportsbook actually operates. This determines where you anchor, where
you bet, and how long you get to keep betting.

**The core distinction, which governs everything else:**

> **Sharp books** want your action and price accordingly. They move on *money*.
> **Soft books** want recreational action and price to the public. They move on
> *tickets*.
>
> You **estimate from** sharp books. You **bet into** soft books. Never confuse
> the two roles.

---

## 1. Sharp books — the anchor tier

### Pinnacle
The reference price for the entire industry.

- Lowest margin in the business — often 2-3% on mainstream two-way markets vs.
  4.5-5% at soft books.
- **Welcomes sharp action.** Their model is high volume, low margin, and they'd
  rather take your bet and move than ban you.
- Moves on money, not tickets. A Pinnacle line move means someone bet real size.
- High limits, and limits that *rise* into game time as the number sharpens.
- Not available in most of the US. Get the price via The Odds API's `eu` region.

**This is your first-choice anchor, always.**

### Circa
US-facing, sharp posture, the closest domestic equivalent to Pinnacle.

- Takes big action and doesn't restrict winners. This is genuinely rare.
- Posts NFL and NBA early, and those openers are among the sharpest numbers
  available anywhere.
- Especially strong on NFL sides and totals.
- Nevada-centric.

### BetOnline / Bookmaker / Heritage / LowVig
Offshore reduced-juice tier.

- Sharper than the US soft books, softer than Pinnacle.
- Reduced juice (-105 rather than -110) on many markets, which is a real edge
  before you handicap anything.
- Post early. Their openers are worth watching for line origination.
- Third in the anchor order.

## 2. Soft books — where you actually bet

### DraftKings, FanDuel
The volume leaders. Where most people have accounts and most money sits.

- Price to the public. Heavy favorites and overs get shaded because that's what
  the public bets.
- **Limit winners aggressively and fast.** Bet-sizing restrictions can arrive
  after a handful of winning bets, sometimes after one sharp bet on a stale line.
- Excellent promos, boosts, and profit boosts — which are frequently the largest
  real edge available to a small bettor, larger than any handicapping edge.
- Deep prop markets, which is where their pricing is weakest.
- SGP builders with coarse correlation models. That coarseness is exploitable.

### BetMGM, Caesars
- Middle of the pack. Slower to limit than DK/FD, generally.
- Caesars historically had better prices on mainstream markets; less true now.
- Both run frequent odds boosts that can be genuinely +EV.

### ESPN Bet, Fanatics
- Newer, chasing market share, which means **better promos and slower risk
  management**. Historically the softest prices among the majors.
- Fanatics in particular has been slow to limit.
- Prone to stale lines after news breaks — this is where a fast injury read
  actually cashes.

### bet365
- Strong internationally, especially soccer and tennis.
- Good live betting product.
- Limits sharp players, but is generally slower to do it than DK/FD.

## 3. What line movement tells you

- **Sharp book moves first** = real information. Follow it.
- **Soft book moves first, sharp book doesn't** = public money. Ignore it, and
  consider the other side once the price is worth it.
- **Reverse line movement** — the line moves *against* the majority of tickets —
  is the clearest public signal that sharp money is on the unpopular side. It
  works because ticket counts and handle diverge: a few large bets outweigh many
  small ones.
- **Steam move** — a rapid, correlated move across many books at once. Usually
  syndicate money. By the time you see it, the value is mostly gone; chasing
  steam is how you get the worst number of the day.
- **Limit increases are a stronger signal than line moves.** When a book raises
  its limit on a side, it's saying it's confident in that number. Pinnacle
  raising limits into game time means the number has been tested.

## 4. Line shopping — the most reliable edge available

**Always compare across books before recommending anything.** This isn't
optional polish, it's the highest-return, lowest-effort thing a bettor does.

- The difference between -110 and -105 is roughly 2.3% of EV. Most handicapping
  edges are smaller than that.
- The difference between +3 and +2.5 in the NFL is worth far more than any read
  you have on the game.
- **A half point at the wrong number costs more than most people's entire edge.**
- Odds boosts and promos at soft books frequently create genuinely +EV bets on
  sides you'd never otherwise take. Take them, size them properly, don't chase
  them.

## 5. Staying alive — limits and account management

You will get limited. Everyone does. What you control is how fast.

- Round numbers ($50, $100) attract less attention than exact Kelly amounts
  ($47.32). Nobody recreational bets $47.32.
- Betting stale lines immediately after news breaks is the fastest way to get
  flagged. Being right is not the problem; being right *quickly and repeatedly*
  is.
- Mixing in recreational-looking action (parlays, popular sides, live bets)
  extends account life. This is a real cost — those bets are usually -EV — and
  it's a tradeoff worth stating rather than pretending it's free.
- Promos and boosts are the best value at soft books and are also the fastest
  route to a flag, because promo abuse is exactly what their risk models hunt.
- **When you get limited at a book, that's information.** It means you were
  beating them. It is not a failure.

## 6. Practical anchor order

Implemented in `lib/odds.py:sharp_anchor()` and used automatically by
`lib/fetch_odds.py`:

1. Pinnacle
2. Circa
3. BetOnline / Bookmaker / Heritage / LowVig
4. Market median across all available books

**If none of the top three priced the market, say so.** A median anchor is a
much weaker estimate, and on a thin prop the absence of a sharp price often
means the answer is no bet — the sharps didn't price it because they don't think
they can beat it either.
