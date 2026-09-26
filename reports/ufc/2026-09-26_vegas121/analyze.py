"""
UFC Vegas 121 (Fight Night: Rosas Jr. vs Barcelos) -- 2026-09-26, Meta APEX, NSAC.

Every price below was retrieved by web search on 2026-09-26 (~11:00 ET) and is
tagged with where it came from. No sharp book (Pinnacle/Circa) price was
retrievable for any fight, so fair probabilities are the power-devigged soft
consensus (plus Kalshi for the main event) -- confidence is capped accordingly.

My own probabilities (READ) are explicit, with ranges, and are never mixed into
the market numbers. Run:  python3 -m reports.ufc.2026-09-26_vegas121.analyze
or simply:                python3 reports/ufc/2026-09-26_vegas121/analyze.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lib.odds import (  # noqa: E402
    american_to_decimal,
    devig,
    devig_spread,
    ev_from_american,
    prob_to_american,
    stake_units,
)

# ---------------------------------------------------------------- moneylines
# (fighter A, fighter B, [consensus A, consensus B], {best A}, {best B}, source)
FIGHTS = [
    dict(n=1, card="Main (5 rds)", wc="BW", a="Raul Rosas Jr.", b="Raoni Barcelos",
         ml=(-148, 124), best_a=(-148, "consensus"), best_b=(150, "BetRivers"),
         src="Covers consensus -148/+124; DK -155/+130; BetRivers Barcelos +150; Kalshi 59/41; opened -210/+177"),
    dict(n=2, card="Co-main", wc="W-BW", a="Ailin Perez", b="Norma Dumont",
         ml=(-150, 125), best_a=(-138, "DK"), best_b=(135, "BetMGM"),
         src="DK -138/+117; BetMGM -165/+135; others -155/+130"),
    dict(n=3, card="Main", wc="LHW", a="Rodolfo Bellato", b="Christian Edwards",
         ml=(-180, 151), best_a=(-170, "best of range"), best_b=(155, "best of range"),
         src="aggregated -180/+151; books -170 to -190 on Bellato"),
    dict(n=4, card="Main", wc="LHW", a="Luis Hernandez", b="Sedriques Dumas",
         ml=(-238, 195), best_a=(-225, "book"), best_b=(195, "Covers"),
         src="Covers -238/+195; others -225/+185; open -192/+160"),
    dict(n=5, card="Main (TUF final)", wc="BW", a="Mahammadali Osmanli", b="Ilimbek Akylbek",
         ml=(-285, 230), best_a=(-285, "DK"), best_b=(240, "book"),
         src="DK -285/+230; Covers -298/+240; opened -400"),
    dict(n=6, card="Main (TUF final)", wc="W-SW", a="Tina Black", b="Melissa Amaya",
         ml=(-210, 176), best_a=(-205, "book"), best_b=(184, "book"),
         src="-205/+170, -210/+176, -219/+184; opened near pick'em"),
    dict(n=7, card="Prelim", wc="BW", a="Rinya Nakamura", b="Brady Hiestand",
         ml=(-325, 260), best_a=(-325, "book"), best_b=(300, "book"),
         src="-325/+260 (BetMGM/Covers); up to -380/+300; opened -500"),
    dict(n=8, card="Prelim", wc="MW", a="Rodolfo Vieira", b="Robert Bryczek",
         ml=(-185, 145), best_a=(-185, "Covers"), best_b=(145, "Covers"),
         src="Covers -185/+145; OPENED Bryczek -210 / Vieira +177 (full flip)"),
    dict(n=9, card="Prelim", wc="LW", a="Josiah Harrell", b="Elves Brener",
         ml=(-125, 105), best_a=(-122, "book"), best_b=(110, "book"),
         src="-125/+105; -130/+110; opened -130/+111"),
    dict(n=10, card="Prelim", wc="BW", a="Montel Jackson", b="Ricky Simon",
         ml=(-210, 175), best_a=(-205, "book"), best_b=(185, "book"),
         src="-205/+173, -210/+175, -225/+185"),
    dict(n=11, card="Prelim", wc="BW", a="John Castaneda", b="Alatengheili",
         ml=(-395, 310), best_a=(-360, "book"), best_b=(310, "book"),
         src="-395/+310, -400/+300, -360/+280"),
    dict(n=12, card="Prelim", wc="W-SW", a="Yazmin Jauregui", b="Vanessa Demopoulos",
         ml=(-900, 625), best_a=(-850, "book"), best_b=(675, "book"),
         src="-900/+575, -850/+625, -1050/+675; opened -1000"),
]

# ------------------------------------------------------------- round totals
# (fight n, line, over, under, source)
TOTALS = [
    (1, 4.5, -125, -105, "MMA Mania odds table"),
    (1, 3.5, -180, None, "DK over 3.5 -180 (under not retrieved); Lineups: 64.3% over 3.5"),
    (4, 1.5, 165, -215, "Clutchpoints/BodyLock"),
    (5, 1.5, -175, 135, "DK"),
    (5, 2.5, -105, -125, "MMA Mania odds table"),
    (8, 1.5, -120, -110, "MMA Mania odds table"),
    (10, 2.5, -190, 145, "book via Clutchpoints"),
    (12, 2.5, -230, 175, "book via Clutchpoints"),
]

# --------------------------------------------------- candidate bets (READ p)
# p_lo/p/p_hi are MY estimates, explicitly [READ], built from the market
# probability times a conditional-method share, with the reasoning in `why`.
# offered=None means the price was NOT retrieved -> trigger price only.
CANDIDATES = [
    dict(n=5, bet="Osmanli by submission", offered=330, book="per Clutchpoints (book unnamed)",
         p_lo=0.21, p=0.26, p_hi=0.30,
         why="0.72 win (mkt) x ~0.62 finish|win x ~0.58 sub share. 8 of 12 wins by sub; "
             "both TUF wins by choke; Akylbek's two recent losses were TKOs, so the sub share is shaded "
             "down from his career 80%."),
    dict(n=1, bet="Rosas/Barcelos OVER 4.5 rounds", offered=-125, book="per MMA Mania table",
         p_lo=0.555, p=0.585, p_hi=0.61,
         why="Market: 64% over 3.5, ~54% over 4.5 -> it prices ~10% of a finish in R4-early R5. "
             "Barcelos has reached the final round 6 straight; Rosas's last 3 and Barcelos's last 3 "
             "wins all went to decision. The age-39 late fade is the real risk and is why this is not higher."),
    dict(n=1, bet="Barcelos ML", offered=150, book="BetRivers (per Lineups)",
         p_lo=0.41, p=0.43, p_hi=0.45,
         why="Market fair ~41-42% (soft consensus and Kalshi agree). +1-3 pts for TDD vs Rosas's "
             "54%-accurate shots and Rosas's 1.34 SLpM / 25% TDD; -1-2 pts for 39 y/o in a first 25-minute fight."),
    dict(n=4, bet="Hernandez by submission", offered=None, book="not retrieved",
         p_lo=0.32, p=0.37, p_hi=0.42,
         why="0.685 win (mkt) x ~0.55 sub|win. Hernandez 5 of 8 by sub; Dumas's 3 sub losses were all "
             "chokes inside R1-R2 (McVey D'arce 2:14 R1, Johnson guillotine R2, Fremd guillotine R2); 33% UFC TDD."),
    dict(n=2, bet="Perez by decision", offered=None, book="not retrieved",
         p_lo=0.45, p=0.49, p_hi=0.53,
         why="0.58 win (mkt) x ~0.85 dec|win. All 6 of Perez's UFC wins are decisions; Dumont is decision-heavy."),
    dict(n=3, bet="Bellato by KO/TKO", offered=None, book="not retrieved",
         p_lo=0.30, p=0.344, p_hi=0.40,
         why="0.63 win (mkt) x ~0.55 KO|win. 8 KO wins incl. 2:42 R1 KO in March; Edwards absorbed heavy volume vs Bukauskas."),
    dict(n=6, bet="Tina Black by decision", offered=None, book="not retrieved",
         p_lo=0.38, p=0.43, p_hi=0.48,
         why="0.665 win (mkt) x ~0.65 dec|win. Black is a volume-light decision fighter (2.4 SLpM, last win UD)."),
    dict(n=11, bet="Castaneda/Alatengheili goes the distance", offered=None, book="not retrieved",
         p_lo=0.58, p=0.63, p_hi=0.68,
         why="Consensus 'destined to go the distance'; Castaneda volume-decision profile; Alatengheili inactive."),
    dict(n=12, bet="Demopoulos ML", offered=675, book="best retrieved",
         p_lo=0.10, p=0.12, p_hi=0.14,
         why="Market fair ~12%. Jauregui's 2-yr layoff and last loss (R1 RNC) push up; Demopoulos age 38, "
             "0-3, out-grappled by Alencar (4 TD, 12:38 control) push down. Net ~ market."),
]

MIN_EV = 0.02


def trigger_american(p: float, min_ev: float = MIN_EV) -> float:
    """Worst price at which EV >= min_ev for win-probability p."""
    return prob_to_american(p / (1.0 + min_ev))


def fmt(a: float | None) -> str:
    if a is None:
        return "n/a"
    return f"{a:+.0f}"


def main() -> dict:
    out = {"fights": [], "totals": [], "candidates": []}

    print("=== MONEYLINES (power devig of soft consensus) ===")
    for f in FIGHTS:
        pa, pb = devig(list(f["ml"]), "power")
        spread = devig_spread(list(f["ml"]))
        hold = sum(1 / american_to_decimal(x) for x in f["ml"]) - 1
        ev_a = ev_from_american(pa, f["best_a"][0])
        ev_b = ev_from_american(pb, f["best_b"][0])
        row = dict(n=f["n"], a=f["a"], b=f["b"], pa=pa, pb=pb,
                   fair_a=prob_to_american(pa), fair_b=prob_to_american(pb),
                   hold=hold, method_spread=spread["widest_spread"], spread_flag=spread["meaningful"],
                   best_a=f["best_a"], best_b=f["best_b"], ev_best_a=ev_a, ev_best_b=ev_b,
                   src=f["src"], card=f["card"], wc=f["wc"])
        out["fights"].append(row)
        print(f"{f['n']:>2} {f['a']:<20} {pa:6.1%} fair {fmt(row['fair_a']):>6} | "
              f"{f['b']:<19} {pb:6.1%} fair {fmt(row['fair_b']):>6} | hold {hold:5.1%} | "
              f"best A {fmt(f['best_a'][0])} EV {ev_a:+.1%}  best B {fmt(f['best_b'][0])} EV {ev_b:+.1%} | devig spread {spread['widest_spread']:.1%}{' !' if spread['meaningful'] else ''}")

    print("\n=== ROUND TOTALS (power devig where both sides retrieved) ===")
    for n, line, over, under, src in TOTALS:
        if over is not None and under is not None:
            po, pu = devig([over, under], "power")
        else:
            po = pu = None
        out["totals"].append(dict(n=n, line=line, over=over, under=under, p_over=po, p_under=pu, src=src))
        if po is None:
            print(f"{n:>2} O/U {line}: over {fmt(over)} under {fmt(under)} -> one-sided, cannot devig ({src})")
        else:
            print(f"{n:>2} O/U {line}: over {fmt(over)} ({po:.1%}, fair {fmt(prob_to_american(po))}) "
                  f"under {fmt(under)} ({pu:.1%}, fair {fmt(prob_to_american(pu))})  [{src}]")

    print("\n=== CANDIDATE PROPS (my READ probability, range, EV at offered) ===")
    for c in CANDIDATES:
        fair = prob_to_american(c["p"])
        trig = trigger_american(c["p"])
        row = dict(c, fair=fair, trigger=trig)
        if c["offered"] is not None:
            row["ev"] = ev_from_american(c["p"], c["offered"])
            row["ev_lo"] = ev_from_american(c["p_lo"], c["offered"])
            row["ev_hi"] = ev_from_american(c["p_hi"], c["offered"])
            row["kelly_units"] = stake_units(c["p"], c["offered"])
            print(f"{c['n']:>2} {c['bet']:<42} p {c['p']:.1%} ({c['p_lo']:.0%}-{c['p_hi']:.0%}) "
                  f"fair {fmt(fair)} offered {fmt(c['offered'])} EV {row['ev']:+.1%} "
                  f"(range {row['ev_lo']:+.1%} to {row['ev_hi']:+.1%}) 1/4K {row['kelly_units']}u "
                  f"| need {fmt(trig)}+")
        else:
            row["ev"] = row["ev_lo"] = row["ev_hi"] = row["kelly_units"] = None
            print(f"{c['n']:>2} {c['bet']:<42} p {c['p']:.1%} ({c['p_lo']:.0%}-{c['p_hi']:.0%}) "
                  f"fair {fmt(fair)} offered n/a -> TRIGGER {fmt(trig)} or better")
        out["candidates"].append(row)

    Path(__file__).with_name("analysis.json").write_text(json.dumps(out, indent=2, default=str))
    return out


if __name__ == "__main__":
    main()
