import sys, math, json
sys.path.insert(0, "/home/user/Sports-betting-model")
from lib.odds import devig, hold, prob_to_american
from lib.venues import home_edge, find

exec(open("/home/user/Sports-betting-model/reports/cfb/slate_fcs_2026-09-26.py").read())
FCS_MARGIN_SD = 17.5   # prior; FCS runs wider than FBS (talent spread is larger)

def ncdf(z): return 0.5*(1+math.erf(z/math.sqrt(2)))

rows=[]
for g in FCS:
    sp, tot, a, h = g.get("sp"), g.get("tot"), g["a"], g["h"]
    r = dict(away=a, home=h, et=g["et"], conf=g.get("conf",""), spread_home=sp, total=tot)
    if sp is not None and tot is not None:
        hs = round((tot - sp)/2.0, 1); as_ = round(tot - hs, 1)
        r.update(proj_home=hs, proj_away=as_, proj_score=f"{h} {hs:.1f} - {a} {as_:.1f}",
                 fav=h if sp<0 else a, margin=round(abs(sp),1))
        pwh = 1-ncdf(sp/FCS_MARGIN_SD)
        r["p_fav_win"] = round((pwh if sp<0 else 1-pwh)*100, 1)
    elif sp is not None:
        r["proj_score"] = "total not retrieved - no score projection published"
        r["fav"] = h if sp<0 else a; r["margin"] = round(abs(sp),1)
        pwh = 1-ncdf(sp/FCS_MARGIN_SD); r["p_fav_win"] = round((pwh if sp<0 else 1-pwh)*100,1)
    if g.get("mlh") and g.get("mla"):
        f = devig([g["mlh"], g["mla"]], "power")
        r["ml_fair_home_pct"]=round(f[0]*100,2); r["ml_fair_home_am"]=round(prob_to_american(f[0]))
        r["ml_hold_pct"]=round(hold([g["mlh"],g["mla"]])*100,2)
    if g.get("to") and g.get("tu"):
        f = devig([g["to"], g["tu"]], "power")
        r["tot_fair_over_pct"]=round(f[0]*100,2); r["tot_hold_pct"]=round(hold([g["to"],g["tu"]])*100,2)
    v = find(h)
    if v and v.team.strip().lower()==h.strip().lower():
        e = home_edge(h, a, fcs=True)
        r.update(venue=e["venue"], hfa_crowd=e["crowd_points"], hfa_alt=e["altitude"]["points"],
                 hfa_total=round(e["total_points"],2), hfa_vs_base=round(e["vs_baseline"],2))
    r["notes"]=g.get("n","")
    # confidence
    s=0
    if r.get("tot_hold_pct") or r.get("ml_hold_pct"): s+=2
    if tot is not None: s+=1
    if "SHOPPABLE" in (g.get("n") or "") or "LOPSIDED" in (g.get("n") or ""): s-=1
    s -= 1   # FCS blanket: data is genuinely thinner. Per sport-fcs.md, cap stakes at 1u.
    r["conf_score"]=s
    r["confidence"]="High" if s>=3 else ("Medium" if s>=1 else "Low")
    # typed edge
    n=(g.get("n") or "")
    if "SHOPPABLE" in n: r["edge_type"]="Shop"; r["best_bet"]="Take Citadel +11.5 (not +10.5) or Chattanooga -10.5 (not -11.5)"
    elif "LOPSIDED" in n:
        # I first read the +116 under as value because it is plus money. It is not.
        # Devigged, the under is FAIR at +130 and you are offered +116: -6.10% EV.
        # Lopsided juice reflects a real market lean, it is not a gift.
        r["edge_type"]="None"
        r["best_bet"]="No bet - under devigs FAIR at +130, offered +116 = -6.1% EV. Plus money is not value."
    elif "HIGHEST TOTAL" in n: r["edge_type"]="Flag"; r["best_bet"]="No bet - 65.5 is the day's extreme; needs a number I don't have"
    elif "neutralised" in n: r["edge_type"]="Situational"; r["best_bet"]="No bet - but do NOT add altitude for MSU here"
    else: r["edge_type"]="None"; r["best_bet"]="No bet - no independent number"
    r["stake_cap"]="1u (FCS data thin per sport-fcs.md)"
    rows.append(r)

print(f"{'game':46} {'conf':13} {'proj score':30} {'sp':>6} {'tot':>5} {'P(fav)':>7} {'conf':>6}")
print("-"*122)
for r in sorted(rows, key=lambda x:(-x["conf_score"], x["et"])):
    print(f"{r['away']+' @ '+r['home']:46} {r['conf']:13} {str(r.get('proj_score'))[:30]:30} "
          f"{r['spread_home'] if r['spread_home'] is not None else 0:>6} {r['total'] or 0:>5} {r.get('p_fav_win','-'):>7} {r['confidence']:>6}")
print("\nFCS venue-DB (altitude priced on the DIFFERENTIAL):")
for r in rows:
    if r.get("venue"):
        print(f"  {r['away']} @ {r['home']:20} {r['venue']:28} crowd {r['hfa_crowd']:+.1f} alt {r['hfa_alt']:+.1f} tot {r['hfa_total']:+.2f} vs FCS base 3.0 {r['hfa_vs_base']:+.2f}")
json.dump(rows, open("/home/user/Sports-betting-model/reports/cfb/computed_fcs_2026-09-26.json","w"), indent=1)
print(f"\n{len(rows)} FCS rows computed")
