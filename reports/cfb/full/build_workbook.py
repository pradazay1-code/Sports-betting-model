import json, sys
from statistics import NormalDist
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
sys.path.insert(0, "/home/user/Sports-betting-model")
from lib.odds import american_to_decimal, prob_to_american
from lib.venues import home_edge, find
exec(open("/home/user/Sports-betting-model/reports/cfb/full/games.py").read())
A = json.load(open("/home/user/Sports-betting-model/reports/cfb/full/analysis.json"))
R = {r["id"]: r for r in A["rows"]}
N = NormalDist()

# ---------- final decisions: the math overrides the first-draft bet text where they disagree ----------
FINAL = {
 109: ("UNDER 52.5 (+116)", "Weather", "1", "Medium-High", 1),
 28:  ("Texas A&M +9.5 (-110); also UNDER 53.5 only if available", "Model", "1", "Medium", 1),
 5:   ("UNDER 49.5 (-110) - ONLY at 49.5; pass at 47.5", "Weather+Shop", "1", "Medium", 1),
 21:  ("Penn State -9.5 (-115)", "Model", "0.5", "Low-Med", 2),
 26:  ("UNDER 61.5 (-110) - ONLY at 61.5, not 59.5", "Model+Shop", "0.5", "Low-Med", 2),
 34:  ("UNDER 58.5 (-104). No side: +6.5 only +0.9% EV", "Model", "0.5", "Low-Med", 2),
 13:  ("OVER 38.5 (-110)", "Model", "0.5", "Low-Med", 2),
 114: ("UNDER 48.5", "Weather", "0.5", "Low-Med", 2),
 104: ("UNDER 49.5", "Weather", "0.5", "Low-Med", 2),
 12:  ("UNDER 48.5 (not 47.5)", "Weather+Shop", "0.5", "Low-Med", 2),
 25:  ("Cincinnati +6.5 (-108)", "Model", "0.5", "Low", 3),
 29:  ("No side: SP+'s USC lean was its own underdog bias (corrected it equals the market). UNDER 62.5 only if available", "Shop", "0.5 if 62.5", "Low", 3),
 115: ("UNDER 44.5", "Weather", "0.25", "Low", 3),
 14:  ("OVER 44.5 - marginal (+2.8%), price unconfirmed", "Model", "0.25", "Low", 3),
 11:  ("NO BET at -120 (EV -3.9%). FPI residual is real but the juice eats it - bet Ole Miss only at +4, or +3.5 at -105 or better", "None", "0", "Low", None),
 118: ("PASS - storm listed but Poughkeepsie forecast not verified", "None", "0", "Low", None),
}
CONF_RANK = {"Medium-High": 0, "Medium": 1, "Low-Med": 2, "Low": 3}

def fmt_m(x): return "" if x is None else f"{x:+.1f}"
def pick(r):
    dm = r["desk_margin"]; fav = r["h"] if dm > 0 else r["a"]
    p = r["desk_ph"] if dm > 0 else 1 - r["desk_ph"]
    return fav, p

HDR = PatternFill("solid", fgColor="1F3864"); HF = Font(bold=True, color="FFFFFF", size=10)
TIER = {1: PatternFill("solid", fgColor="C6EFCE"), 2: PatternFill("solid", fgColor="FFEB9C"), 3: PatternFill("solid", fgColor="FCE4D6")}
CF = {"Medium-High": "63BE7B", "Medium": "A9D08E", "Low-Med": "FFE699", "Low": "F4B084"}
SUB = PatternFill("solid", fgColor="D9E2F3")

def header(ws, ncols, row=1):
    for c in range(1, ncols+1):
        cl = ws.cell(row=row, column=c); cl.fill = HDR; cl.font = HF
        cl.alignment = Alignment(wrap_text=True, vertical="center")
    ws.freeze_panes = ws.cell(row=row+1, column=1); ws.row_dimensions[row].height = 32
def widths(ws, w):
    for i, x in enumerate(w, 1): ws.column_dimensions[get_column_letter(i)].width = x
def wrap(ws, first=2):
    for row in ws.iter_rows(min_row=first):
        for c in row: c.alignment = Alignment(wrap_text=True, vertical="top")

wb = Workbook()

# =================== 1. BEST BETS ===================
ws = wb.active; ws.title = "Best Bets"
ws.append(["Tier","Rank","Kick ET","Game","BET","Type","Stake (u)","Win prob","EV","Confidence","Basis","What kills it"])
bets = []
for gid, (txt, typ, stake, conf, tier) in FINAL.items():
    if tier is None: continue
    r = R[gid]
    first = txt.split()[0].upper()
    if first in ("UNDER", "OVER"):                       # a totals bet
        if "wx_scen" in r:   p, ev = r["bet_p"], r["bet_ev"]
        elif "tot_ev" in r:  p, ev = r["tot_p"], r["tot_ev"]
        else:                p, ev = None, None
    elif txt.lower().startswith("no side") and "tot_ev" in r:   # explicitly not a side bet: the play is the total
        p, ev = r["tot_p"], r["tot_ev"]
    elif "side_ev" in r:                                  # a side bet - never report the total's numbers here
        p, ev = r["side_p"], r["side_ev"]
    elif "tot_ev" in r:                                   # 'no side' rows whose only play is a total
        p, ev = r["tot_p"], r["tot_ev"]
    else:
        p, ev = None, None
    bets.append((tier, CONF_RANK[conf], -(p or 0), gid, txt, typ, stake, conf, p, ev))
bets.sort()
BASIS = {
 109: "Nor'easter in the Bronx: N 20-30, gusts 45-55, 90% rain, wind advisory - yet the OVER is a -144 favourite. The market has not priced the storm. +EV if the storm costs more than 1 point; +12% even on conservative assumptions.",
 28: "Both independent models, bias-corrected, land on A&M: SP+ LSU by 4, FPI LSU by ~5.4, vs market 9.5. Line already moved toward A&M from +10.5. A&M 2-0 vs LSU under Elko/Reed incl. 49-25 in Baton Rouge.",
 5: "Nor'easter at BC: rain the entire game, NE sustained 18-35, gusts 40+. SP+ neutral total 53; the storm must cost >4.3 pts for 49.5 to be +EV - base case -6 gives +9%. Books split 47.5-49.5: only the top number works.",
 21: "Two-model consensus (SP+ 16.5, FPI ~19) far above -9.5; no QB injury explains it. +9.0% EV after heavy market shrinkage, but the gap is big enough to size down: early-season models still carry preseason weight.",
 26: "SP+ total 54 vs 61.5 with clear weather - the largest SP+ total gap on the board. Market likely pricing OSU's 70-point game vs Oregon. Only at 61.5.",
 34: "SP+ total 53.7 vs 58.5, and the under is the cheaper side at -104.",
 13: "SP+ total 46.1 vs a board-low 38.5, sunny with 5-10 mph wind in Ann Arbor. The Iowa-under habit may have pushed the number too far.",
 114: "Philadelphia storm edge: sustained 15-25, gusts 45, rain from midday. EV assumes the FCS total has NOT been adjusted; if it has, this is -4.5% (the vig).",
 104: "Same Philadelphia storm-edge conditions as Lehigh/Penn, same unadjusted-market assumption.",
 12: "Rain inside the kickoff window; SP+ neutral total 49. Books split 47.5/48.5 - the extra point is the reliable part of this edge.",
 25: "Current models (ESPN Matchup Predictor 58.7%, dimers 30-26) have KSU by ~3-4 vs 6.5. Tightest market on the board (3.05% hold) - sharpest money, smallest stake.",
 29: "Oregon -1.5 to -3.5 and totals 61.5-62.5 across books. SP+ total 59. Under is only a bet at 62.5.",
 115: "Coastal Connecticut: wind advisory, gusts 40-55 inland. But 44.5 is already low for FCS - part of the storm may be in it.",
 14: "SP+ total 49 vs 44.5. Marginal after shrinkage and the price was not retrieved.",
}
KILL = {k: next(g["kill"] for g in G if g["id"] == k) for k in FINAL}
KILL[5] = "Storm track shifting east before noon, or only 47.5/48.5 available"
KILL[12] = "Rain clearing before 15:30 ET, or only 47.5 available"
for rank, b in enumerate(bets, 1):
    tier, _, _, gid, txt, typ, stake, conf, p, ev = b
    g = R[gid]
    ws.append([tier, rank, g["et"], f"{g['a']} @ {g['h']}", txt, typ, stake,
               None if p is None else round(p*100, 1), None if ev is None else round(ev*100, 1),
               conf, BASIS.get(gid, ""), KILL.get(gid, "")])
header(ws, 12)
for row in range(2, ws.max_row+1):
    t = ws.cell(row=row, column=1).value
    for c in range(1, 13): ws.cell(row=row, column=c).fill = TIER[t]
    ws.cell(row=row, column=5).font = Font(bold=True, size=10)
    ws.cell(row=row, column=10).fill = PatternFill("solid", fgColor=CF[ws.cell(row=row, column=10).value])
ws.append([])
tot_u = sum(float(b[6].split()[0]) for b in bets)
storm = [109, 5, 114, 104, 115]
storm_u = sum(float(FINAL[i][2].split()[0]) for i in storm)
NOTES = [
 f"TOTAL EXPOSURE if you play everything: {tot_u:.2f}u. The disciplined card is TIER 1 ONLY: 3u.",
 f"CORRELATION WARNING: {storm_u:.2f}u rides on ONE storm (Fordham, BC, Lehigh/Penn, Villanova, Sacred Heart). If the Nor'easter under-delivers, those lose together. Do not add to them.",
 "Win prob / EV use the DESK number: bias-corrected models blended with the market (40% model with 2+ models, 25% with one; 30% for SP+ totals). Weather EVs are the BASE scenario - see the Weather tab for the full range.",
 "Every stake is quarter-Kelly-or-less and capped: 2u ceiling, 1u on anything FCS or resting on an input marked [READ].",
 "Prices marked -110 where the exact price was not retrieved. Confirm at your book before betting: a worse price can flip a thin edge.",
]
for n in NOTES:
    ws.append([n]); ws.merge_cells(start_row=ws.max_row, start_column=1, end_row=ws.max_row, end_column=12)
    ws.cell(row=ws.max_row, column=1).font = Font(bold=True, color="C00000"); ws.row_dimensions[ws.max_row].height = 30
widths(ws, [5,5,7,30,42,13,8,8,7,11,70,40]); wrap(ws)

# ----- shop table on the same sheet
ws.append([]); ws.append(["CONDITIONAL - only if you are betting the game anyway: take the better number"])
ws.cell(row=ws.max_row, column=1).font = Font(bold=True, size=11, color="1F3864")
SHOP = [(102,"Citadel +11.5  or  Chattanooga -10.5  (books 1 pt apart)"),(119,"Cornell +15.5  or  Yale -14  (1.5 pts apart)"),
        (117,"Monmouth +3  (not +2.5)"),(3,"Colorado +10  or  Baylor -9.5"),(18,"NMSU +13.5 or UNM -11.5; over 48.5 / under 50.5"),
        (23,"ODU +6.5  or  JMU -5.5"),(32,"WSU +10.5  or  Arizona -9.5"),(38,"Charlotte +10.5; over 48.5 / under 50.5"),
        (30,"App State +14  (not +13.5)"),(4,"Louisville -13  (not -13.5)")]
for gid, s in SHOP: ws.append(["","",R[gid]["et"],f"{R[gid]['a']} @ {R[gid]['h']}", s])
ws.append([]); ws.append(["STRUCTURAL (price not retrieved - bet only if the team total is posted at or above the implied number):"])
ws.cell(row=ws.max_row, column=1).font = Font(bold=True, size=11, color="1F3864")
for gid in (7,17,16,36,6,24,2):
    r = R[gid]; ft = (r["tot"] + abs(r["sp"]))/2
    fav = r["h"] if r["sp"] < 0 else r["a"]
    ws.append(["","",r["et"],f"{r['a']} @ {r['h']}", f"{fav} team-total UNDER / 2H under (implied team total {ft:.1f})"])

# =================== 2. ALL GAMES, ranked ===================
ws2 = wb.create_sheet("All Games (ranked)")
cols = ["Rank","Div","Kick ET","Away","Home","Mkt spread (home)","Mkt total","MARKET proj score","DESK proj score",
        "Desk pick (SU)","Desk win %","Models used","Model margin vs mkt","Weather","Confidence","BEST BET","Stake","Type"]
ws2.append(cols)
allr = []
for r in A["rows"]:
    gid = r["id"]
    txt, typ, stake, conf, tier = FINAL.get(gid, (r["bet"], r["btype"], r["stake"], r["conf"], None))
    fav, p = pick(r)
    key = (tier if tier else 9, CONF_RANK.get(conf, 3), -p)
    allr.append((key, r, txt, typ, stake, conf, fav, p))
allr.sort(key=lambda x: x[0])
for i, (k, r, txt, typ, stake, conf, fav, p) in enumerate(allr, 1):
    mods = []
    if "fpi_margin" in r: mods.append("FPI")
    if "sp_h" in r or r["id"] in (4,): mods.append("SP+")
    if r["id"] in (12,25,15): mods.append("numberFire/dimers")
    mproj = f"{r['h']} {r['mkt_h']} - {r['a']} {r['mkt_a']}" if "mkt_h" in r else "total n/a"
    dproj = f"{r['h']} {r['desk_h']} - {r['a']} {r['desk_a']}" if "desk_h" in r else "total n/a"
    ws2.append([i, r["div"], r["et"], r["a"], r["h"], r["sp"], r.get("tot"), mproj, dproj, fav, round(p*100,1),
                ", ".join(mods) or "none (market only)", None if "model_vs_mkt" not in r else round(r["model_vs_mkt"],1),
                r.get("wx","not retrieved"), conf, txt, stake, typ])
header(ws2, len(cols))
for row in range(2, ws2.max_row+1):
    c = ws2.cell(row=row, column=15); c.fill = PatternFill("solid", fgColor=CF.get(c.value, "FFFFFF"))
    ws2.cell(row=row, column=16).font = Font(bold=True, size=10)
    ws2.cell(row=row, column=9).font = Font(bold=True, size=10)
widths(ws2, [5,5,7,17,17,9,7,28,28,16,8,14,10,34,11,44,7,12]); wrap(ws2)

# =================== 3. GAME ANALYSIS (narrative) ===================
ws3 = wb.create_sheet("Game Analysis")
ws3.append(["Kick ET","Div","Game","Records / context","Line movement / book spread","Injuries & availability","Weather",
            "ANALYSIS","BEST BET","Confidence"])
for k, r, txt, typ, stake, conf, fav, p in sorted(allr, key=lambda x: (x[1]["div"], x[1]["et"])):
    ws3.append([r["et"], r["div"], f"{r['a']} @ {r['h']}", r.get("rec",""), r.get("line",""), r.get("inj",""),
                r.get("wx","not retrieved"), r["ana"], txt, conf])
header(ws3, 10)
widths(ws3, [7,5,30,28,28,34,30,80,36,10]); wrap(ws3)

# =================== 4. MODELS vs MARKET ===================
ws4 = wb.create_sheet("Models vs Market")
ws4.append(["Game","Mkt home margin","FPI home win %","FPI margin (raw)","SP+ proj (home-away)","SP+ margin (raw)",
            "Model consensus (bias-corrected)","Consensus minus market","DESK margin (blended)","SP+ total","Mkt total","SP+ total minus mkt","Other models"])
for r in A["rows"]:
    if r.get("n_models", 0) == 0: continue
    ws4.append([f"{r['a']} @ {r['h']}", -r["sp"],
                None if "fpi_h" not in r else round(r["fpi_h"]*100,1),
                None if "fpi_margin" not in r else round(r["fpi_margin"],1),
                "" if "sp_h" not in r else f"{r['sp_h']}-{r['sp_a']}",
                None if "sp_margin" not in r else round(r["sp_margin"],1),
                round(r["model_margin"],1), round(r["model_vs_mkt"],1), round(r["desk_margin"],1),
                None if "sp_total" not in r else round(r["sp_total"],1), r.get("tot"),
                None if "sp_total" not in r else round(r["sp_total"]-r["tot"],1), r.get("other","")])
header(ws4, 13)
ws4.append([])
for n in [f"MEASURED BIAS toward the market favourite: FPI {A['FPI_BIAS']:+.2f} pts (n={A['n_fpi']}), SP+ {A['SP_BIAS']:+.2f} pts (n={A['n_sp']}). FPI runs hot on favourites, SP+ runs cold.",
          "Both are removed before comparing to the market. Raw gaps are NOT edges: most of them are these biases.",
          "Example: SP+ projects Oregon 30-29 over USC (a USC lean). Bias-corrected it becomes Oregon by 3.1 vs the market's 3.5 - no edge at all.",
          f"SP+ TOTALS show no systematic lean ({A['SP_TOT_BIAS']:+.2f} pts), so a large SP+ total gap is informative on its own.",
          "The market is still weighted 60-75% in every DESK number. Two respected public models do not outvote a liquid market - they nudge it.",
          "FPI does not rate FCS teams, so FCS games carry market numbers only."]:
    ws4.append([n]); ws4.merge_cells(start_row=ws4.max_row, start_column=1, end_row=ws4.max_row, end_column=13)
    ws4.cell(row=ws4.max_row, column=1).font = Font(bold=True, color="1F3864")
widths(ws4, [30,9,9,9,11,9,13,12,11,8,8,10,60]); wrap(ws4)

# =================== 5. WEATHER ===================
ws5 = wb.create_sheet("Weather")
ws5.append(["Game","Kick ET","Category","Forecast (retrieved)","Mkt total","Scenario","Storm cost (pts)","Projected total","P(under)","EV"])
order = {"storm_core":0,"storm_edge":1,"rain":2,"wind":3,"clear":4,"indoor":5}
for r in sorted([x for x in A["rows"] if x.get("wx")], key=lambda x: order.get(x.get("wxc",""),9)):
    base_row = [f"{r['a']} @ {r['h']}", r["et"], r.get("wxc",""), r["wx"], r.get("tot")]
    if "wx_scen" in r:
        for j, s in enumerate(r["wx_scen"][:3]):
            lab, a, mu, p, ev = s
            ws5.append((base_row if j == 0 else ["","","","",""]) + [lab, a, round(mu,1), round(p*100,1), round(ev*100,1)])
        price = r["evcalc"]["price"]
        pu = 0.5 if price != 116 else (1-0.5653)
        ws5.append(["","","","","", "market already fully priced it", None, None, round(pu*100,1), round((pu*american_to_decimal(price)-1)*100,1)])
        ws5.append(["","","","","", f"break-even: storm must cost more than {-r['wx_breakeven_adj']:.1f} pts", None, None, None, None])
    else:
        ws5.append(base_row + ["-", None, None, None, None])
header(ws5, 10)
ws5.append([])
for n in ["Storm-cost assumptions are [READ], not data: core storm (sustained 20+ mph, gusts 45+, heavy rain) -6 pts base, range -3 to -9; storm edge (15-25 mph, gusts ~40) -4, range -2 to -6; rain only -2, range -1 to -3.",
          "Why wind and not rain: sustained wind above ~15-20 mph degrades deep passing and field-goal range; rain alone does much less. Every storm game here clears that wind threshold.",
          "Fordham is the one storm game with direct evidence the market has NOT adjusted: the OVER is a -144 favourite. For the others the EV assumes an unadjusted FCS total - the 'already priced' row shows the downside if that is wrong.",
          "Hanover NH (Monmouth @ Dartmouth) is NOT a storm game - NNE 5-10 mph. Not every Northeast game gets the storm treatment.",
          "Weather was retrievable for 20 of 59 games. The rest were not reachable (Open-Meteo and weather sites are proxy-blocked); nothing was assumed for them."]:
    ws5.append([n]); ws5.merge_cells(start_row=ws5.max_row, start_column=1, end_row=ws5.max_row, end_column=10)
    ws5.cell(row=ws5.max_row, column=1).font = Font(bold=True, color="1F3864")
widths(ws5, [30,7,11,52,8,34,10,10,8,8]); wrap(ws5)

# =================== 6. HOME FIELD ===================
ws6 = wb.create_sheet("Home Field")
ws6.append(["Game","Venue","Crowd pts","Altitude pts","Altitude differential (ft)","Total HFA","vs flat baseline","Note"])
for r in A["rows"]:
    h = r["h"]; v = find(h)
    if v and v.team.strip().lower() == h.strip().lower():
        e = home_edge(h, r["a"].replace(" (FCS)",""), fcs=(r["div"]=="FCS"))
        ws6.append([f"{r['a']} @ {h}", e["venue"], e["crowd_points"], e["altitude"]["points"], e["altitude"]["differential_ft"],
                    round(e["total_points"],2), round(e["vs_baseline"],2),
                    e["altitude"].get("warning","") or ("visitor elevation unknown - defaulted to sea level" if not e["away_altitude_known"] else "")])
header(ws6, 8); widths(ws6, [32,30,9,9,12,9,10,60]); wrap(ws6)

# =================== 7. NO MARKET ===================
ws7 = wb.create_sheet("No Market")
ws7.append(["Div","Away","Home","Status"])
for d, a, h in NO_MARKET: ws7.append([d, a, h, "Identified on the slate. No line retrievable. Nothing estimated."])
header(ws7, 4); widths(ws7, [6,24,42,60])

# =================== 8. METHOD & SOURCES ===================
ws8 = wb.create_sheet("Method & Sources")
M = [("WHAT THIS IS",""),
 ("Coverage", f"{len(A['rows'])} games with a retrieved market (40 FBS, 19 FCS) + {len(NO_MARKET)} identified with no market. Friday games (already played) excluded."),
 ("Retrieved [FACT]", "Spreads, totals, moneylines, two-sided prices, ESPN FPI, Bill Connelly SP+ projections & ratings, numberFire/dimers/SportsLine, weather, injury reports. All via web search, 2026-09-26."),
 ("Derived [MODEL]", "Market-implied score, devigged fair prices (power), model bias, bias-corrected consensus, desk margin/total, win probability, EV, weather scenarios."),
 ("Judgment [READ]", "Model-vs-market weights (40%/25%/30%), storm cost per category, margin SD 16.5 FBS / 17.5 FCS, total SD 14."),
 ("",""),("THE PROJECTIONS",""),
 ("MARKET proj score", "Recovered exactly from spread + total: fav = (total + |spread|)/2. It is the market's own opinion, so it can never produce an edge by itself."),
 ("DESK proj score", "Market blended with bias-corrected models (where any exist), plus the weather adjustment (where retrieved). Where no model or weather exists it EQUALS the market - stated, not hidden."),
 ("Desk pick / win %", "Straight-up favourite on the desk margin, win probability from a normal on that margin."),
 ("",""),("WHY MOST GAMES ARE 'NO BET'",""),
 ("The rule", "Under 2% EV after devig is noise. Most games are either priced right, or the only disagreement is a known model bias."),
 ("Proof", "Three first-draft picks were killed by the arithmetic: USC +3.5 (the 'edge' was SP+'s underdog bias), Ole Miss +3.5 (real signal, -120 juice kills it), Missouri +6.5 (+0.9%, below the floor)."),
 ("",""),("GAPS - STATED, NOT FILLED",""),
 ("Injuries", "Only the injuries surfaced in reporting were retrieved (Lagway, Barnett, the PSU/WIS report). CFB has no mandated injury report. Check starting QBs before kickoff - a QB out is worth 4-14 pts."),
 ("FCS models", "FPI does not cover FCS; no public FCS projection was retrievable. FCS numbers are market + weather only, and FCS stakes are capped at 1u."),
 ("Weather", "20 of 59 games. The rest were not reachable."),
 ("Prices", "Where only a spread/total was retrievable, -110 is assumed and marked. Confirm your price."),
 ("No-market games", f"{len(NO_MARKET)} games, listed on their own tab."),
 ("",""),("SOURCES",""),
 ("Odds", "FanDuel Research, Covers, Action Network, RotoWire, SportsGrid, Bleacher Nation, BetMGM, Yahoo/iHeart previews, sportsbookreview"),
 ("Models", "ESPN FPI via Saturday Down South / BVM / SI / Yahoo team sites; Bill Connelly SP+ via Inside the Hall, SI team sites, SDS; numberFire; dimers; SportsLine (CBS)"),
 ("Weather", "NWS, News 12 Bronx, weather.com, FOX 5 NY, CBS/6abc Philadelphia, WTNH/Stamford Advocate (CT), The Key Play / Fighting Gobbler (BC), WATE, WeatherBug, Weather Underground"),
 ("Injuries", "Yahoo/SI team sites, Black Shoe Diaries, Bucky's 5th Quarter, Heartland College Sports, statecollege.com"),
 ("Storm game list", "VSiN 'College Football Games Impacted by Nor'easter This Weekend'"),
]
for a, b in M: ws8.append([a, b])
header(ws8, 2)
for row in range(2, ws8.max_row+1):
    a = ws8.cell(row=row, column=1)
    if a.value and not ws8.cell(row=row, column=2).value: a.font = Font(bold=True, color="1F3864", size=11); a.fill = SUB
widths(ws8, [22, 130]); wrap(ws8)

out = "/home/user/Sports-betting-model/reports/cfb/CFB_FULL_SLATE_2026-09-26.xlsx"
wb.save(out)
print("wrote", out)
for s in wb.sheetnames: print(f"  {s:22} {wb[s].max_row-1:>3} rows")
print(f"\nBets: {len(bets)} | total {tot_u:.2f}u | storm-correlated {storm_u:.2f}u")
for b in bets:
    tier, _, _, gid, txt, typ, stake, conf, p, ev = b
    print(f"  T{tier} {R[gid]['a'][:16]:>16} @ {R[gid]['h'][:16]:<16} {txt[:44]:44} {stake:>10}u  P {'' if p is None else f'{p*100:4.1f}%':>6}  EV {'' if ev is None else f'{ev*100:+5.1f}%':>7}  {conf}")
