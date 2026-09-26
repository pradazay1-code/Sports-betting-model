import { describe, it, expect } from "vitest";
import { currentSeason, consensus, CfbdError, spRatings, matchupRatings, fullSlate, type CfbLine } from "../lib/cfbd";

// No CFBD_API_KEY in the test environment, and the CFBD host is not reachable
// from CI, so the network paths are asserted to FAIL LOUDLY rather than mocked.
// The pure functions below are the parts worth unit testing.

describe("currentSeason", () => {
  it("labels a season by the year it starts, flipping in March", () => {
    expect(currentSeason(new Date("2026-09-26T00:00:00Z"))).toBe(2026);
    expect(currentSeason(new Date("2026-12-31T00:00:00Z"))).toBe(2026);
    expect(currentSeason(new Date("2027-01-15T00:00:00Z"))).toBe(2026); // bowl season
    expect(currentSeason(new Date("2027-02-28T00:00:00Z"))).toBe(2026);
    expect(currentSeason(new Date("2027-03-01T00:00:00Z"))).toBe(2027); // flips
  });
});

describe("missing key", () => {
  it("throws a message that tells the agent what to do instead", async () => {
    await expect(spRatings()).rejects.toThrow(/CFBD_API_KEY is not set/);
    await expect(spRatings()).rejects.toThrow(/say the ratings spine is missing/);
  });
  it("propagates through matchupRatings rather than returning empty ratings", async () => {
    await expect(matchupRatings("Miami", "Wake Forest")).rejects.toThrow(/CFBD_API_KEY/);
  });
  it("throws from fullSlate when BOTH divisions fail, never an empty slate", async () => {
    // Returning {count: 0, games: []} would invite presenting an empty slate as
    // though the week had no games.
    await expect(fullSlate()).rejects.toThrow(CfbdError);
    await expect(fullSlate()).rejects.toThrow(/Could not fetch either division/);
  });
});

describe("consensus", () => {
  const line: CfbLine = {
    homeTeam: "Miami", awayTeam: "Wake Forest", week: 4,
    lines: [
      { provider: "Bovada", spread: -20.5, overUnder: 51.5, homeMoneyline: -1400, awayMoneyline: 800 },
      { provider: "DraftKings", spread: -21, overUnder: 52, homeMoneyline: -1500, awayMoneyline: 850 },
      { provider: "ESPN Bet", spread: -20, overUnder: 51, homeMoneyline: -1450, awayMoneyline: 825 },
    ],
  };

  it("takes the median, not the mean", () => {
    const c = consensus(line);
    expect(c.medianSpread).toBe(-20.5);
    expect(c.medianTotal).toBe(51.5);
  });
  it("reports the range so book disagreement is visible", () => {
    const c = consensus(line);
    expect(c.spreadRange).toEqual([-21, -20]);
    expect(c.totalRange).toEqual([51, 52]);
  });
  it("averages the middle two on an even count", () => {
    const c = consensus({ ...line, lines: line.lines.slice(0, 2) });
    expect(c.medianSpread).toBeCloseTo(-20.75, 9);
  });
  it("says plainly that this is not a sharp price", () => {
    expect(consensus(line).note).toMatch(/median anchor, not a sharp price/);
    expect(consensus(line).note).toMatch(/no Pinnacle/i);
  });
  it("returns null rather than 0 when a market has no prices", () => {
    const c = consensus({ ...line, lines: [{ provider: "X", spread: null, overUnder: null, homeMoneyline: null, awayMoneyline: null }] });
    expect(c.medianSpread).toBeNull();
    expect(c.medianTotal).toBeNull();
    expect(c.spreadRange).toBeNull();
  });
  it("handles an empty provider list", () => {
    const c = consensus({ ...line, lines: [] });
    expect(c.medianSpread).toBeNull();
    expect(c.providers).toEqual([]);
  });
  it("lists which providers were included", () => {
    expect(consensus(line).providers).toEqual(["Bovada", "DraftKings", "ESPN Bet"]);
  });
});
