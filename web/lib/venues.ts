/**
 * College football venue database — home-field advantage and altitude.
 *
 * GENERATED from lib/venues.py. Do not hand-edit; regenerate so the two engines
 * cannot drift.
 *
 * `hfa` is the venue's crowd/environment edge in POINTS, EXCLUDING altitude.
 * Crowd and altitude are independent effects and are reported separately on
 * purpose — stacking a big crowd number on top of a big altitude number
 * double-counts. Altitude is a FOURTH-QUARTER effect: weight it toward
 * second-half and live markets, not the full-game side.
 *
 * In the NFL home-field advantage is nearly flat. In college football it is not,
 * and the gap between the hardest place to play and an empty MAC stadium is worth
 * four points or more. Most public models apply a flat 2.5 to everything — that
 * gap is the most reliably mispriced situational factor in the sport.
 */

export interface Venue {
  name: string;
  team: string;
  lat: number;
  lon: number;
  altitudeFt: number;
  capacity: number;
  surface: string;
  roof: string;
  /** Crowd/environment points, EXCLUDING altitude. */
  hfa: number;
  note?: string;
}

export const FBS_BASELINE_HFA = 2.5;
/** Higher than FBS: smaller venues sit closer to the field and crowds are denser. */
export const FCS_BASELINE_HFA = 3.0;

export const VENUES: Venue[] = [
  {"name": "Tiger Stadium (Death Valley)", "team": "LSU", "lat": 30.4118, "lon": -91.1836, "altitudeFt": 56, "capacity": 102321, "surface": "grass", "roof": "open", "hfa": 4.0, "note": "Night games are a separate animal - add ~0.5 more after dark. Historically the single toughest road environment in the sport."},
  {"name": "Autzen Stadium", "team": "Oregon", "lat": 44.0584, "lon": -123.0684, "altitudeFt": 400, "capacity": 54000, "surface": "turf", "roof": "open", "hfa": 3.8, "note": "Loudest per capita in the country. Bowl design traps noise - false-start rates spike."},
  {"name": "Kyle Field", "team": "Texas A&M", "lat": 30.61, "lon": -96.34, "altitudeFt": 350, "capacity": 102733, "surface": "grass", "roof": "open", "hfa": 3.8, "note": "12th Man tradition, 100k+ standing. Third-down noise is the mechanism."},
  {"name": "Beaver Stadium", "team": "Penn State", "lat": 40.8122, "lon": -77.856, "altitudeFt": 1180, "capacity": 106572, "surface": "grass", "roof": "open", "hfa": 3.7, "note": "Whiteout games specifically are worth ~1 extra point. Not all games are whiteouts."},
  {"name": "Neyland Stadium", "team": "Tennessee", "lat": 35.955, "lon": -83.925, "altitudeFt": 886, "capacity": 101915, "surface": "grass", "roof": "open", "hfa": 3.6, "note": "Checkerboard + Vol Navy. Enormous when Tennessee is good; fades when they aren't."},
  {"name": "Bryant-Denny Stadium", "team": "Alabama", "lat": 33.2083, "lon": -87.5504, "altitudeFt": 230, "capacity": 100077, "surface": "grass", "roof": "open", "hfa": 3.5, "note": "Crowd is big but corporate/older; talent gap usually does the work, not the noise."},
  {"name": "Ben Hill Griffin (The Swamp)", "team": "Florida", "lat": 29.6499, "lon": -82.3486, "altitudeFt": 82, "capacity": 88548, "surface": "grass", "roof": "open", "hfa": 3.6, "note": "Heat and humidity in September is a real fourth-quarter factor for northern teams."},
  {"name": "Ohio Stadium", "team": "Ohio State", "lat": 40.0017, "lon": -83.0197, "altitudeFt": 725, "capacity": 102780, "surface": "turf", "roof": "open", "hfa": 3.5},
  {"name": "Camp Randall Stadium", "team": "Wisconsin", "lat": 43.07, "lon": -89.4126, "altitudeFt": 869, "capacity": 75822, "surface": "turf", "roof": "open", "hfa": 3.4, "note": "Jump Around between 3rd and 4th quarters is genuinely disruptive."},
  {"name": "Sanford Stadium", "team": "Georgia", "lat": 33.95, "lon": -83.3733, "altitudeFt": 640, "capacity": 92746, "surface": "grass", "roof": "open", "hfa": 3.5},
  {"name": "Memorial Stadium (Death Valley)", "team": "Clemson", "lat": 34.6787, "lon": -82.8432, "altitudeFt": 800, "capacity": 81500, "surface": "grass", "roof": "open", "hfa": 3.5},
  {"name": "Jordan-Hare Stadium", "team": "Auburn", "lat": 32.6025, "lon": -85.4894, "altitudeFt": 709, "capacity": 88043, "surface": "grass", "roof": "open", "hfa": 3.4},
  {"name": "Doak Campbell Stadium", "team": "Florida State", "lat": 30.438, "lon": -84.3045, "altitudeFt": 190, "capacity": 79560, "surface": "grass", "roof": "open", "hfa": 3.3},
  {"name": "Husky Stadium", "team": "Washington", "lat": 47.6503, "lon": -122.3016, "altitudeFt": 30, "capacity": 70138, "surface": "turf", "roof": "open", "hfa": 3.4, "note": "Open end faces the lake; noise reflects off the covered sides."},
  {"name": "Williams-Brice Stadium", "team": "South Carolina", "lat": 33.9731, "lon": -81.0194, "altitudeFt": 240, "capacity": 77559, "surface": "grass", "roof": "open", "hfa": 3.3, "note": "Sandstorm entrance. Underrated environment."},
  {"name": "Kinnick Stadium", "team": "Iowa", "lat": 41.6586, "lon": -91.5513, "altitudeFt": 690, "capacity": 69250, "surface": "turf", "roof": "open", "hfa": 3.3},
  {"name": "Michigan Stadium", "team": "Michigan", "lat": 42.2658, "lon": -83.7487, "altitudeFt": 860, "capacity": 107601, "surface": "turf", "roof": "open", "hfa": 3.2, "note": "Largest capacity in the country but a famously quiet bowl - big is not loud."},
  {"name": "Lane Stadium", "team": "Virginia Tech", "lat": 37.2199, "lon": -80.4185, "altitudeFt": 2080, "capacity": 65632, "surface": "grass", "roof": "open", "hfa": 3.4, "note": "Enter Sandman entrance. Mild elevation on top of a real crowd."},
  {"name": "War Memorial Stadium", "team": "Wyoming", "lat": 41.3114, "lon": -105.569, "altitudeFt": 7220, "capacity": 29181, "surface": "turf", "roof": "open", "hfa": 3.0, "note": "HIGHEST stadium in Division I. Sea-level teams fade badly in the 4th. Also brutally cold and windy late in the year."},
  {"name": "Falcon Stadium", "team": "Air Force", "lat": 38.997, "lon": -104.8434, "altitudeFt": 6621, "capacity": 46692, "surface": "turf", "roof": "open", "hfa": 2.8, "note": "Altitude plus a triple-option-style clock-control scheme compounds the fatigue."},
  {"name": "Folsom Field", "team": "Colorado", "lat": 40.0096, "lon": -105.2669, "altitudeFt": 5360, "capacity": 50183, "surface": "turf", "roof": "open", "hfa": 3.0},
  {"name": "Maverik Stadium", "team": "Utah State", "lat": 41.7518, "lon": -111.8125, "altitudeFt": 4775, "capacity": 25100, "surface": "turf", "roof": "open", "hfa": 2.8},
  {"name": "Rice-Eccles Stadium", "team": "Utah", "lat": 40.76, "lon": -111.8488, "altitudeFt": 4637, "capacity": 51444, "surface": "turf", "roof": "open", "hfa": 3.3},
  {"name": "Mackay Stadium", "team": "Nevada", "lat": 39.5455, "lon": -119.816, "altitudeFt": 4600, "capacity": 27000, "surface": "turf", "roof": "open", "hfa": 2.5},
  {"name": "Hughes Stadium / Canvas", "team": "Colorado State", "lat": 40.5734, "lon": -105.0866, "altitudeFt": 5003, "capacity": 41200, "surface": "turf", "roof": "open", "hfa": 2.6},
  {"name": "Dreamstyle Stadium", "team": "New Mexico", "lat": 35.067, "lon": -106.625, "altitudeFt": 5157, "capacity": 39224, "surface": "turf", "roof": "open", "hfa": 2.6},
  {"name": "Albertsons Stadium", "team": "Boise State", "lat": 43.6027, "lon": -116.1969, "altitudeFt": 2730, "capacity": 36387, "surface": "turf", "roof": "open", "hfa": 3.4, "note": "The blue turf is a genuine visual-adaptation edge, not just a gimmick. Boise's home record is historically absurd."},
  {"name": "Carrier Dome / JMA Wireless", "team": "Syracuse", "lat": 43.0362, "lon": -76.1363, "altitudeFt": 400, "capacity": 49250, "surface": "turf", "roof": "dome", "hfa": 3.2, "note": "Dome noise is trapped; no weather ever. Kills weather-based unders."},
  {"name": "Alamodome", "team": "UTSA", "lat": 29.4169, "lon": -98.4791, "altitudeFt": 650, "capacity": 65000, "surface": "turf", "roof": "dome", "hfa": 2.0, "note": "Huge dome, usually sparse. Capacity misleads - low real HFA."},
  {"name": "Superdome", "team": "Tulane", "lat": 29.9511, "lon": -90.0812, "altitudeFt": 3, "capacity": 73208, "surface": "turf", "roof": "dome", "hfa": 2.2},
  {"name": "Ford Field", "team": "Neutral", "lat": 42.34, "lon": -83.0456, "altitudeFt": 600, "capacity": 65000, "surface": "turf", "roof": "dome", "hfa": 0.0, "note": "Neutral site."},
  {"name": "Mercedes-Benz Stadium", "team": "Neutral", "lat": 33.7554, "lon": -84.4008, "altitudeFt": 1050, "capacity": 71000, "surface": "turf", "roof": "retractable", "hfa": 0.0, "note": "Neutral site - CFP and kickoff games."},
  {"name": "AT&T Stadium", "team": "Neutral", "lat": 32.7473, "lon": -97.0945, "altitudeFt": 550, "capacity": 80000, "surface": "turf", "roof": "retractable", "hfa": 0.0, "note": "Neutral site."},
  {"name": "Clarence T.C. Ching Complex", "team": "Hawaii", "lat": 21.2969, "lon": -157.8171, "altitudeFt": 20, "capacity": 15000, "surface": "turf", "roof": "open", "hfa": 3.5, "note": "The TRAVEL is the edge, not the crowd. Mainland teams cross 5-6 time zones and play at a body-clock hour that is brutal. The return trip wrecks the following week too - fade Hawaii road opponents the NEXT week as well."},
  {"name": "Rentschler Field", "team": "UConn", "lat": 41.7614, "lon": -72.6432, "altitudeFt": 40, "capacity": 40000, "surface": "grass", "roof": "open", "hfa": 1.8},
  {"name": "Eccles Coliseum", "team": "Southern Utah", "lat": 37.6742, "lon": -113.0619, "altitudeFt": 5830, "capacity": 8500, "surface": "turf", "roof": "open", "hfa": 2.0, "note": "FCS. Higher than most FBS altitude venues - SUU travels DOWN to Colorado State."},
  {"name": "Bobcat Stadium", "team": "Montana State", "lat": 45.666, "lon": -111.0429, "altitudeFt": 4820, "capacity": 21650, "surface": "turf", "roof": "open", "hfa": 3.4, "note": "FCS elite. Bozeman altitude means MTST carries its own acclimation on the road."},
  {"name": "Stewart Stadium", "team": "Weber State", "lat": 41.19, "lon": -111.945, "altitudeFt": 4775, "capacity": 17500, "surface": "turf", "roof": "open", "hfa": 2.8, "note": "FCS."},
  {"name": "Nottingham Field", "team": "Northern Colorado", "lat": 40.405, "lon": -104.697, "altitudeFt": 4675, "capacity": 8533, "surface": "turf", "roof": "open", "hfa": 2.4, "note": "FCS. Greeley sits high - UNC is NOT a sea-level visitor at Wyoming."},
  {"name": "Holt Arena", "team": "Idaho State", "lat": 42.861, "lon": -112.434, "altitudeFt": 4450, "capacity": 12000, "surface": "turf", "roof": "dome", "hfa": 2.6, "note": "FCS, indoor."},
  {"name": "Walkup Skydome", "team": "Northern Arizona", "lat": 35.181, "lon": -111.654, "altitudeFt": 6900, "capacity": 10000, "surface": "turf", "roof": "dome", "hfa": 2.4, "note": "FCS. Flagstaff is among the highest elevations in the country - NAU carries its own acclimation everywhere and NEUTRALISES the altitude edge of other mountain hosts. Indoor."},
  {"name": "Washington-Grizzly Stadium", "team": "Montana", "lat": 46.859, "lon": -113.985, "altitudeFt": 3200, "capacity": 25217, "surface": "turf", "roof": "open", "hfa": 3.6, "note": "FCS elite. One of the best home environments at any level."},
  {"name": "Roos Field", "team": "Eastern Washington", "lat": 47.492, "lon": -117.583, "altitudeFt": 1900, "capacity": 11702, "surface": "turf", "roof": "open", "hfa": 2.8, "note": "FCS. The red turf."},
  {"name": "Fargodome", "team": "North Dakota State", "lat": 46.892, "lon": -96.806, "altitudeFt": 900, "capacity": 18700, "surface": "turf", "roof": "dome", "hfa": 3.8, "note": "MOVED TO FBS (Mountain West) for 2026. Indoor - NDSU never practices in wind, and at 900 ft it is effectively a sea-level team when it travels to altitude."},
  {"name": "Dana J. Dykhouse Stadium", "team": "South Dakota State", "lat": 44.32, "lon": -96.771, "altitudeFt": 1650, "capacity": 19340, "surface": "turf", "roof": "open", "hfa": 3.4, "note": "FCS elite."},
  {"name": "Hornet Stadium", "team": "Sacramento State", "lat": 38.556, "lon": -121.423, "altitudeFt": 30, "capacity": 21195, "surface": "turf", "roof": "open", "hfa": 2.6, "note": "FCS."},
  {"name": "Gaylord Family Oklahoma Memorial", "team": "Oklahoma", "lat": 35.2058, "lon": -97.4425, "altitudeFt": 1180, "capacity": 86112, "surface": "grass", "roof": "open", "hfa": 3.3},
  {"name": "Darrell K Royal-Texas Memorial", "team": "Texas", "lat": 30.2837, "lon": -97.7325, "altitudeFt": 500, "capacity": 100119, "surface": "turf", "roof": "open", "hfa": 3.3},
  {"name": "Notre Dame Stadium", "team": "Notre Dame", "lat": 41.6983, "lon": -86.2339, "altitudeFt": 720, "capacity": 77622, "surface": "grass", "roof": "open", "hfa": 3.0, "note": "Storied but not especially loud. Tourist-heavy crowd."},
  {"name": "Los Angeles Memorial Coliseum", "team": "USC", "lat": 34.0141, "lon": -118.2879, "altitudeFt": 160, "capacity": 77500, "surface": "grass", "roof": "open", "hfa": 2.2, "note": "Famously soft home environment. Late-arriving, early-leaving crowd."},
  {"name": "Rose Bowl", "team": "UCLA", "lat": 34.1613, "lon": -118.1676, "altitudeFt": 830, "capacity": 88565, "surface": "grass", "roof": "open", "hfa": 1.8, "note": "Often mostly empty. One of the weakest home edges in a power conference."},
  {"name": "Sun Devil Stadium", "team": "Arizona State", "lat": 33.4255, "lon": -111.9325, "altitudeFt": 1180, "capacity": 53599, "surface": "grass", "roof": "open", "hfa": 2.4, "note": "September heat is the real factor, not the crowd."},
  {"name": "Faurot Field", "team": "Missouri", "lat": 38.9358, "lon": -92.3334, "altitudeFt": 750, "capacity": 61620, "surface": "turf", "roof": "open", "hfa": 2.9},
  {"name": "Spartan Stadium", "team": "Michigan State", "lat": 42.7281, "lon": -84.4847, "altitudeFt": 840, "capacity": 75005, "surface": "grass", "roof": "open", "hfa": 2.9},
  {"name": "Ross-Ade Stadium", "team": "Purdue", "lat": 40.4348, "lon": -86.9186, "altitudeFt": 610, "capacity": 57236, "surface": "turf", "roof": "open", "hfa": 2.5},
  {"name": "Memorial Stadium", "team": "Nebraska", "lat": 40.8206, "lon": -96.7057, "altitudeFt": 1180, "capacity": 85458, "surface": "turf", "roof": "open", "hfa": 3.2, "note": "Sellout streak is real; the team's quality has muted the edge in recent years."},
];

const BY_TEAM = new Map(VENUES.map((v) => [v.team.toLowerCase(), v]));

export function findVenue(team: string): Venue | undefined {
  const k = team.trim().toLowerCase();
  const exact = BY_TEAM.get(k);
  if (exact) return exact;
  // tolerate "Ohio St", "Texas A&M Aggies", etc.
  for (const v of VENUES) {
    const t = v.team.toLowerCase();
    if (t.startsWith(k) || k.startsWith(t)) return v;
  }
  return undefined;
}

/**
 * Altitude priced off the DIFFERENTIAL, not the raw home elevation. A 4,600-foot
 * home team hosting a 4,820-foot visitor has no altitude edge at all — that is the
 * mistake this function exists to prevent.
 */
/**
 * Points of edge from an altitude DIFFERENTIAL, not from raw home elevation —
 * a team that trains at altitude carries its own acclimation.
 *
 * Scale mirrors lib/venues.py exactly. It is a prior, not a measurement:
 *   < 2,000 ft -> negligible | 2,000-4,000 -> 0.5 | 4,000-6,000 -> 1.0 | 6,000+ -> 1.5
 *
 * The effect is fourth-quarter fatigue, so it hits second-half team totals and
 * live unders harder than it hits the full-game side.
 */
export function altitudeEdge(homeFt: number, awayFt = 0) {
  const diff = homeFt - awayFt;
  let points: number, description: string;
  if (diff < 2000) {
    points = 0.0;
    description = "negligible";
  } else if (diff < 4000) {
    points = 0.5;
    description = "mild - may show up in the fourth quarter";
  } else if (diff < 6000) {
    points = 1.0;
    description = "real - visiting team should fade late";
  } else {
    points = 1.5;
    description = "severe - one of the largest situational edges in the sport";
  }
  return {
    homeFt, awayFt, differentialFt: diff, points, description,
    negligible: points === 0,
    note: points === 0
      ? "Differential too small to price. Negligible."
      : "Effect is cumulative. Weight it toward 2nd-half and live markets, not the full-game side.",
  };
}

export interface HomeEdge {
  venue: string | null;
  crowdPoints: number;
  altitude: ReturnType<typeof altitudeEdge>;
  totalPoints: number;
  vsBaseline: number;
  baseline: number;
  warnings: string[];
  note?: string;
}

/** Crowd and altitude, separated. Sum them yourself only if you mean to. */
export function homeEdge(homeTeam: string, awayTeam?: string, fcs = false): HomeEdge {
  const baseline = fcs ? FCS_BASELINE_HFA : FBS_BASELINE_HFA;
  const hv = findVenue(homeTeam);
  const av = awayTeam ? findVenue(awayTeam) : undefined;
  const warnings: string[] = [];

  if (!hv) {
    warnings.push(
      `No venue record for '${homeTeam}', so the ${fcs ? "FCS" : "FBS"} baseline of ${baseline} was used. ` +
        "Do not treat this as a researched number.",
    );
    return {
      venue: null, crowdPoints: baseline, altitude: altitudeEdge(0, 0),
      totalPoints: baseline, vsBaseline: 0, baseline, warnings,
    };
  }
  if (awayTeam && !av) {
    warnings.push(
      `No venue record for '${awayTeam}', so its elevation defaulted to sea level. ` +
        "If the visitor is itself a high-altitude team, the real altitude edge is smaller or zero.",
    );
  }
  const alt = altitudeEdge(hv.altitudeFt, av?.altitudeFt ?? 0);
  const total = hv.hfa + alt.points;
  return {
    venue: hv.name, crowdPoints: hv.hfa, altitude: alt,
    totalPoints: total, vsBaseline: total - baseline, baseline,
    warnings, note: hv.note,
  };
}

