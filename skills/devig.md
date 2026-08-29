# Devigging and fair odds

Reference for turning a posted price into a fair probability. Implemented in
`lib/odds.py` — **run the code, don't do this in your head.**

---

## 1. The conversions

| From | To | Formula |
|---|---|---|
| American (+) | decimal | `1 + A/100` |
| American (−) | decimal | `1 + 100/|A|` |
| decimal | implied prob | `1/D` |
| prob | decimal | `1/p` |
| decimal ≥ 2 | American | `(D−1) × 100` |
| decimal < 2 | American | `−100 / (D−1)` |

Worth memorizing as sanity checks: -110 = 1.909 = 52.38%. +100 = 2.00 = 50%.
-200 = 1.50 = 66.7%. +150 = 2.50 = 40%.

## 2. Why devig at all

A two-way market at -110/-110 sums to 104.76% implied probability. That extra
4.76% is the overround; the book's **hold** is `1 − 1/1.0476 = 4.55%`. Neither
side is really 52.38% to win — the market's actual opinion is 50/50, and the vig
is the fee for finding out.

If you compare a soft book's price to a *raw* implied probability you will find
"edges" everywhere and they'll all be the vig. Devigging is not optional
pre-processing. It's the whole calculation.

## 3. The four methods

Given raw implied probabilities `q_i` that sum to `Π > 1`:

### Multiplicative (proportional)
```
p_i = q_i / Π
```
Every outcome scaled by the same factor. Simple, stable, and the right default
for multiway markets. Its weakness: it assumes the book applies vig
proportionally, which **overstates the longshot's fair probability** in markets
with real favorite-longshot bias.

### Additive
```
p_i = q_i − (Π − 1)/n
```
Takes an equal *amount* off each outcome, which is proportionally more from the
longshot. The mirror-image bias of multiplicative. On extreme longshots it can
go negative — `lib/odds.py` clamps and renormalizes, and when it does, distrust
the result.

### Power
```
solve  Σ q_i^k = 1  for k > 1,   then  p_i = q_i^k
```
**Default for two-way markets.** Shrinks longshots more than favorites, which is
closer to how books actually build a line. Solved by bisection on `k`, which is
safe because every `q_i < 1` makes the sum strictly decreasing in `k`.

### Shin
```
p_i = [ √(z² + 4(1−z)·q_i²/Π) − z ] / (2(1−z))
solve for z ∈ [0,1) such that Σ p_i = 1
```
Models the overround as the book's protection against a proportion `z` of
insider money. Usually lands between multiplicative and power. The `z` it
recovers is interpretable on its own: a high `z` means the book is pricing heavy
adverse selection, which tells you something about the market before you even
look at the number.

## 4. House defaults

| Market type | Method | Why |
|---|---|---|
| Two-way (sides, totals, two-way props) | **power** | handles favorite-longshot bias |
| Multiway (futures, method of victory, 3-way soccer, first TD) | **multiplicative** | power and Shin destabilize with long tails |

**When methods disagree by more than ~1.5 points of probability, quote a range,
not a point estimate,** and let the width feed your confidence. `devig_spread()`
computes this and flags it.

Big disagreement almost always means one of three things, in descending order of
likelihood: the price is stale, the market is thin, or one side is a genuine
longshot where the method choice actually matters. None of those are reasons to
be more confident.

## 5. Anchoring — the part people get wrong

**Devig the sharp book. Bet the soft book. Never the same price for both.**

Priority for the anchor:
1. **Pinnacle** — low margin, high limits, welcomes sharp action, moves on money
   rather than on tickets. The closest thing to a true price that exists.
2. **Circa** — same posture, US-facing, especially strong on NFL sides/totals.
3. **BetOnline / Bookmaker / Heritage / LowVig** — reduced-juice offshore tier.
4. **Market median** — only when nothing above is available.

Soft books — DraftKings, FanDuel, BetMGM, Caesars, ESPN Bet, Fanatics, bet365 —
are where you **place** the bet. Their prices reflect where the public money is,
not where the true probability is. Devigging DraftKings against FanDuel is
devigging noise against noise.

**If no sharp book priced the market, say so.** That alone should cut confidence.
On thin props it usually means no bet — the reason the sharps didn't price it is
that they don't think they can beat it either.

Pull odds with `regions=us,us2,eu`. The `eu` region is where Pinnacle lives; a
US-only pull leaves you with nothing to anchor on.

## 6. Turning fair into a decision

```
EV%  = p_fair × decimal_offered − 1
Kelly f = (p·b − q) / b        b = decimal − 1,  q = 1 − p
stake  = f / 4                 quarter Kelly, capped at 2u
```

Report all three forms every time: **fair price, offered price, EV%.**

Under ~2% EV after devig is inside the error bars of the method itself. That's
not a thin edge, it's no edge. Say so.

## 7. Sanity checks before you trust a number

- Does the fair price sit *between* the two posted prices? It must.
- Do the fair probabilities sum to 1.0000? `lib/odds.py` renormalizes, so if
  they don't, something upstream is broken.
- Is the "edge" implausibly large? Over ~10% EV on a mainstream market is
  almost never free money. In order of likelihood: you mis-mapped the outcomes,
  the line is stale, one side is a different number than you think, or the book
  has already taken it down. Check all four before you get excited.
- Did you compare markets at the **same number**? -2.5 and -3 are different
  markets. Devigging one against the other silently buys you a key number.

## 8. Worked example

Pinnacle: Chiefs +118 / Bills −128.

```
$ python3 -m lib.odds devig 118 -128
market      : 2-way — +118 / -128
overround   : 1.0201   hold: 1.97%
method      : power (house default for 2-way)

outcome        raw     fair   fair line
0           0.4587   0.4482      +123.1
1           0.5614   0.5518      -123.1

all methods:
  multiplicative  0.4497  0.5503
  additive        0.4487  0.5513
  power           0.4482  0.5518  <- used
  shin            0.4487  0.5513

  methods agree within 0.0015 — point estimate is fine.
```

Note the hold: 1.97%. That's Pinnacle. A soft book would be holding 4-5% on the
same game, which is precisely why we anchor here and bet there.

DraftKings has the Chiefs +132.

```
$ python3 -m lib.odds ev --fair 123.1 --offered 132
fair prob   : 0.4482   (+123.1)
offered     : +132   (decimal 2.3200)
EV          : +3.99%
kelly       : 0.7555% of bankroll  (1/4)
stake       : 0.76u
verdict     : BET
```

Fair +123.1, offered +132, EV +3.99%, 0.76u at quarter Kelly. That's a bet —
**after** you check injuries, and only if the number is still there when you get
to the window.
