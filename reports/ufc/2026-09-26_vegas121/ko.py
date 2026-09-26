"""
P(fight ends by KO/TKO) for UFC Vegas 121.

P(KO) = P(A wins) * P(KO | A wins) + P(B wins) * P(KO | B wins)

Win probabilities are the power-devigged market (analysis.json, [MODEL]).
The KO-given-win shares are [READ] -- no KO/TKO method prices were retrievable
except Covers' implied Nakamura-by-KO (~34% with vig), which anchors that one.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from lib.odds import prob_to_american  # noqa: E402

# fight n: (KO share if A wins, KO share if B wins, note)
KO_SHARE = {
    1: (0.15, 0.30, "Rosas is a back-taker; Barcelos 8 KO wins but none in his recent decision run"),
    2: (0.05, 0.20, "Perez 6/6 UFC wins by decision; Dumont a distance striker, few finishes"),
    3: (0.55, 0.40, "Bellato 8 KO incl. 2:42 R1 in March, KO'd twice; Edwards back-to-back R1 TKOs regionally"),
    4: (0.37, 0.45, "Hernandez 3 KO / 5 sub; Dumas KO'd twice in R1, but choked three times"),
    5: (0.25, 0.10, "Osmanli 8 of 10 finishes by sub; Akylbek TKO'd twice on ONE"),
    6: (0.15, 0.40, "Black a decision fighter; Amaya R1 TKO of Sugimoto, TKO of Canuto on TUF"),
    7: (0.40, 0.25, "anchored on Covers' implied Nakamura KO ~34% (devigged ~30%)"),
    8: (0.08, 0.75, "Bryczek 12 KO wins; Vieira head-kick KO'd by Nickal, fades after R1"),
    9: (0.45, 0.30, "Harrell KO'd R1 in debut; Brener KO'd by Alvarez, 11 of 16 wins by sub"),
    10: (0.40, 0.10, "Jackson 8 KO, 6.5in reach; Simon a volume grinder"),
    11: (0.20, 0.45, "Castaneda volume/decision; Alatengheili 5 KO wins"),
    12: (0.33, 0.03, "Jauregui 7 of 11 wins by KO/TKO but 2-yr layoff; Demopoulos not KO'd in 3-fight skid"),
}

fights = {f["n"]: f for f in json.loads(Path(__file__).with_name("analysis.json").read_text())["fights"]}
trig = lambda p: prob_to_american(p / 1.02)

rows = []
for n, (ka, kb, note) in KO_SHARE.items():
    f = fights[n]
    pa_ko, pb_ko = f["pa"] * ka, f["pb"] * kb
    rows.append((pa_ko + pb_ko, n, f["a"], pa_ko, f["b"], pb_ko, note))

rows.sort(reverse=True)
print(f"{'fight':<42}{'P(KO)':>7}{'fair':>7}{'need':>7}   by fighter")
for p, n, a, pa_ko, b, pb_ko, note in rows:
    print(f"{n:>2} {a} vs {b:<22}"[:42].ljust(42) + f"{p:7.1%}{prob_to_american(p):+7.0f}{trig(p):+7.0f}"
          f"   {a.split()[-1]} {pa_ko:.1%} (fair {prob_to_american(pa_ko):+.0f}, need {trig(pa_ko):+.0f}) | "
          f"{b.split()[-1]} {pb_ko:.1%} (fair {prob_to_american(pb_ko):+.0f})")
print(f"\nexpected KO/TKO finishes on the card: {sum(r[0] for r in rows):.2f} of 12 "
      f"(2026 UFC base rate 37.4% -> {0.374*12:.1f})")
