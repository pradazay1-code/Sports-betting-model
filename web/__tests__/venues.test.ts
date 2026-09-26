import { describe, it, expect } from "vitest";
import {
  VENUES, FBS_BASELINE_HFA, FCS_BASELINE_HFA, findVenue, altitudeEdge, homeEdge,
} from "../lib/venues";

// Expected values come from `python3 -m lib.venues`, the reference engine.

describe("the venue table", () => {
  it("is populated and internally consistent", () => {
    expect(VENUES.length).toBeGreaterThanOrEqual(50);
    for (const v of VENUES) {
      expect(v.team.length).toBeGreaterThan(0);
      expect(v.name.length).toBeGreaterThan(0);
      // Neutral sites are legitimately 0.0 — that is the point of them.
      expect(v.hfa).toBeGreaterThanOrEqual(0);
      expect(v.hfa).toBeLessThan(6);          // nothing is worth 6 points of crowd
      if (v.team === "Neutral") expect(v.hfa).toBe(0);
      expect(v.altitudeFt).toBeGreaterThanOrEqual(0);
      expect(Math.abs(v.lat)).toBeLessThanOrEqual(90);
      expect(Math.abs(v.lon)).toBeLessThanOrEqual(180);
    }
  });
  it("has no duplicate home teams", () => {
    // Several rows share team "Neutral" on purpose (Ford Field, AT&T, MBS), so
    // uniqueness only applies to real home venues.
    const teams = VENUES.filter((v) => v.team !== "Neutral").map((v) => v.team);
    expect(new Set(teams).size).toBe(teams.length);
  });
  it("carries neutral sites, all with zero crowd edge", () => {
    const neutrals = VENUES.filter((v) => v.team === "Neutral");
    expect(neutrals.length).toBeGreaterThanOrEqual(3);
    for (const n of neutrals) expect(n.hfa).toBe(0);
  });
  it("puts Wyoming highest in Division I", () => {
    const highest = [...VENUES].sort((a, b) => b.altitudeFt - a.altitudeFt)[0];
    expect(highest.team).toBe("Wyoming");
    expect(highest.altitudeFt).toBe(7220);
  });
  it("uses a higher FCS baseline than FBS", () => {
    expect(FBS_BASELINE_HFA).toBe(2.5);
    expect(FCS_BASELINE_HFA).toBe(3.0);
  });
});

describe("findVenue", () => {
  it("is case and whitespace insensitive", () => {
    expect(findVenue("wyoming")?.team).toBe("Wyoming");
    expect(findVenue("  Air Force  ")?.team).toBe("Air Force");
  });
  it("returns undefined rather than guessing", () => {
    expect(findVenue("Hogwarts")).toBeUndefined();
  });
});

describe("altitudeEdge — python parity on the documented tiers", () => {
  it("prices the differential, not the raw elevation", () => {
    // Northern Colorado (4,675 ft) at Wyoming (7,220 ft) is NOT a sea-level trip.
    const naive = altitudeEdge(7220, 0);
    const real = altitudeEdge(7220, 4675);
    expect(naive.points).toBe(1.5);
    expect(real.points).toBe(0.5);   // 2,545 ft differential
    expect(real.points).toBeLessThan(naive.points);
  });
  it("matches each tier boundary exactly", () => {
    expect(altitudeEdge(1999, 0).points).toBe(0.0);
    expect(altitudeEdge(2000, 0).points).toBe(0.5);
    expect(altitudeEdge(3999, 0).points).toBe(0.5);
    expect(altitudeEdge(4000, 0).points).toBe(1.0);
    expect(altitudeEdge(5999, 0).points).toBe(1.0);
    expect(altitudeEdge(6000, 0).points).toBe(1.5);
    expect(altitudeEdge(20000, 0).points).toBe(1.5);  // capped, not extrapolated
  });
  it("Wyoming hosting Hawaii is +1.5, matching the python CLI", () => {
    const a = altitudeEdge(7220, 20);
    expect(a.differentialFt).toBe(7200);
    expect(a.points).toBe(1.5);
    expect(a.description).toContain("severe");
  });
  it("flags negligible rather than reporting a tiny fake number", () => {
    const a = altitudeEdge(860, 840);
    expect(a.points).toBe(0);
    expect(a.negligible).toBe(true);
  });
  it("never returns a negative edge for a downhill trip", () => {
    expect(altitudeEdge(20, 7220).points).toBe(0);
  });
  it("always carries the fourth-quarter timing caveat when it prices anything", () => {
    expect(altitudeEdge(7220, 20).note).toMatch(/2nd-half|second-half/i);
  });
});

describe("homeEdge", () => {
  it("reproduces the python CLI for Wyoming vs Hawaii", () => {
    const e = homeEdge("Wyoming", "Hawaii");
    expect(e.venue).toBe("War Memorial Stadium");
    expect(e.crowdPoints).toBe(3.0);
    expect(e.altitude.points).toBe(1.5);
    expect(e.totalPoints).toBe(4.5);
    expect(e.vsBaseline).toBe(2.0);      // 2 full points more than a flat 2.5
    expect(e.warnings).toHaveLength(0);
  });
  it("keeps crowd and altitude separate so they are not double-counted", () => {
    const e = homeEdge("Air Force", "Hawaii");
    expect(e.crowdPoints).toBe(2.8);
    expect(e.altitude.points).toBe(1.5);
    expect(e.totalPoints).toBeCloseTo(4.3, 10);
  });
  it("warns loudly instead of inventing a number for an unknown venue", () => {
    const e = homeEdge("Some Directional State");
    expect(e.venue).toBeNull();
    expect(e.crowdPoints).toBe(FBS_BASELINE_HFA);
    expect(e.warnings.join(" ")).toMatch(/Do not treat this as a researched number/);
  });
  it("uses the FCS baseline when told the game is FCS", () => {
    const e = homeEdge("Some Directional State", undefined, true);
    expect(e.crowdPoints).toBe(FCS_BASELINE_HFA);
  });
  it("warns when the visitor's elevation had to be assumed", () => {
    const e = homeEdge("Wyoming", "Unknown Tech");
    expect(e.warnings.join(" ")).toMatch(/defaulted to sea level/);
    expect(e.altitude.points).toBe(1.5);   // possibly overstated, and it says so
  });
  it("gives a neutral site no crowd edge", () => {
    const e = homeEdge("Neutral");
    expect(e.crowdPoints).toBe(0);
    expect(e.vsBaseline).toBeLessThan(0);   // strictly worse than a flat 2.5
  });
  it("spreads well over a point between the best and worst real crowd", () => {
    // CLAUDE.md 3.4a: the gap between the hardest place to play and an empty
    // MAC stadium is the most reliably mispriced situational factor in CFB.
    const hfas = VENUES.filter((v) => v.team !== "Neutral").map((v) => v.hfa);
    expect(Math.max(...hfas) - Math.min(...hfas)).toBeGreaterThanOrEqual(1.5);
  });
});
