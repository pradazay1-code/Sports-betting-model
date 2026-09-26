# UFC Vegas 121: Rosas Jr. vs Barcelos

**Date and venue:** Sat 2026-09-26, Meta APEX, Las Vegas, under the Nevada commission (NSAC). Prelims start 5pm ET and the main card 8pm ET.

**When the data was pulled:** about 11:00–11:30 ET on fight day, by web search. The numbers come from `analyze.py`, which also writes them to `analysis.json`.

**No sharp anchor.** No Pinnacle or Circa price could be retrieved for any fight. Fair lines are therefore the power-devigged soft-book consensus; the main event also has Kalshi (59/41) as a cross-check. That alone caps every confidence level on this card at Medium.

**How claims are tagged:**
- `[FACT]` means retrieved.
- `[MODEL]` means computed with `lib/odds.py`.
- `[READ]` means my judgment.

---

## Past UFC bet history

- **This repo has none.** There is no `bets.db` and no earlier UFC report, so there is no personal UFC record to learn from yet. Anything taken tonight should go through `/log` so the next card has closing line value (CLV) to review.
- **Base rates `[FACT]`:**
  - UFC favorites win about 65%.
  - Underdogs cashed 32% in 2023–24 and 34.5% over ten years.
  - In 2026, 43.8% of bouts went to decision, down from 54.4% in 2024. KO/TKO is 37.4% this year.
- **This card `[MODEL]`:** the devigged favorites sum to **8.1 expected favorite wins out of 12.**
  - At least 3 upsets happen **81%** of the time.
  - All 12 favorites win **0.8%** of the time.
  - A four-favorite parlay of Osmanli, Hernandez, Nakamura and Jauregui hands the book **17.0%** instead of 4.5% (`python3 -m lib.odds parlay -285 -225 -325 -900`).
- **The market story this week `[FACT]`:** money has faded the hyped favorites.
  - Rosas went from −210 to −148.
  - Nakamura went from −500 to −325.
  - Osmanli went from −400 to −285.
  - **Two lines flipped outright.** Bryczek opened −210 and Vieira is now −185. Black/Amaya went from near pick'em to Black −205.
  - On DraftKings, Barcelos has **61% of the handle on 48% of the tickets.** Bigger bets are on the dog.
- **The fighters' own betting history `[FACT]`:**
  - Barcelos won 3 of his last 5 as the underdog, including Payton Talbott at **+710**.
  - Rosas's only loss was the UFC 287 upset to Christian Rodriguez.

---

## The card at a glance

| # | Fight | Winner (fair win %) | Rounds | Method | Best bet |
|---|---|---|---|---|---|
| 1 | Rosas Jr. vs Barcelos (5 rds) | **Rosas Jr.** (57.7%) | 5, full 25:00 | Decision | **Barcelos ML +150** (BetRivers), 0.75u |
| 2 | Pérez vs Dumont | **Pérez** (57.9%) | 3 | Decision | Pérez by decision, **only at +108 or better** |
| 3 | Bellato vs Edwards | **Bellato** (62.5%) | Ends R2 | KO/TKO | Bellato by KO/TKO, **only at +197 or better** |
| 4 | Hernandez vs Dumas | **Hernandez** (68.7%) | Ends R1 | Submission | Hernandez by sub, **only at +176 or better** |
| 5 | Osmanli vs Akylbek | **Osmanli** (72.3%) | Ends R2 | Submission | **Osmanli by submission +330**, 0.5u |
| 6 | Black vs Amaya | **Black** (66.1%) | 3 | Decision | Black by decision, **only at +137 or better** |
| 7 | Nakamura vs Hiestand | **Nakamura** (74.9%) | Ends R2 | KO/TKO (decision close) | No bet |
| 8 | Vieira vs Bryczek | **Vieira** (62.4%) | Ends R1 | Submission | No bet |
| 9 | Harrell vs Brener | **Harrell** (53.5%) | Ends R2 | KO/TKO | No bet (coin flip) |
| 10 | Jackson vs Simón | **Jackson** (66.0%) | 3 | Decision | No bet |
| 11 | Castañeda vs Alatengheili | **Castañeda** (78.3%) | 3 | Decision | Goes the distance, **only at −162 or better** |
| 12 | Jauregui vs Demopoulos | **Jauregui** (88.9%) | 3 | Decision | No bet |

**Weigh-ins `[FACT]`:**
- All 24 fighters made weight.
- **Castañeda was 0.5 lb over on his first attempt.** He shaved his head and made 136 about 20 minutes later.
- Short-notice replacement Hernandez weighed in **7 lb heavier** than Dumas.

---

## Bets

| Bet | Fair | Offered | EV% | Stake | Confidence |
|---|---|---|---|---|---|
| Barcelos ML | +136 (market) / +133 (read) | **+150 BetRivers** | +5.7% (market) / +7.5% (read); +2.5% at Kalshi's 41% | **0.75u** | Low–Medium |
| Rosas/Barcelos **Over 4.5 rds** | −141 (read) | −125 | +5.3% (range −0.1% to +9.8%) | **0.5u** | Low |
| **Osmanli by submission** | +285 (read) | +330 | +11.8% (range −9.7% to +29.0%) | **0.5u** | Low |

**Total risk is 1.75u.** The two main-event bets are positively correlated: Barcelos's winning path is a decision, and a Rosas submission kills both. Treat them as 1.25u on one fight.

**Trigger-only plays.** These method prices were not retrieved. Bet one only if you see the price listed or better; each is capped at 0.5u.
- Hernandez by submission +176 (fair +170). Alternatively, Hernandez inside the distance at −163 (fair −172).
- Pérez by decision +108 (fair +104).
- Bellato by KO/TKO +197 (fair +191).
- Tina Black by decision +137 (fair +133).
- Castañeda/Alatengheili goes the distance −162 (fair −170).

---

## Which fights end by KO/TKO

This comes from `ko.py`. For each fight, P(KO) = P(A wins) x P(KO | A wins) + P(B wins) x P(KO | B wins).
- The win probabilities are the devigged market `[MODEL]`.
- The KO-given-win shares are `[READ]`. Only one KO method price could be retrieved: Covers' implied Nakamura KO, about 34% with vig. That one anchors fight 7.

The card expects **3.6 KO/TKO finishes out of 12.** The 2026 UFC base rate (37.4%) would give 4.5. The card runs low because so many of these fighters are grapplers.

| Fight | P(KO/TKO) | Who lands it | Fair: fight ends by KO |
|---|---|---|---|
| Bellato vs Edwards | **49%** | Bellato 34%, Edwards 15% | +103 |
| Hernandez vs Dumas | 40% | Hernandez 25%, Dumas 14% (a submission is likelier) | +153 |
| Harrell vs Brener | 38% | Harrell 24%, Brener 14% | +163 |
| Nakamura vs Hiestand | 36% | Nakamura 30% | +176 |
| Vieira vs Bryczek | 33% | Bryczek 28%, Vieira 5% | +201 |
| Jackson vs Simón | 30% | Jackson 26% | +236 |
| Jauregui vs Demopoulos | 30% | Jauregui 29% | +237 |
| Castañeda vs Alatengheili | 25% | Castañeda 16%, Alatengheili 10% | +293 |
| Black vs Amaya | 24% | Amaya 14%, Black 10% | +326 |
| Rosas vs Barcelos | 21% | Barcelos 13%, Rosas 9% | +368 |
| Osmanli vs Akylbek | 21% | Osmanli 18% | +380 |
| Pérez vs Dumont | 11% | Dumont 8% | +784 |

**KO trigger prices.** None of these props were retrieved. Each price below is the worst price at which the bet still clears 2% EV. Each is capped at 0.5u, because the KO share behind it is a `[READ]`.
- Bellato/Edwards ends by KO/TKO (either fighter): +107
- Bellato by KO/TKO: +197
- Bryczek by KO/TKO: +262
- Nakamura by KO/TKO: +241
- Jauregui by KO/TKO: +248
- Jackson by KO/TKO: +286

---

## Fight-by-fight

### 1. Raul Rosas Jr. (−148) vs Raoni Barcelos (+124): bantamweight, 5 rounds

**Market `[FACT]`:**
- Opened −210/+177. Consensus is now −148/+124; DraftKings is −155/+130; BetRivers has Barcelos +150.
- Kalshi is 59/41.
- Handle is 61% on Barcelos against 48% of tickets.
- Over 3.5 rounds is −180 (Lineups: 64.3%). The O/U 4.5 line is −125/−105.

**Market `[MODEL]`:**
- Power devig makes Rosas 57.7% (−136) and Barcelos 42.3% (+136).
- Over 4.5 is 52.2%.

**Rosas `[FACT]`:**
- Ranked #12, age 21, record 12-1 (6-1 UFC). He is on a 5-fight win streak and is the youngest UFC main eventer ever.
- March 2026: unanimous decision over Rob Font, landing only **10 significant strikes** with **0 submission attempts.**
- Before that: outpointed Vince Morales and submitted Ricky Turcios with a rear-naked choke.
- Career rates: 1.34 SLpM, 42% accuracy, 52% striking defense, **6.10 takedowns per 15 minutes at 54%, 25% takedown defense.**
- Only loss: unanimous decision to Christian Rodriguez (UFC 287, 29-28 on all three cards). He won R1 and was out-grappled in R2 and R3.

**Barcelos `[FACT]`:**
- Ranked #13, age 39, record 22-5 (8 KO, 3 submissions, 11 decisions).
- Five straight wins: Talbott (+710), Garbrandt, Simón (**stuffed 6 of 6 takedowns**), and Montel Jackson (split decision; landed 6 of 18 takedowns with 7:45 of control).
- He has reached the final round in **6 straight fights.** This is his first main event.

**`[READ]`:**
- Rosas wins fights by getting to backs and winning scrambles, and he barely strikes. Barcelos is the best wrestler he has faced.
- The man who beat Rosas, Rodriguez, did it with grappling after Rosas faded.
- Barcelos's counter-risk is his age: the first 25-minute fight at 39 is where a sudden fade appears. That risk sits in R4–R5, and it is why the over is not a bigger play.
- I have this about 57/43. That is close to the market, but +150 on a 42–43% fighter is a bet.

**Pick:** Rosas by decision, 5 rounds.
**Bet:** Barcelos +150, 0.75u. It clears 2% only at **+145 or better.** At DraftKings's +130 it is −2.7%, so no bet there. The Over 4.5 at −125 is a 0.5u secondary.

**What would change my mind:**
- Late money pushes Rosas back past −175 against the handle.
- +150 is gone. At that point the Barcelos bet is dead.

### 2. Ailín Pérez (−150) vs Norma Dumont (+125): women's bantamweight co-main

**Market:** DraftKings −138/+117; BetMGM −165/+135. `[MODEL]` Pérez 57.9% (−138).

**Pérez `[FACT]`:**
- Ranked #4, record 13-2, six-fight win streak, and **all 6 UFC wins by decision.**
- February 2026: unanimous decision over Macy Chiasson with 6 takedowns and about 7.5 minutes of control.
- Career rates: 4.90 takedowns per 15 minutes; absorbs 1.58 significant strikes per minute.

**Dumont `[FACT]`:**
- Ranked #2, record 13-3 (9-3 UFC).
- Career rates: 3.86 SLpM at 50%, 65% striking defense, **72% takedown defense.**
- Her streak was snapped in April 2026 by Joselyne Edwards on a unanimous decision (29-28, 29-28, 30-27). She stayed on her back foot in R3, apparently believing she was up 2–0.

**`[READ]`:** This is a pure position fight: Pérez's chain wrestling against Dumont's 72% takedown defense. Control time wins rounds in Nevada. Dumont's habit of coasting late is a scorecard liability in a close fight.

**Pick:** Pérez by unanimous decision, 3 rounds.
**Bet:** Pérez by decision at +108 or better (fair +104). At the moneyline there is no edge (−0.1%).

### 3. Rodolfo Bellato (−180) vs Christian Edwards (+151): light heavyweight

**Market:** `[MODEL]` Bellato 62.5% (−166). Under 1.5 rounds is +130; the other side was not retrieved.

**Bellato `[FACT]`:**
- Record 13-3-1 (1 NC) with 8 KO wins.
- March 2026 (UFC 326): first-round KO of Luke Fernandez at 2:42.
- Two of his losses are by KO.

**Edwards `[FACT]`:**
- Record 8-5 (0-1 UFC).
- May 2026: lost a split decision to Modestas Bukauskas on short notice while absorbing heavy volume.
- Clinch, takedowns and leg kicks; two straight first-round TKOs on the regional scene before that.

**`[READ]`:** Bellato has the power and the experience. Edwards's clinch-and-grind approach can drag this into R2 and R3, which is why I'm not forcing the R1 under. Light heavyweight finish rates are high on both sides.

**Pick:** Bellato by KO/TKO, R2.
**Bet:** Bellato by KO/TKO at +197 or better; otherwise no bet.

### 4. Luis Hernandez (−238) vs Sedriques Dumas (+195): light heavyweight

**Market:**
- Covers −238/+195, others −225/+185; opened −192/+160.
- `[MODEL]` Hernandez 68.7%. Under 1.5 rounds (−215) is 65.7% fair.

**Hernandez `[FACT]`:**
- Record 8-0, with 5 submissions and 3 KOs. He is a Miami-Dade deputy.
- Won his Contender Series contract about 11 days ago with a R2 submission.
- Replaces the injured Mickey Gall on about 2 days' notice and moves up to 205.

**Dumas `[FACT]`:**
- Record 10-5 (1 NC), 1-5 over his last six, **and all 5 losses are stoppages:**
  - Jackson McVey, D'arce choke, R1 2:14 (April 2026)
  - Donte Johnson, guillotine, R2 1:25 (November 2025)
  - Oleksiejczuk, TKO, R1 2:49 (April 2025)
  - Ruziboev, TKO, R1 3:18 (March 2024)
  - Josh Fremd, guillotine, R2 (March 2023)
- 33% takedown defense in the UFC.
- Arrested in February 2024 (battery) and April 2025 (home-invasion robbery charges).

**`[READ]`:**
- The short-notice fade usually applies. Here the cut was a non-issue: he came in 7 lb heavy, not drained.
- He is in fight shape off the Contender Series, and Dumas prepared for Gall, another grappler.
- Dumas has been choked out three times in R1–R2.

**Pick:** Hernandez by submission, R1.
**Bet:** Hernandez by submission at +176 or better (fair +170), or Hernandez inside the distance at −163 or better. The moneyline itself is fair, so no bet on it.

**What would change my mind:** Hernandez spending the first 2 minutes striking at range with the taller man, or any report that the cut up to 205 was a bad one.

### 5. Mahammadali Osmanli (−285) vs Ilimbek Akylbek (+230): The Ultimate Fighter 34 (TUF 34) bantamweight final

**Market `[FACT]`:**
- DraftKings −285/+230; opened −400.
- O/U 1.5 rounds: −175/+135.
- O/U 2.5 rounds: −105/−125.
- Osmanli by submission +330.

**Market `[MODEL]`:**
- Osmanli 72.3%.
- The totals imply about a 55–58% chance the fight is finished at all.

**Osmanli `[FACT]`:**
- Record 12-1, with 10 finishes, **8 of them submissions.**
- On TUF he submitted Christian Strong and choked out Artem Belakh. Before the show: a R2 guillotine of Yunusov in November 2025.

**Akylbek `[FACT]`:**
- Record 10-3. December 2025: a R4 rear-naked choke of Mo Miller.
- That win snapped a streak of **back-to-back TKO losses** (Eskiev, Nazruloev) on ONE Friday Fights.
- The two had an altercation on the show.

**`[MODEL]` + `[READ]` fair price for the prop:**
- About 57% finish chance, times about 80% of finishes being Osmanli's, gives roughly 45% for Osmanli inside the distance.
- Times a 55–60% submission share gives **about 26%** (range 21–30%).
- The submission share is shaded down from his career 80% because Akylbek's own recent losses were TKOs.

**Pick:** Osmanli by submission, R2.
**Bet:** Osmanli by submission +330, 0.5u. It clears 2% only at **+292 or better.** At −285, the moneyline itself is −2.3% EV: that's MMA Mania's "Weekend Lock," and it has no edge.

**What would change my mind:** the submission prop sitting at +250 or shorter where you are, or Osmanli coming out looking to strike.

### 6. Tina Black (Valesca Machado) (−210) vs Melissa Amaya (+176): TUF 34 strawweight final

**Market:** Opened near pick'em and is now −205 to −219. `[MODEL]` Black 66.1%.

**Black `[FACT]`:**
- Age 30, record 16-4, 4-fight win streak.
- Last official fight: unanimous decision over Yasmin Castanho in December 2024. Her TUF bouts since then are exhibitions, so the layoff is less real than it looks on paper.
- 2.4 SLpM.

**Amaya `[FACT]`:**
- Record 8-0 with 5 straight finishes.
- On TUF she submitted Melisano and TKO'd Canuto.

**`[READ]`:** A price move this size is information. Black is the more complete, more experienced fighter. Amaya is dangerous early, then Black takes over.

**Pick:** Black by decision, 3 rounds.
**Bet:** Black by decision at +137 or better; otherwise no bet.

### 7. Rinya Nakamura (−325) vs Brady Hiestand (+260): bantamweight

**Market:**
- −325 up to −380; opened −500.
- `[MODEL]` Nakamura 74.9%. The devig methods disagree by 1.5 points, so read it as a range.
- Covers' implied method split: Nakamura by KO 34%, by decision 33%.

**Nakamura `[FACT]`:**
- Record 10-1 (3-1 UFC); Road to UFC winner.
- **Returns from a one-year layoff** (knee injury). Last fight: body-kick TKO of Nathan Fletcher in August 2025.
- 2.58 takedowns per 15 minutes at 81%.

**Hiestand `[FACT]`:**
- Record 9-2 (3-1 UFC).
- **Out since June 2024, a layoff of more than 2 years, including another ACL surgery.** Last fight: R3 rear-naked choke of Garrett Armfield.
- 42% takedown defense.

**`[READ]`:** A layoff over 18 months is a real hit (see `skills/sport-ufc.md`), and Hiestand's includes a second knee reconstruction. The market knows that and moved the price toward him anyway.

**Pick:** Nakamura by TKO, R2, with a decision close behind.
**Bet:** None. −325 is about −2% EV.

### 8. Rodolfo Vieira (−185) vs Robert Bryczek (+145): middleweight

**Market `[FACT]`:**
- **A full flip:** Bryczek opened −210 and Vieira +177; now Vieira is −185 and Bryczek +145.
- Vieira by submission is priced near 44%.
- O/U 1.5 rounds: −120/−110.

**Market `[MODEL]`:**
- Vieira 62.4%.
- Hold is 5.7%, the worst on the card.

**Vieira `[FACT]`:**
- Record 11-5 (6-5 UFC); **9 of 11 wins by submission, 6 of them in R1.** His cardio fades after R1.
- Two straight losses: head-kick KO by Bo Nickal (November 2025) and a unanimous decision to Eric McConico (April 2026).
- He has switched camps.

**Bryczek `[FACT]`:**
- Record 18-7 (1-2 UFC), 12 KO wins.
- Lost a unanimous decision to Cam Rowston (May 2026); KO'd Tavares (September 2025).

**`[READ]`:** Vieira either gets a submission early or fades and gets hurt late. The flip ate all the value: Vieira by submission at about 44% is where I have it.

**Pick:** Vieira by submission, R1.
**Bet:** None.

### 9. Josiah Harrell (−125) vs Elves Brener (+105): lightweight

**Market:** `[MODEL]` Harrell 53.5%.

**Harrell `[FACT]`:**
- Record 11-1 (0-1 UFC).
- His UFC debut was a R1 KO loss to Jacobe Smith (February 2026). Before that he had a rear-naked choke of Melvin Guillard.

**Brener `[FACT]`:**
- Record 16-6 (3-3 UFC), with 11 submission wins (9 in R1) and 3 Fight of the Night bonuses.
- On a 3-fight skid: Ribovics by unanimous decision (August 2025), Alvarez by KO (August 2024), and Orolbai.
- About 14 months since his last MMA fight; says he'll win by KO.

**`[READ]`:** Two fighters with finish equity and questionable defense. The market is right that this is a coin flip.

**Pick:** Harrell by KO/TKO, R2. This is the lowest-confidence pick on the card.
**Bet:** None.

### 10. Montel Jackson (−210) vs Ricky Simón (+175): bantamweight rematch

**Market:** `[MODEL]` Jackson 66.0%. Over 2.5 rounds is 62.8% fair.

**Jackson `[FACT]`:**
- Age 34, record 15-4 (9-4 UFC), 8 KOs.
- **4" height and 6.5" reach advantage.** 3.02 SLpM at 52%.
- On a 2-fight skid, including the split decision to Barcelos.

**Simón `[FACT]`:**
- Age 34, record 22-7-1.
- 3.03 SLpM at only 42%.
- 2-4-1 over his last 7: a draw with Yanez in March 2026 and a unanimous decision loss to Barcelos.
- Beat Jackson by unanimous decision at UFC 227 in 2018, in Jackson's UFC debut.

**`[READ]`:** 2018 means nothing now. Jackson's length and accuracy are the edge, and Simón's form is sliding.

**Pick:** Jackson by decision, 3 rounds.
**Bet:** None.

### 11. John Castañeda (−395) vs Alatengheili (+310): bantamweight

**Market:** `[MODEL]` Castañeda 78.3%. At −360, Castañeda is +0.1% EV, which is noise.

**Castañeda `[FACT]`:**
- **Was 0.5 lb over on his first weigh-in attempt;** shaved his head and made 136 on the second.
- The higher-volume, more active fighter.

**Alatengheili `[FACT]`:**
- Only one fight since May 2024.
- Negative striking differential; 5 KO and 3 submission wins.

**`[READ]`:**
- A struggling cut shows up in R3, not R1, so it is a mild negative for a −395 favorite, not a reason to take +310.
- Fair on the dog is +361, so he isn't "worth a look at +300" at these prices.

**Pick:** Castañeda by decision, 3 rounds.
**Bet:** Goes the distance at −162 or better (fair −170); not retrieved.

### 12. Yazmin Jauregui (−900) vs Vanessa Demopoulos (+625): strawweight

**Market:**
- −850 to −1050.
- `[MODEL]` Jauregui 88.9%. The devig methods disagree by 2.2 points, which is normal for a longshot, so read it as a range.
- Over 2.5 rounds is 67.2%.

**Jauregui `[FACT]`:**
- Record 11-2 (3-2 UFC).
- **Out since a R1 rear-naked choke loss to Ketlen Souza in September 2024,** about 2 years.

**Demopoulos `[FACT]`:**
- Age 38, on a 3-fight losing streak:
  - Jaqueline Amorim, armbar, R1 (September 2024)
  - Talita Alencar, unanimous decision; she gave up 4 takedowns and 12:38 of control
  - Jamey-Lyn Horth, unanimous decision

**`[READ]`:** The two concerns cancel. Jauregui's layoff and her last loss by submission argue against laying −900. Demopoulos being 38 and getting out-grappled by mid-tier opponents argues against her at +675, where fair is +733 to +805.

**Pick:** Jauregui by decision, 3 rounds.
**Bet:** None.

---

## Sources

- Weigh-ins: [UFC official](https://www.ufc.com/news/official-weigh-in-results-fight-night-rosas-barcelos-vegas-121), [Sherdog](https://www.sherdog.com/news/news/UFC-Vegas-121-weighin-results-24-fighters-make-weight-202956), [Bloody Elbow: Castañeda head shave](https://bloodyelbow.com/2026/09/25/ufc-vegas-121-star-shaves-his-head-to-make-weight-after-failing-on-first-attempt/), [Bloody Elbow: 7 lb gap](https://bloodyelbow.com/2026/09/25/ufc-vegas-121-short-notice-clash-made-official-despite-big-7lb-weight-difference-between-fighters/)
- Market and splits: [DK Network splits](https://dknetwork.draftkings.com/2026/09/26/ufc-fight-night-rosas-jr-vs-barcelos-fight-card-odds-betting-splits/), [Lineups trends](https://www.lineups.com/articles/ufc-fight-night-rosas-jr-barcelos-betting-trends-odds-data/), [Deadspin line movement](https://deadspin.com/ufc-vegas-121-line-movement-two-betting-favorites-have-completely-flipped/), [Coinbase/Kalshi market](https://www.coinbase.com/predictions/event/KXUFCFIGHT-26SEP26ROSBAR), [Sherdog opening odds](https://www.sherdog.com/news/news/UFC-Vegas-121-odds-Rosas-Jr-favored-Jauregui-opens-at-1000-202947), [MMA Mania props](https://www.mmamania.com/ufc-odds/474071/ufc-vegas-121-best-betting-props-parlays-and-picks-rosas-jr-vs-barcelos), [MMA Mania Weekend Lock](https://www.mmamania.com/ufc-odds/474571/heres-mmamania-coms-ufc-vegas-121-betting-odds-weekend-lock-whats-yours)
- Fight previews and odds: [Covers main event](https://www.covers.com/ufc/fight-night-raul-rosas-jr-vs-raoni-barcelos-predictions-picks-odds), [Covers Vieira/Bryczek](https://www.covers.com/ufc/fight-night-rodolfo-vieira-vs-robert-bryczek-predictions-picks-odds), [Covers Nakamura/Hiestand](https://www.covers.com/ufc/fight-night-brady-hiestand-vs-rinya-nakamura-predictions-picks-odds), [VSiN](https://vsin.com/mma/ufc-vegas-121-rosas-jr-vs-barcelos-odds-picks-predictions-and-best-bets/), [Clutchpoints Osmanli](https://clutchpoints.com/betting/mehemmedeli-osmanli-vs-ilimbek-akylbek-prediction-odds-pick-for-ufc-vegas-121), [Clutchpoints Hernandez](https://clutchpoints.com/betting/luis-hernandez-vs-sedriques-dumas-prediction-odds-pick-for-ufc-vegas-121), [Clutchpoints Jackson](https://clutchpoints.com/betting/montel-jackson-vs-ricky-simon-prediction-odds-pick-for-ufc-vegas-121), [Clutchpoints Jauregui](https://clutchpoints.com/betting/yazmin-jauregui-vs-vanessa-demopolous-prediction-odds-pick-for-ufc-vegas-121), [Clutchpoints Bellato](https://clutchpoints.com/betting/rodolfo-bellato-vs-christian-edwards-prediction-odds-pick-for-ufc-vegas-121), [Clutchpoints Harrell](https://clutchpoints.com/betting/josiah-harrell-vs-elves-brener-prediction-odds-pick-for-ufc-vegas-121), [BetMGM Pérez/Dumont](https://sports.betmgm.com/en/blog/ufc/vegas-121-norma-dumont-ailin-perez-predictions-odds-bm05/), [Low Kick Black/Amaya](https://www.lowkickmma.com/tina-black-favoured-melissa-amaya-tuf-34-strawweight-final/), [Deadspin best bets](https://deadspin.com/ufc-vegas-121-predictions-best-bets-for-saturdays-fight-card/)
- Fighter records: [UFCStats Dumont](http://ufcstats.com/fighter-details/d3f5d33d61cd00c9), [Cageside Press: Edwards over Dumont](https://cagesidepress.com/2026/04/25/ufc-vegas-116-joselyne-edwards-halts-norma-dumonts-win-streak-extends-her-own/), [UFCStats Dumas](http://ufcstats.com/fighter-details/4e6738062d469256), [Tapology Dumas](https://www.tapology.com/fightcenter/fighters/188574-sedriques-dumas), [ESPN: Rosas loss to Rodriguez](https://www.espn.com/mma/story/_/id/36126765/raul-rosas-drops-second-ufc-fight-decision-christian-rodriguez), [MMA Decisions UFC 287](https://mmadecisions.com/decision/13904/Christian-Rodriguez-vs-Raul-Rosas-Jr.), [RotoWire Demopoulos](https://www.rotowire.com/mma/player/vanessa-demopoulos-2204), [Heavy: Dumas arrest](https://heavy.com/sports/ufc/sedriques-dumas-new-arrest-mugshot/)
- Base rates: [FightMatrix favorites/underdogs](https://www.fightmatrix.com/2026/07/24/what-fightmatrix-rankings-reveal-about-ufc-favorites-and-underdogs/), [MMA Hive](https://www.mmahive.com/ufc-favorites-vs-underdogs/), [Grappler HQ UFC statistics](https://www.grapplerhq.com/mma/ufc-statistics/)
