import json, sys
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

rows = json.load(open("/home/user/Sports-betting-model/reports/cfb/computed_2026-09-26.json"))
exec(open("/home/user/Sports-betting-model/reports/cfb/slate_data_2026-09-26.py").read())

HDR   = PatternFill("solid", fgColor="1F3864")
HDRF  = Font(bold=True, color="FFFFFF", size=10)
SUB   = PatternFill("solid", fgColor="D9E2F3")
GOOD  = PatternFill("solid", fgColor="C6EFCE")
WARN  = PatternFill("solid", fgColor="FFEB9C")
BAD   = PatternFill("solid", fgColor="FFC7CE")
MONO  = Font(name="Consolas", size=10)
THIN  = Border(*[Side(style="thin", color="BFBFBF")]*4)

def style_header(ws, ncols, row=1):
    for c in range(1, ncols+1):
        cell = ws.cell(row=row, column=c)
        cell.fill = HDR; cell.font = HDRF
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = ws.cell(row=row+1, column=1)
    ws.row_dimensions[row].height = 30

def autosize(ws, maxw=46):
    for col in ws.columns:
        L = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(L+2, 9), maxw)

wb = Workbook()

# ============ SHEET 1: full slate ============
ws = wb.active; ws.title = "Slate"
COLS = [
 ("Kick ET","et"), ("Away","away"), ("Home","home"),
 ("Home Spread","spread_home"), ("Total","total"), ("Favorite","fav"), ("Margin","margin"),
 ("PROJ SCORE (market-implied)","proj_score"), ("Proj Home","proj_home"), ("Proj Away","proj_away"),
 ("P(fav win) %","p_fav_win_spread"),
 ("ML fair home %","ml_fair_home_pct"), ("ML fair home (Am)","ml_fair_home_am"), ("ML hold %","ml_hold_pct"),
 ("Total fair OVER %","tot_fair_over_pct"), ("Total hold %","tot_hold_pct"),
 ("Spread fair home %","spr_fair_home_pct"), ("Spread hold %","spr_hold_pct"),
 ("Venue","venue"), ("HFA crowd","hfa_crowd"), ("HFA altitude","hfa_alt"), ("HFA total","hfa_total"),
 ("HFA vs flat 2.5","hfa_vs_flat25"),
 ("Weather","weather"), ("Confidence","confidence"), ("Edge type","edge_type"),
 ("BEST BET","best_bet"), ("Notes","notes"),
]
ws.append([c[0] for c in COLS])
for r in sorted(rows, key=lambda x: (-x["conf_score"], x["et"])):
    ws.append([r.get(k) for _, k in COLS])
style_header(ws, len(COLS))
conf_i = [k for _,k in COLS].index("confidence")+1
edge_i = [k for _,k in COLS].index("edge_type")+1
for row in range(2, ws.max_row+1):
    ws.cell(row=row, column=conf_i).fill = {"High":GOOD,"Medium":WARN,"Low":BAD}[ws.cell(row=row,column=conf_i).value]
    if ws.cell(row=row, column=edge_i).value != "None":
        ws.cell(row=row, column=edge_i).fill = SUB
    ws.cell(row=row, column=8).font = Font(bold=True, size=10)
autosize(ws)

# ============ SHEET 2: actionable ============
ws2 = wb.create_sheet("Actionable")
ws2.append(["Rank","Game","Kick ET","Edge type","The bet","Basis (why this is real)","Stake","Confidence","What kills it"])
ACTION = [
 (1,"Utah @ Iowa State","15:30","Shop + Weather","UNDER 48.5 (not 47.5)",
  "Books split: most 48.5, FanDuel 47.5. A full point of CFB total is ~4-5 cents of free equity. "
  "Independently: steady rain + afternoon showers, 64F, kickoff inside the rain window.","1u","Low-Med",
  "Rain clearing before 15:30 ET, or the number reaching 47 (nothing left)"),
 (2,"Oregon @ USC","19:30","Shop","If ORE: take -1.5, do NOT lay -3.5",
  "Spread ranges ORE -1.5 to -3.5 across books - widest disagreement on the board. Two points on a "
  "near-coinflip is worth more than any opinion I can form without a ratings spine.","1u","Medium",
  "All books converging to -3.5 before kick"),
 (3,"Colorado @ Baylor","12:00","Shop","If COL: take +10, if BAY: take -9.5",
  "Market split -9.5/-10. Pure number-shopping, no model needed.","1u","Medium","Books converging"),
 (4,"Oklahoma State @ West Virginia","19:00","Shop","If OKST: take +2.5 if it exists; pass at +2",
  "WVU -1.5 to -2 and totals 59.5 vs 61.5 across books. Context: OKST beat Oregon 39-31, and SP+ still "
  "rates Oregon 5th - a team that just beat a top-5 SP+ outfit is a 2-pt road dog.","1u","Medium",
  "Nothing better than +2 available; one result is not a spine"),
 (5,"Wisconsin @ Penn State","17:00","Weather","Lean UNDER 44.5 (-110), or pass",
  "N wind 10-20 gusting ~25 at Beaver Stadium. BUT 44.5 is already 7 pts below every comparable "
  "number on the board - the wind is largely in the price. Fair is exactly 50/50.","1u max","Low",
  "Gusts under 10 at kick makes 44.5 a live OVER"),
 (6,"FCS: Chattanooga @ The Citadel","14:00","Shop","Citadel +11.5 (not +10.5), or Chattanooga -10.5 (not -11.5)",
  "Two books are on different numbers: CHAT -11.5 (-111) and CIT +10.5 (-132). The market is 10.5/11.5, "
  "so one full point is available on whichever side you want. Pure shopping.","1u (FCS cap)","Low-Med",
  "Both books converging to 11"),
 (7,"FCS: Northern Arizona @ Montana State","15:00","Situational","No bet - but do NOT add altitude for Montana State",
  "My own venue engine initially credited MSU with +1.0 of altitude by defaulting NAU to sea level. NAU plays "
  "in Flagstaff at ~6,900ft - HIGHER than Bozeman's 4,820. Real differential is -2,080ft, so the altitude edge "
  "is ZERO. MSU gets crowd only (+3.4). Most models would add a point that does not exist.","-","Medium",
  "Nothing - this is a correction, not a bet"),
 (8,"Money games (Pitt/FSU/Duke/SMU)","various","Structural","Favorite 2H under / team-total under - NOT the side",
  "FBS-vs-FCS: big favorites empty the bench. Implied favorite team totals are Pitt 58.5, FSU 54.5, "
  "Duke 53.0, SMU 47.0. Those are 1st-half numbers being priced as full-game.","1u, thin data","Low",
  "A backup QB who can actually play, or a starter left in for 4 quarters"),
]
for a in ACTION: ws2.append(list(a))
style_header(ws2, 9)
for r in range(2, ws2.max_row+1):
    ws2.cell(row=r, column=5).font = Font(bold=True, size=10)
    for c in range(1,10): ws2.cell(row=r,column=c).alignment = Alignment(wrap_text=True, vertical="top")
ws2.column_dimensions["F"].width = 62; ws2.column_dimensions["I"].width = 40
ws2.column_dimensions["E"].width = 34; ws2.column_dimensions["B"].width = 30
for c in "ACDGH": ws2.column_dimensions[c].width = 13

# ============ SHEET 3: weather ============
ws3 = wb.create_sheet("Weather")
ws3.append(["Game","Kick ET","Total","Forecast (retrieved)","Read"])
WX_READ = {
 "Iowa State":"MATERIAL - rain in the kickoff window on the lowest total of the day. The one weather edge.",
 "Penn State":"MATERIAL - 10-20 gusting 25 suppresses deep passing and FG range. Largely priced already.",
 "Tennessee":"Non-factor. Ideal football weather.",
 "Ohio State":"Non-factor.",
 "Florida":"Non-factor. 82F is the mild version of Florida in September.",
 "West Virginia":"Non-factor. Light N wind on the highest total (61.5) - no suppression.",
 "LSU":"Non-factor. Night game, 66F, light/variable.",
}
for r in sorted(rows, key=lambda x: x["et"]):
    if r["weather"] != "not retrieved":
        ws3.append([f"{r['away']} @ {r['home']}", r["et"], r["total"], r["weather"], WX_READ.get(r["home"],"")])
ws3.append([]); ws3.append(["NOT RETRIEVED for the other 33 games","","","Open-Meteo and every weather-site fetch is blocked by this container's egress proxy; these 7 came from search snippets.",""])
style_header(ws3, 5)
ws3.column_dimensions["A"].width=32; ws3.column_dimensions["D"].width=58; ws3.column_dimensions["E"].width=62
for r in range(2, ws3.max_row+1):
    for c in range(1,6): ws3.cell(row=r,column=c).alignment=Alignment(wrap_text=True, vertical="top")

# ============ SHEET 4: venue / HFA ============
ws4 = wb.create_sheet("Home Field")
ws4.append(["Game","Venue","Crowd pts","Altitude pts","Total HFA","vs flat 2.5","Note"])
for r in sorted(rows, key=lambda x: -(x.get("hfa_total") or 0)):
    if r.get("venue"):
        ws4.append([f"{r['away']} @ {r['home']}", r["venue"], r["hfa_crowd"], r["hfa_alt"], r["hfa_total"], r["hfa_vs_flat25"], ""])
ws4.append([])
ws4.append(["Crowd and altitude are priced SEPARATELY on purpose - stacking them naively double-counts.","","","","","",""])
ws4.append(["Altitude is a FOURTH-QUARTER effect. Weight it to 2nd-half and live markets, not the full-game side.","","","","","",""])
ws4.append(["Tulane: this DB says Superdome, retrieved data says Yulman Stadium. DB may be stale - do not trust that row.","","","","","",""])
ws4.append(["Virginia, Cincinnati, Iowa State, Michigan St and others: no exact venue record, so NO number was invented.","","","","","",""])
style_header(ws4, 7)
ws4.column_dimensions["A"].width=34; ws4.column_dimensions["B"].width=30; ws4.column_dimensions["G"].width=30

# ============ SHEET 5: method + what's missing ============
ws5 = wb.create_sheet("Method & Gaps")
M = [
 ["WHAT THIS IS",""],
 ["Slate","Every FBS game on Sat 2026-09-26 for which a market could be retrieved: 40 games."],
 ["Retrieved [FACT]","Spreads, totals, moneylines, two-sided prices, weather. Source: web search, 2026-09-26."],
 ["Derived [MODEL]","Projected score, implied team totals, win probability, devigged fair prices, hold, HFA."],
 ["NOT present","Any independent power rating. No SP+, no FPI, no PPG model. Nothing here is estimated."],
 ["",""],
 ["HOW THE PROJECTION WORKS",""],
 ["Formula","fav = (total + |spread|)/2 ; dog = (total - |spread|)/2"],
 ["Meaning","This is the MARKET'S projection, recovered exactly from the spread and total."],
 ["Critical limit","Because it IS the market, it can never disagree with the market, so it cannot by itself"],
 ["","produce an edge. Any 'edge' from comparing it to the market is circular and fake."],
 ["Win probability","P(fav wins) from a normal on the spread, SD = 16.5 pts. That SD is a PRIOR, not a measurement."],
 ["",""],
 ["WHY THERE ARE NO MODEL-BASED PICKS",""],
 ["Rule (CLAUDE.md 3.4b)","College football spreads require SP+/FPI or equivalent. Without one, publish no side."],
 ["Why that rule exists","A points-per-game model on this sport once produced a pick'em against Miami -20.5."],
 ["","136 teams on wildly different schedules: two-game scoring averages carry almost no signal."],
 ["Proof it matters","Devigging the market then betting it returns NEGATIVE EV by construction:"],
 ["","Utah/ISU under at -106 = -4.63% EV. Wisconsin/PSU under at -110 = -4.55% EV. That IS the vig."],
 ["Conclusion","Every edge on the Actionable tab is a SHOPPING or WEATHER or STRUCTURAL edge."],
 ["","Not one is a model edge, because I have no model. That distinction is the whole point."],
 ["",""],
 ["CONFIDENCE SCORING (auditable)",""],
 ["+2","Two-sided prices retrieved (market can be devigged)"],
 ["+1","Weather retrieved"],
 ["+1","No book disagreement noted"],
 ["-1","Book disagreement noted (line varies across books)"],
 ["-2","FBS-vs-FCS money game (data genuinely thin)"],
 ["High / Medium / Low","score >= 3 / 1-2 / <= 0"],
 ["",""],
 ["GAPS - STATED, NOT PAPERED OVER",""],
 ["FBS games with no market","Gardner-Webb @ Marshall, Kennesaw St @ Arkansas State, FAU @ ULM, UNLV @ Akron,"],
 ["","Houston Christian @ Georgia Southern. Listed, never estimated."],
 ["The entire FCS slate","~65 games. Search could not return a reliable FCS game list, and most FCS games"],
 ["","carry no posted market. Nothing invented to fill it."],
 ["Weather","7 of 40 games. Open-Meteo and all weather-site fetches are proxy-blocked here."],
 ["Injuries / QB status","NOT retrieved for any game. In CFB there is no mandated injury report, and QB status is"],
 ["","the single highest-value input in the sport - worth 4-7 pts with a good backup, 10-14 with a freshman."],
 ["","Treat every number here as PROVISIONAL until you check today's inactives."],
 ["Line shopping","Mostly one book per game. Where a range was found it is on the Actionable tab."],
 ["","Per CLAUDE.md 3.3, a single book's price means the edge is UNCONFIRMED."],
 ["",""],
 ["HOW TO MAKE THIS COMPLETE",""],
 ["Set CFBD_API_KEY","Free at collegefootballdata.com/key. Gives SP+ for all 138 FBS AND all FCS teams, the full"],
 ["","two-division slate, and per-provider lines. That single key turns this into the real thing."],
]
for r in M: ws5.append(r)
style_header(ws5, 2)
ws5.column_dimensions["A"].width = 30; ws5.column_dimensions["B"].width = 112
for r in range(2, ws5.max_row+1):
    a = ws5.cell(row=r, column=1)
    if a.value and not ws5.cell(row=r,column=2).value:
        a.font = Font(bold=True, color="1F3864", size=11); a.fill = SUB
    ws5.cell(row=r,column=2).alignment = Alignment(wrap_text=True, vertical="top")


# ============ SHEET: FCS ============
import json as _json
fcs = _json.load(open("/home/user/Sports-betting-model/reports/cfb/computed_fcs_2026-09-26.json"))
exec(open("/home/user/Sports-betting-model/reports/cfb/slate_fcs_2026-09-26.py").read())
ws6 = wb.create_sheet("FCS")
FC = [("Kick ET","et"),("Away","away"),("Home","home"),("Conf","conf"),
      ("Home Spread","spread_home"),("Total","total"),("Favorite","fav"),("Margin","margin"),
      ("PROJ SCORE (market-implied)","proj_score"),("Proj Home","proj_home"),("Proj Away","proj_away"),
      ("P(fav win) %","p_fav_win"),("ML fair home %","ml_fair_home_pct"),("ML fair home (Am)","ml_fair_home_am"),
      ("ML hold %","ml_hold_pct"),("Total fair OVER %","tot_fair_over_pct"),("Total hold %","tot_hold_pct"),
      ("Venue","venue"),("HFA crowd","hfa_crowd"),("HFA altitude","hfa_alt"),("HFA total","hfa_total"),
      ("Confidence","confidence"),("Edge type","edge_type"),("BEST BET","best_bet"),
      ("Stake cap","stake_cap"),("Notes","notes")]
ws6.append([c[0] for c in FC])
for r in sorted(fcs, key=lambda x:(-x["conf_score"], x["et"])):
    ws6.append([r.get(k) for _,k in FC])
style_header(ws6, len(FC))
ci = [k for _,k in FC].index("confidence")+1
for row in range(2, ws6.max_row+1):
    val = ws6.cell(row=row, column=ci).value
    if val: ws6.cell(row=row, column=ci).fill = {"High":GOOD,"Medium":WARN,"Low":BAD}[val]
    ws6.cell(row=row, column=9).font = Font(bold=True, size=10)
ws6.append([])
ws6.append(["IDENTIFIED BUT NO MARKET RETRIEVABLE - listed, never estimated:"])
for a_,h_,c_ in FCS_NO_MARKET:
    ws6.append(["", a_, h_, c_, None, None, None, None, "no market retrieved"])
ws6.append([])
ws6.append(["FBS-vs-FCS money games are on the Slate tab: " + "; ".join(MONEY_GAMES)])
ws6.append(["FCS stakes are capped at 1u per skills/sport-fcs.md - 63 scholarships vs 85, and the data is genuinely thin."])
ws6.append(["Ivy and Pioneer leagues are NON-SCHOLARSHIP and are effectively a different sport. Princeton/Dartmouth/Penn/Georgetown games carry that caveat."])
ws6.append(["Margin SD used for FCS win probability: 17.5 pts (a PRIOR, wider than the 16.5 used for FBS - FCS talent spread is larger)."])
autosize(ws6)

out = "/home/user/Sports-betting-model/reports/cfb/CFB_Slate_2026-09-26.xlsx"
wb.save(out)
print("wrote", out)
print("sheets:", wb.sheetnames)
print("slate rows:", len(rows))
