"""Compute market-implied projections + build the spreadsheet for 2026-09-26 CFB.

Every number here is either RETRIEVED (market/weather) or DERIVED from retrieved
market data by explicit arithmetic. Nothing is estimated from a model I don't have.

The projection is the MARKET'S projection: a spread and a total jointly imply a
score. That is legitimate and reproducible. It is NOT an independent number, so
it cannot by itself produce an edge -- see the EDGE_TYPE column.
"""
import sys, math, os
sys.path.insert(0, "/home/user/Sports-betting-model")
from lib.odds import devig, hold, prob_to_american, implied_prob
from lib.venues import home_edge, find as find_venue

exec(open("/home/user/Sports-betting-model/reports/cfb/slate_data_2026-09-26.py").read())

CFB_MARGIN_SD = 16.5   # prior, not a measurement (matches web/lib/ratings.ts)

def ncdf(z): return 0.5 * (1 + math.erf(z / math.sqrt(2)))

rows = []
for g in G:
    sp, tot = g.get("sp"), g.get("tot")
    a, h = g["a"], g["h"]
    r = dict(away=a, home=h, et=g["et"], spread_home=sp, total=tot)

    # --- market-implied projected score ---
    if sp is not None and tot is not None:
        hs = (tot - sp) / 2.0
        as_ = (tot + sp) / 2.0
        # Round ONE side and derive the other, so proj_home + proj_away == total exactly.
        # Rounding both independently left 9 rows off by 0.1, which is the kind of
        # thing that makes a reader rightly distrust every other number on the sheet.
        r["proj_home"] = round(hs, 1)
        r["proj_away"] = round(tot - r["proj_home"], 1)
        r["proj_score"] = f"{h} {r['proj_home']:.1f} - {a} {r['proj_away']:.1f}"
        r["fav"] = h if sp < 0 else (a if sp > 0 else "pick")
        r["margin"] = round(abs(sp), 1)
        # win prob from the spread
        pw_home = 1 - ncdf(sp / CFB_MARGIN_SD)
        r["p_home_win_spread"] = round(pw_home * 100, 1)
        r["p_fav_win_spread"] = round((pw_home if sp < 0 else 1 - pw_home) * 100, 1)

    # --- devigs where two-sided prices exist ---
    if g.get("mlh") and g.get("mla"):
        f = devig([g["mlh"], g["mla"]], "power")
        r["ml_fair_home_pct"] = round(f[0] * 100, 2)
        r["ml_fair_home_am"] = round(prob_to_american(f[0]))
        r["ml_hold_pct"] = round(hold([g["mlh"], g["mla"]]) * 100, 2)
    if g.get("to") and g.get("tu"):
        f = devig([g["to"], g["tu"]], "power")
        r["tot_fair_over_pct"] = round(f[0] * 100, 2)
        r["tot_hold_pct"] = round(hold([g["to"], g["tu"]]) * 100, 2)
    if g.get("sph") and g.get("spa"):
        f = devig([g["sph"], g["spa"]], "power")
        r["spr_fair_home_pct"] = round(f[0] * 100, 2)
        r["spr_hold_pct"] = round(hold([g["sph"], g["spa"]]) * 100, 2)

    # --- venue layer (only where the venue is in the DB) ---
    # STRICT match only. A fuzzy match put "Virginia" in Virginia Tech's Lane
    # Stadium, which is exactly the kind of silent wrong number that ruins a card.
    v = find_venue(h)
    if v and v.team.strip().lower() != h.strip().lower():
        v = None
        r["venue_note"] = f"no exact venue record for '{h}' (fuzzy match to '{find_venue(h).team}' rejected)"
    if v:
        e = home_edge(h, a)
        r["venue"] = e["venue"]
        r["hfa_crowd"] = e["crowd_points"]
        r["hfa_alt"] = e["altitude"]["points"]
        r["hfa_total"] = round(e["total_points"], 2)
        r["hfa_vs_flat25"] = round(e["vs_baseline"], 2)
    r["weather"] = g.get("wx", "not retrieved")
    r["notes"] = g.get("n", "")
    r["fcs_opp"] = bool(g.get("fcsopp"))

    # --- confidence: objective scoring, stated so it is auditable ---
    s = 0
    if r.get("tot_hold_pct") or r.get("spr_hold_pct") or r.get("ml_hold_pct"): s += 2
    if g.get("wx"): s += 1
    disagree = any(k in (g.get("n") or "") for k in ["alt ", "split", "across books", "-10.5", "to -3.5", "48.5-50.5", "44.5-45.5", "47.5/48.5", "52-53.5", "48.5-50.5"])
    if not disagree: s += 1
    if g.get("fcsopp"): s -= 2
    if disagree: s -= 1
    r["conf_score"] = s
    r["confidence"] = "High" if s >= 3 else ("Medium" if s >= 1 else "Low")

    # --- best bet: typed, so the basis is never ambiguous ---
    if g.get("fcsopp"):
        ft = round((tot + abs(sp)) / 2.0, 1)
        r["edge_type"] = "Structural"
        r["best_bet"] = f"Favorite 2H under / team-total under (fav implied {ft}); NOT the side"
    elif disagree:
        r["edge_type"] = "Shop"
        r["best_bet"] = "Books disagree - take the better number, no model needed"
    elif "RAIN" in (g.get("wx") or "") or "GUSTS" in (g.get("wx") or ""):
        r["edge_type"] = "Weather"
        r["best_bet"] = "Under lean on sourced weather; cap 1u"
    else:
        r["edge_type"] = "None"
        r["best_bet"] = "No bet - no independent number vs a fairly priced market"
    rows.append(r)

# ---------- console summary ----------
print(f"{'game':42} {'proj score':26} {'sp':>6} {'tot':>5} {'P(fav)':>7} {'conf':>6} {'edge':>10}")
print("-"*112)
for r in sorted(rows, key=lambda x: (-x["conf_score"], x["home"])):
    g = f"{r['away']} @ {r['home']}"
    print(f"{g:42} {r.get('proj_score','n/a'):26} {r['spread_home'] if r['spread_home'] is not None else 0:>6} "
          f"{r['total'] or 0:>5} {r.get('p_fav_win_spread','-'):>7} {r['confidence']:>6} {r['edge_type']:>10}")

print()
print("Venue-DB games (home-field priced, not flat 2.5):")
for r in rows:
    if r.get("venue"):
        print(f"  {r['away']} @ {r['home']:18} {r['venue']:28} crowd {r['hfa_crowd']:+.1f}  alt {r['hfa_alt']:+.1f}  tot {r['hfa_total']:+.2f}  vs flat2.5 {r['hfa_vs_flat25']:+.2f}")

import json
json.dump(rows, open("/home/user/Sports-betting-model/reports/cfb/computed_2026-09-26.json","w"), indent=1)
print(f"\n{len(rows)} rows computed -> computed_2026-09-26.json")
