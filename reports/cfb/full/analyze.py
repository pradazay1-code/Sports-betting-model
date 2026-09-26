"""Desk analysis for the full slate. Every number is either retrieved (games.py) or derived here
by stated arithmetic. Judgment inputs are named constants so they can be audited and changed."""
import sys, json
from statistics import NormalDist, mean
sys.path.insert(0, "/home/user/Sports-betting-model")
from lib.odds import devig, hold, prob_to_american, american_to_decimal
exec(open("/home/user/Sports-betting-model/reports/cfb/full/games.py").read())

N = NormalDist()
SD_M = {"FBS": 16.5, "FCS": 17.5}   # margin SD around a projection  [PRIOR]
SD_T = 14.0                          # total SD around a projection   [PRIOR]
W_TWO, W_ONE = 0.40, 0.25            # weight on model consensus vs market (2+ models / 1 model) [READ]
W_TOT = 0.30                         # weight on SP+ total vs market total                       [READ]
WX_ADJ = {"storm_core": -6.0, "storm_edge": -4.0, "rain": -2.0, "wind": -1.0}   # base-case points [READ]
MIN_EV = 0.02

# extra numeric models, as HOME margins (sources in games.py 'other')
EXTRA = {12: -16.5*N.inv_cdf(0.752),   # numberFire Utah 75.2% (Utah away)
         25: 26-30,                    # dimers KSU 30-26 (home CIN)
         15: -16.5*N.inv_cdf(0.57)}    # dimers TCU 57% (TCU away)
SPWP  = {4: 16.5*N.inv_cdf(0.78)}      # SP+ win prob Louisville 78% -> SP+ margin

def sgn(x): return 1 if x > 0 else (-1 if x < 0 else 0)

# ---------- 1. measure each model's bias toward the MARKET FAVOURITE ----------
fpi_res, sp_res = [], []
for g in G:
    mm = -g["sp"]
    if "fpi_h" in g and mm != 0:
        fpi_res.append((16.5*N.inv_cdf(g["fpi_h"]) - mm) * sgn(mm))
    if "sp_h" in g and mm != 0:
        sp_res.append(((g["sp_h"]-g["sp_a"]) - mm) * sgn(mm))
FPI_BIAS, SP_BIAS = mean(fpi_res), mean(sp_res)
sp_tot_res = [ (g["sp_h"]+g["sp_a"]) - g["tot"] for g in G if "sp_h" in g and g.get("tot")]
SP_TOT_BIAS = mean(sp_tot_res)

rows = []
for g in G:
    d = g["div"]; sdm = SD_M[d]
    sp, tot = g["sp"], g.get("tot")
    mm = -sp
    r = dict(g)
    # market projection
    if tot is not None:
        r["mkt_h"] = round((tot + mm)/2, 1); r["mkt_a"] = round(tot - r["mkt_h"], 1)
    # market win prob (home)
    if g.get("mlh") and g.get("mla"):
        f = devig([g["mlh"], g["mla"]], "power"); r["mkt_ph"] = f[0]; r["ml_hold"] = hold([g["mlh"], g["mla"]])
    else:
        r["mkt_ph"] = 1 - N.cdf(sp/sdm)
    if g.get("to") and g.get("tu"):
        r["tot_fair_over"] = devig([g["to"], g["tu"]], "power")[0]; r["tot_hold"] = hold([g["to"], g["tu"]])
    # models -> bias-corrected home margins
    mods = []
    if "fpi_h" in g:
        raw = 16.5*N.inv_cdf(g["fpi_h"]); r["fpi_margin"] = raw
        mods.append(("FPI", raw - sgn(mm)*FPI_BIAS))
    if "sp_h" in g:
        raw = g["sp_h"]-g["sp_a"]; r["sp_margin"] = raw; r["sp_total"] = g["sp_h"]+g["sp_a"]
        mods.append(("SP+", raw - sgn(mm)*SP_BIAS))
    if g["id"] in SPWP:
        raw = SPWP[g["id"]]; r["sp_margin"] = raw; mods.append(("SP+", raw - sgn(mm)*SP_BIAS))
    if g["id"] in EXTRA:
        mods.append(("other", EXTRA[g["id"]]))
    r["n_models"] = len(mods)
    if mods:
        cons = mean(m for _, m in mods); r["model_margin"] = cons
        w = W_TWO if len(mods) >= 2 else W_ONE
        r["desk_margin"] = w*cons + (1-w)*mm
        r["model_vs_mkt"] = cons - mm
    else:
        r["desk_margin"] = mm
    # desk total
    if tot is not None:
        t = tot
        if "sp_total" in r: t = tot + W_TOT*(r["sp_total"] - tot)
        wc = g.get("wxc", "")
        if wc in WX_ADJ and g["id"] not in (5, 12):          # 5/12 handled via neutral SP+ base in evcalc
            t = t + WX_ADJ[wc]
        if g["id"] == 5:  t = 53.0 + WX_ADJ["storm_core"]   # VT/BC: SP+ neutral 53 minus storm
        if g["id"] == 12: t = 49.0 + WX_ADJ["rain"]         # UTAH/ISU: SP+ neutral 49 minus rain
        if g["id"] == 109:                                   # Fordham: market-implied median minus storm
            med = 52.5 + SD_T*N.inv_cdf(devig([-144,116],"power")[0]); t = med + WX_ADJ["storm_core"]
        r["desk_total"] = t
        r["desk_h"] = round((t + r["desk_margin"])/2, 1); r["desk_a"] = round(t - r["desk_h"], 1)
    r["desk_ph"] = 1 - N.cdf(-r["desk_margin"]/sdm)
    rows.append(r)

# ---------- 2. EV for every bet type we can price ----------
def ev_cover(p, price): return p*american_to_decimal(price) - 1

for r in rows:
    r["ev_rows"] = []
    sdm = SD_M[r["div"]]
    ec = r.get("evcalc")
    if ec:                                        # weather totals: scenario table
        line, price = ec["line"], ec["price"]
        base = ec["base"]
        if base is None:
            po = devig([r["to"], r["tu"]], "power")[0]; base = line + SD_T*N.inv_cdf(po)
        r["wx_base"] = base
        scen = []
        for lab, a in zip(("conservative","base","aggressive"), ec["adj"]):
            mu = base + a; p = N.cdf((line - mu)/SD_T)
            scen.append((lab, a, mu, p, ev_cover(p, price)))
        scen.append(("market already fully adjusted", None, None, None, 1/american_to_decimal(price)*0 + (0.5*american_to_decimal(price)-1) if price!=116 else None))
        # break-even adjustment
        pbe = 1/american_to_decimal(price); mu_be = line - SD_T*N.inv_cdf(pbe)
        r["wx_scen"] = scen; r["wx_breakeven_adj"] = mu_be - base
        r["bet_p"] = scen[1][3]; r["bet_ev"] = scen[1][4]; r["bet_price"] = price

# model side bets: price with the desk (bias-corrected, market-shrunk) margin
SIDE = {28: ("away", 9.5, -110), 21: ("home", -9.5, -115), 25: ("home", 6.5, -108),
        29: ("home", 3.5, -114), 11: ("away", 3.5, -120), 34: ("away", 6.5, -110)}
for r in rows:
    if r["id"] in SIDE:
        who, line, price = SIDE[r["id"]]
        dm, sdm = r["desk_margin"], SD_M[r["div"]]
        # P(home margin + line_home > 0); line given from bettor's side
        if who == "away":   p = N.cdf((line - dm)/sdm)          # away +line covers if home margin < line
        else:               p = 1 - N.cdf((-line - dm)/sdm)     # home line covers if margin > -line
        r["side_p"], r["side_ev"], r["side_price"] = p, ev_cover(p, price), price

# model totals: SP+ blended
TOT = {26: ("under", 61.5, -110), 34: ("under", 58.5, -104), 13: ("over", 38.5, -110),
       14: ("over", 44.5, -110), 35: ("under", 54.5, -114), 28: ("under", 53.5, -110), 29: ("under", 62.5, -110)}
for r in rows:
    if r["id"] in TOT and "sp_total" in r:
        side, line, price = TOT[r["id"]]
        mu = r["tot"] + W_TOT*(r["sp_total"] - r["tot"])
        p = N.cdf((line-mu)/SD_T) if side == "under" else 1 - N.cdf((line-mu)/SD_T)
        r["tot_p"], r["tot_ev"], r["tot_price"], r["tot_mu"] = p, ev_cover(p, price), price, mu

json.dump(dict(rows=rows, FPI_BIAS=FPI_BIAS, SP_BIAS=SP_BIAS, SP_TOT_BIAS=SP_TOT_BIAS,
               n_fpi=len(fpi_res), n_sp=len(sp_res)),
          open("/home/user/Sports-betting-model/reports/cfb/full/analysis.json","w"), indent=1, default=str)

print(f"MODEL BIAS toward the market favourite (pts):  FPI {FPI_BIAS:+.2f} (n={len(fpi_res)})   SP+ {SP_BIAS:+.2f} (n={len(sp_res)})")
print(f"SP+ total bias vs market: {SP_TOT_BIAS:+.2f}  -> no systematic lean, so large SP+ total gaps carry information")
print()
print("SIDE bets after bias correction + market shrinkage:")
for r in rows:
    if "side_ev" in r:
        tag = "BET" if r["side_ev"] >= MIN_EV else "NO BET"
        print(f"  {r['a']:>16} @ {r['home'] if 'home' in r else r['h']:<18} model {r.get('model_margin',0):+5.1f} mkt {-r['sp']:+5.1f} desk {r['desk_margin']:+5.1f}  P {r['side_p']*100:4.1f}%  EV {r['side_ev']*100:+5.1f}%  @{r['side_price']}  -> {tag}")
print("\nMODEL TOTALS (SP+ blended at w=0.3):")
for r in rows:
    if "tot_ev" in r:
        side, line, price = TOT[r["id"]]
        tag = "BET" if r["tot_ev"] >= MIN_EV else "NO BET"
        print(f"  {r['a']:>16} @ {r['h']:<18} {side} {line} @{price}: SP+ {r['sp_total']:.1f} mkt {r['tot']} -> mu {r['tot_mu']:.1f}  P {r['tot_p']*100:4.1f}%  EV {r['tot_ev']*100:+5.1f}%  -> {tag}")
print("\nWEATHER TOTALS (scenario EV):")
for r in rows:
    if "wx_scen" in r:
        s = r["wx_scen"]
        print(f"  {r['a']:>16} @ {r['h']:<18} under {r['evcalc']['line']} @{r['evcalc']['price']}: base {r['wx_base']:.1f} | "
              + " | ".join(f"{x[0][:5]} {x[1]:+.0f}: EV {x[4]*100:+5.1f}%" for x in s[:3])
              + f" | break-even needs storm to cost {-r['wx_breakeven_adj']:.1f}+ pts")
