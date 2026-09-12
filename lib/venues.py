"""
College football venue database — home-field advantage, altitude, and weather geo.

Home field advantage in college football is NOT a constant the way it nearly is
in the NFL. The spread between the loudest, highest, hardest place to play and a
half-empty MAC stadium on a Tuesday is worth **four points or more**, and most
public models apply a flat 2.5 to everything. That gap is the single most
reliably mispriced situational factor in the sport.

Two things drive it and they are independent:

  1. **Crowd / venue** — noise, proximity, false-start and delay-of-game rates
     for visiting offenses, officiating drift.
  2. **Altitude** — a physiological effect that shows up in the fourth quarter,
     not the first. It is cumulative fatigue, not an early-game edge.

`hfa` below is in POINTS, the venue's crowd/environment edge only. Altitude is
carried separately in `altitude_ft` and priced with `altitude_edge()`, because
stacking them naively double-counts.

Numbers are calibrated to a league-average FBS home edge of ~2.5 points. They
are a prior to reason from, not a measurement — treat them as [READ], adjust for
the specific game, and say so.

CLI:
    python3 -m lib.venues lookup "Death Valley"
    python3 -m lib.venues team LSU
    python3 -m lib.venues altitude
    python3 -m lib.venues edge --home Wyoming --away Hawaii
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Iterable

#: League-average FBS home-field advantage, in points. Has drifted DOWN over the
#: last decade (better travel, more neutral officiating, portal-era parity).
FBS_BASELINE_HFA = 2.5

#: FCS baseline. Higher than FBS: smaller venues sit closer to the field, crowds
#: are more partisan, and visiting teams travel worse (buses, not charters).
FCS_BASELINE_HFA = 3.0


@dataclass(frozen=True)
class Venue:
    name: str
    team: str
    lat: float
    lon: float
    altitude_ft: int
    capacity: int
    surface: str          # grass | turf
    roof: str             # open | dome | retractable
    hfa: float            # crowd/environment points, EXCLUDING altitude
    note: str = ""


# ---------------------------------------------------------------------------
# The venues that actually move a number.
# ---------------------------------------------------------------------------

VENUES: tuple[Venue, ...] = (
    # --- Elite crowd environments (hfa 3.5+) ---------------------------------
    Venue("Tiger Stadium (Death Valley)", "LSU", 30.4118, -91.1836, 56, 102321, "grass", "open", 4.0,
          "Night games are a separate animal - add ~0.5 more after dark. Historically the "
          "single toughest road environment in the sport."),
    Venue("Autzen Stadium", "Oregon", 44.0584, -123.0684, 400, 54000, "turf", "open", 3.8,
          "Loudest per capita in the country. Bowl design traps noise - false-start rates spike."),
    Venue("Kyle Field", "Texas A&M", 30.6100, -96.3400, 350, 102733, "grass", "open", 3.8,
          "12th Man tradition, 100k+ standing. Third-down noise is the mechanism."),
    Venue("Beaver Stadium", "Penn State", 40.8122, -77.8560, 1180, 106572, "grass", "open", 3.7,
          "Whiteout games specifically are worth ~1 extra point. Not all games are whiteouts."),
    Venue("Neyland Stadium", "Tennessee", 35.9550, -83.9250, 886, 101915, "grass", "open", 3.6,
          "Checkerboard + Vol Navy. Enormous when Tennessee is good; fades when they aren't."),
    Venue("Bryant-Denny Stadium", "Alabama", 33.2083, -87.5504, 230, 100077, "grass", "open", 3.5,
          "Crowd is big but corporate/older; talent gap usually does the work, not the noise."),
    Venue("Ben Hill Griffin (The Swamp)", "Florida", 29.6499, -82.3486, 82, 88548, "grass", "open", 3.6,
          "Heat and humidity in September is a real fourth-quarter factor for northern teams."),
    Venue("Ohio Stadium", "Ohio State", 40.0017, -83.0197, 725, 102780, "turf", "open", 3.5),
    Venue("Camp Randall Stadium", "Wisconsin", 43.0700, -89.4126, 869, 75822, "turf", "open", 3.4,
          "Jump Around between 3rd and 4th quarters is genuinely disruptive."),
    Venue("Sanford Stadium", "Georgia", 33.9500, -83.3733, 640, 92746, "grass", "open", 3.5),
    Venue("Memorial Stadium (Death Valley)", "Clemson", 34.6787, -82.8432, 800, 81500, "grass", "open", 3.5),
    Venue("Jordan-Hare Stadium", "Auburn", 32.6025, -85.4894, 709, 88043, "grass", "open", 3.4),
    Venue("Doak Campbell Stadium", "Florida State", 30.4380, -84.3045, 190, 79560, "grass", "open", 3.3),
    Venue("Husky Stadium", "Washington", 47.6503, -122.3016, 30, 70138, "turf", "open", 3.4,
          "Open end faces the lake; noise reflects off the covered sides."),
    Venue("Williams-Brice Stadium", "South Carolina", 33.9731, -81.0194, 240, 77559, "grass", "open", 3.3,
          "Sandstorm entrance. Underrated environment."),
    Venue("Kinnick Stadium", "Iowa", 41.6586, -91.5513, 690, 69250, "turf", "open", 3.3),
    Venue("Michigan Stadium", "Michigan", 42.2658, -83.7487, 860, 107601, "turf", "open", 3.2,
          "Largest capacity in the country but a famously quiet bowl - big is not loud."),
    Venue("Lane Stadium", "Virginia Tech", 37.2199, -80.4185, 2080, 65632, "grass", "open", 3.4,
          "Enter Sandman entrance. Mild elevation on top of a real crowd."),

    # --- Altitude venues (the physiological edge) ----------------------------
    Venue("War Memorial Stadium", "Wyoming", 41.3114, -105.5690, 7220, 29181, "turf", "open", 3.0,
          "HIGHEST stadium in Division I. Sea-level teams fade badly in the 4th. "
          "Also brutally cold and windy late in the year."),
    Venue("Falcon Stadium", "Air Force", 38.9970, -104.8434, 6621, 46692, "turf", "open", 2.8,
          "Altitude plus a triple-option-style clock-control scheme compounds the fatigue."),
    Venue("Folsom Field", "Colorado", 40.0096, -105.2669, 5360, 50183, "turf", "open", 3.0),
    Venue("Maverik Stadium", "Utah State", 41.7518, -111.8125, 4775, 25100, "turf", "open", 2.8),
    Venue("Rice-Eccles Stadium", "Utah", 40.7600, -111.8488, 4637, 51444, "turf", "open", 3.3),
    Venue("Mackay Stadium", "Nevada", 39.5455, -119.8160, 4600, 27000, "turf", "open", 2.5),
    Venue("Hughes Stadium / Canvas", "Colorado State", 40.5734, -105.0866, 5003, 41200, "turf", "open", 2.6),
    Venue("Dreamstyle Stadium", "New Mexico", 35.0670, -106.6250, 5157, 39224, "turf", "open", 2.6),
    Venue("Albertsons Stadium", "Boise State", 43.6027, -116.1969, 2730, 36387, "turf", "open", 3.4,
          "The blue turf is a genuine visual-adaptation edge, not just a gimmick. "
          "Boise's home record is historically absurd."),

    # --- Domes and controlled environments -----------------------------------
    Venue("Carrier Dome / JMA Wireless", "Syracuse", 43.0362, -76.1363, 400, 49250, "turf", "dome", 3.2,
          "Dome noise is trapped; no weather ever. Kills weather-based unders."),
    Venue("Alamodome", "UTSA", 29.4169, -98.4791, 650, 65000, "turf", "dome", 2.0,
          "Huge dome, usually sparse. Capacity misleads - low real HFA."),
    Venue("Superdome", "Tulane", 29.9511, -90.0812, 3, 73208, "turf", "dome", 2.2),
    Venue("Ford Field", "Neutral", 42.3400, -83.0456, 600, 65000, "turf", "dome", 0.0, "Neutral site."),
    Venue("Mercedes-Benz Stadium", "Neutral", 33.7554, -84.4008, 1050, 71000, "turf", "retractable", 0.0,
          "Neutral site - CFP and kickoff games."),
    Venue("AT&T Stadium", "Neutral", 32.7473, -97.0945, 550, 80000, "turf", "retractable", 0.0, "Neutral site."),

    # --- Travel / isolation extremes ----------------------------------------
    Venue("Clarence T.C. Ching Complex", "Hawaii", 21.2969, -157.8171, 20, 15000, "turf", "open", 3.5,
          "The TRAVEL is the edge, not the crowd. Mainland teams cross 5-6 time zones "
          "and play at a body-clock hour that is brutal. The return trip wrecks the "
          "following week too - fade Hawaii road opponents the NEXT week as well."),
    Venue("Rentschler Field", "UConn", 41.7614, -72.6432, 40, 40000, "grass", "open", 1.8),

    # --- FCS venues, added because an FCS visitor defaulting to sea level
    #     silently overstates every altitude edge. Several FCS programs play
    #     HIGHER than the FBS teams they visit. ----------------------------------
    Venue("Eccles Coliseum", "Southern Utah", 37.6742, -113.0619, 5830, 8500, "turf", "open", 2.0,
          "FCS. Higher than most FBS altitude venues - SUU travels DOWN to Colorado State."),
    Venue("Bobcat Stadium", "Montana State", 45.6660, -111.0429, 4820, 21650, "turf", "open", 3.4,
          "FCS elite. Bozeman altitude means MTST carries its own acclimation on the road."),
    Venue("Stewart Stadium", "Weber State", 41.1900, -111.9450, 4775, 17500, "turf", "open", 2.8, "FCS."),
    Venue("Nottingham Field", "Northern Colorado", 40.4050, -104.6970, 4675, 8533, "turf", "open", 2.4,
          "FCS. Greeley sits high - UNC is NOT a sea-level visitor at Wyoming."),
    Venue("Holt Arena", "Idaho State", 42.8610, -112.4340, 4450, 12000, "turf", "dome", 2.6, "FCS, indoor."),
    Venue("Washington-Grizzly Stadium", "Montana", 46.8590, -113.9850, 3200, 25217, "turf", "open", 3.6,
          "FCS elite. One of the best home environments at any level."),
    Venue("Roos Field", "Eastern Washington", 47.4920, -117.5830, 1900, 11702, "turf", "open", 2.8,
          "FCS. The red turf."),
    Venue("Fargodome", "North Dakota State", 46.8920, -96.8060, 900, 18700, "turf", "dome", 3.8,
          "MOVED TO FBS (Mountain West) for 2026. Indoor - NDSU never practices in wind, "
          "and at 900 ft it is effectively a sea-level team when it travels to altitude."),
    Venue("Dana J. Dykhouse Stadium", "South Dakota State", 44.3200, -96.7710, 1650, 19340, "turf", "open", 3.4, "FCS elite."),
    Venue("Hornet Stadium", "Sacramento State", 38.5560, -121.4230, 30, 21195, "turf", "open", 2.6, "FCS."),

    # --- Notable mid-tier / low HFA (do not apply a flat number) -------------
    Venue("Gaylord Family Oklahoma Memorial", "Oklahoma", 35.2058, -97.4425, 1180, 86112, "grass", "open", 3.3),
    Venue("Darrell K Royal-Texas Memorial", "Texas", 30.2837, -97.7325, 500, 100119, "turf", "open", 3.3),
    Venue("Notre Dame Stadium", "Notre Dame", 41.6983, -86.2339, 720, 77622, "grass", "open", 3.0,
          "Storied but not especially loud. Tourist-heavy crowd."),
    Venue("Los Angeles Memorial Coliseum", "USC", 34.0141, -118.2879, 160, 77500, "grass", "open", 2.2,
          "Famously soft home environment. Late-arriving, early-leaving crowd."),
    Venue("Rose Bowl", "UCLA", 34.1613, -118.1676, 830, 88565, "grass", "open", 1.8,
          "Often mostly empty. One of the weakest home edges in a power conference."),
    Venue("Sun Devil Stadium", "Arizona State", 33.4255, -111.9325, 1180, 53599, "grass", "open", 2.4,
          "September heat is the real factor, not the crowd."),
    Venue("Faurot Field", "Missouri", 38.9358, -92.3334, 750, 61620, "turf", "open", 2.9),
    Venue("Spartan Stadium", "Michigan State", 42.7281, -84.4847, 840, 75005, "grass", "open", 2.9),
    Venue("Ross-Ade Stadium", "Purdue", 40.4348, -86.9186, 610, 57236, "turf", "open", 2.5),
    Venue("Memorial Stadium", "Nebraska", 40.8206, -96.7057, 1180, 85458, "turf", "open", 3.2,
          "Sellout streak is real; the team's quality has muted the edge in recent years."),
)

_BY_TEAM = {v.team.lower(): v for v in VENUES}
_BY_NAME = {v.name.lower(): v for v in VENUES}


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------


def find(query: str) -> Venue | None:
    """Look up by team or venue name. Substring match, case-insensitive."""
    q = query.lower().strip()
    if q in _BY_TEAM:
        return _BY_TEAM[q]
    if q in _BY_NAME:
        return _BY_NAME[q]
    for key, v in {**_BY_TEAM, **_BY_NAME}.items():
        if q in key:
            return v
    return None


def altitude_edge(home_ft: int, away_ft: int = 0) -> dict:
    """
    Points of edge from an altitude differential.

    The effect is real, well documented in endurance physiology, and **shows up
    late**. It is fourth-quarter fatigue, not a first-quarter advantage, which is
    why it hits second-half team totals and live unders harder than it hits the
    full-game side.

    Scale used here (a prior, not a measurement):
        < 2,000 ft differential  -> negligible
        2,000 - 4,000 ft         -> ~0.5 pt
        4,000 - 6,000 ft         -> ~1.0 pt
        6,000+ ft                -> ~1.5 pt

    A team that trains at altitude carries its own acclimation, which is why the
    differential matters rather than the raw home elevation.
    """
    diff = home_ft - away_ft
    if diff < 2000:
        pts, desc = 0.0, "negligible"
    elif diff < 4000:
        pts, desc = 0.5, "mild - may show up in the fourth quarter"
    elif diff < 6000:
        pts, desc = 1.0, "real - visiting team should fade late"
    else:
        pts, desc = 1.5, "severe - one of the largest situational edges in the sport"
    return {
        "home_ft": home_ft,
        "away_ft": away_ft,
        "differential_ft": diff,
        "points": pts,
        "description": desc,
        "timing": "Effect is cumulative. Weight it toward 2nd-half and live markets.",
    }


def home_edge(home_team: str, away_team: str | None = None, *, fcs: bool = False) -> dict:
    """
    Total home-field edge in points: venue environment + altitude differential.

    Returns the components separately on purpose. A flat 2.5 applied to every
    game is the error this function exists to prevent — and so is silently
    stacking a big crowd number on top of a big altitude number without saying
    which is which.
    """
    hv = find(home_team)
    av = find(away_team) if away_team else None
    baseline = FCS_BASELINE_HFA if fcs else FBS_BASELINE_HFA

    if hv is None:
        return {
            "home": home_team,
            "venue": None,
            "crowd_points": baseline,
            "altitude": altitude_edge(0, 0),
            "total_points": baseline,
            "confidence": "low",
            "note": (
                f"No venue record for {home_team!r}. Falling back to the "
                f"{'FCS' if fcs else 'FBS'} baseline of {baseline}. "
                "Do not treat this as a researched number."
            ),
        }

    away_known = av is not None
    alt = altitude_edge(hv.altitude_ft, av.altitude_ft if av else 0)
    if not away_known and hv.altitude_ft >= 3000:
        alt["warning"] = (
            f"No venue record for {away_team!r}, so its elevation defaulted to sea level. "
            f"If that team plays at altitude, this OVERSTATES the edge — verify before using."
        )
    total = hv.hfa + alt["points"]
    return {
        "away_altitude_known": away_known,
        "home": hv.team,
        "venue": hv.name,
        "capacity": hv.capacity,
        "surface": hv.surface,
        "roof": hv.roof,
        "crowd_points": hv.hfa,
        "altitude": alt,
        "total_points": round(total, 2),
        "vs_baseline": round(total - baseline, 2),
        "confidence": "medium" if av else "low",
        "coords": (hv.lat, hv.lon),
        "note": hv.note,
    }


def altitude_venues(min_ft: int = 4000) -> list[Venue]:
    return sorted((v for v in VENUES if v.altitude_ft >= min_ft),
                  key=lambda v: -v.altitude_ft)


def outdoor_venues() -> Iterable[Venue]:
    """Venues where weather is a live factor — feed these to lib.fetch_news."""
    return (v for v in VENUES if v.roof == "open")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _show(v: Venue) -> None:
    print(f"  {v.name}  ({v.team})")
    print(f"    capacity {v.capacity:,}   {v.surface}/{v.roof}   {v.altitude_ft:,} ft")
    print(f"    crowd HFA {v.hfa:+.1f} pts   (FBS baseline {FBS_BASELINE_HFA})")
    print(f"    coords {v.lat}, {v.lon}")
    if v.note:
        print(f"    {v.note}")


def _cmd_lookup(args) -> int:
    v = find(args.query)
    if v is None:
        print(f"no venue matching {args.query!r}. Try `python3 -m lib.venues list`.")
        return 1
    _show(v)
    return 0


def _cmd_team(args) -> int:
    return _cmd_lookup(argparse.Namespace(query=args.team))


def _cmd_altitude(args) -> int:
    print(f"Venues at or above {args.min_ft:,} ft:\n")
    for v in altitude_venues(args.min_ft):
        print(f"  {v.altitude_ft:>6,} ft   {v.team:<16} {v.name}")
    print("\nAltitude is a FOURTH-QUARTER effect. Weight it toward second-half")
    print("markets and live unders rather than the full-game side.")
    return 0


def _cmd_edge(args) -> int:
    e = home_edge(args.home, args.away, fcs=args.fcs)
    print(f"HOME EDGE — {args.home}" + (f" vs {args.away}" if args.away else ""))
    print("-" * 60)
    if e["venue"] is None:
        print(f"  {e['note']}")
        print(f"  total: {e['total_points']:+.2f} pts")
        return 0
    print(f"  venue          : {e['venue']}  ({e['capacity']:,}, {e['surface']}/{e['roof']})")
    print(f"  crowd edge     : {e['crowd_points']:+.2f} pts")
    a = e["altitude"]
    print(f"  altitude       : {a['home_ft']:,} ft vs {a['away_ft']:,} ft "
          f"-> {a['points']:+.2f} pts ({a['description']})")
    print(f"  TOTAL          : {e['total_points']:+.2f} pts")
    print(f"  vs baseline    : {e['vs_baseline']:+.2f} pts "
          f"({'MORE' if e['vs_baseline'] > 0 else 'LESS'} than a flat {FBS_BASELINE_HFA})")
    if e["note"]:
        print(f"\n  {e['note']}")
    if a["points"] > 0:
        print(f"\n  {a['timing']}")
    return 0


def _cmd_list(args) -> int:
    for v in sorted(VENUES, key=lambda x: -x.hfa):
        print(f"  {v.hfa:+.1f}  {v.altitude_ft:>6,} ft  {v.team:<16} {v.name}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lib.venues", description="CFB venues, HFA, altitude.")
    sub = p.add_subparsers(dest="cmd", required=True)

    lk = sub.add_parser("lookup", help="look up a venue or team")
    lk.add_argument("query")
    lk.set_defaults(func=_cmd_lookup)

    tm = sub.add_parser("team", help="venue for a team")
    tm.add_argument("team")
    tm.set_defaults(func=_cmd_team)

    al = sub.add_parser("altitude", help="altitude venues, highest first")
    al.add_argument("--min-ft", dest="min_ft", type=int, default=4000)
    al.set_defaults(func=_cmd_altitude)

    ed = sub.add_parser("edge", help="home edge for a matchup")
    ed.add_argument("--home", required=True)
    ed.add_argument("--away", default=None)
    ed.add_argument("--fcs", action="store_true")
    ed.set_defaults(func=_cmd_edge)

    sub.add_parser("list", help="all venues by HFA").set_defaults(func=_cmd_list)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
