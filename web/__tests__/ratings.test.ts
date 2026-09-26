import { describe, it, expect } from "vitest";
import {
  ratingsSpread, projectBoth, teamTotals,
  CFB_MARGIN_SD, NFL_MARGIN_SD, NFL_LEAGUE_MEAN_PPG, CFB_LEAGUE_MEAN_PPG,
} from "../lib/ratings";

describe("ratingsSpread — the 3.4b spine requirement", () => {
  it("REFUSES to price a CFB side with no ratings", () => {
    // The real failure: a PPG model produced a pick'em against Miami -20.5.
    const r = ratingsSpread({
      homeTeam: "Miami", awayTeam: "Wake Forest", marketSpread: -20.5, sport: "cfb",
    });
    expect(r.playable).toBe(false);
    expect(r.projectedMargin).toBeUndefined();
    expect(r.fairHomeSpread).toBeUndefined();
    expect(r.reason).toMatch(/ratings spine/);
    expect(r.reason).toMatch(/3\.4b/);
  });
  it("refuses when only one side has a rating", () => {
    expect(ratingsSpread({ homeTeam: "A", awayTeam: "B", homeRating: 12 }).playable).toBe(false);
    expect(ratingsSpread({ homeTeam: "A", awayTeam: "B", awayRating: 12 }).playable).toBe(false);
  });
  it("treats NaN as missing rather than propagating it", () => {
    const r = ratingsSpread({ homeTeam: "A", awayTeam: "B", homeRating: NaN, awayRating: 3 });
    expect(r.playable).toBe(false);
  });
  it("names which team is missing the rating", () => {
    const r = ratingsSpread({ homeTeam: "Miami", awayTeam: "Wake Forest", homeRating: 21.4 });
    expect(r.reason).toContain("Wake Forest");
    expect(r.reason).not.toContain("Miami and");
  });
});

describe("ratingsSpread — pricing", () => {
  const base = {
    homeTeam: "Miami", awayTeam: "Wake Forest",
    homeRating: 21.4, awayRating: -1.9, ratingName: "SP+" as const,
    hfa: 2.9, sport: "cfb" as const,
  };

  it("converts a ratings gap plus HFA into a margin and a spread", () => {
    const r = ratingsSpread(base);
    expect(r.playable).toBe(true);
    expect(r.projectedMargin).toBeCloseTo(26.2, 6);   // 21.4 - (-1.9) + 2.9
    expect(r.fairHomeSpread).toBeCloseTo(-26.2, 6);   // book-facing sign
  });
  it("applies no home field at a neutral site", () => {
    const r = ratingsSpread({ ...base, neutralSite: true });
    expect(r.hfaUsed).toBe(0);
    expect(r.projectedMargin).toBeCloseTo(23.3, 6);
    expect(r.notes.join(" ")).toMatch(/Neutral site/);
  });
  it("warns when it had to fall back to a flat HFA", () => {
    const r = ratingsSpread({ ...base, hfa: undefined });
    expect(r.notes.join(" ")).toMatch(/NOT a constant/);
  });
  it("leans the side its number favors", () => {
    const r = ratingsSpread({ ...base, marketSpread: -20.5 });
    expect(r.disagreement).toBeCloseTo(-5.7, 6);
    expect(r.leanSide).toBe("Miami");          // we have Miami better than market
    expect(r.homeCoverProb).toBeCloseTo(0.635, 2);
  });
  it("leans the underdog when the market is too high on the favorite", () => {
    const r = ratingsSpread({ ...base, marketSpread: -33.5 });
    expect(r.disagreement).toBeGreaterThan(0);
    expect(r.leanSide).toBe("Wake Forest");
    expect(r.homeCoverProb!).toBeLessThan(0.5);
  });
  it("calls no side when it agrees with the market", () => {
    const r = ratingsSpread({ ...base, marketSpread: -26 });
    expect(r.leanSide).toMatch(/none/);
  });
  it("says the market is probably right when the gap is large", () => {
    const r = ratingsSpread({ ...base, marketSpread: -14.5 });
    expect(r.notes.join(" ")).toMatch(/base rate says the market is right/);
  });
  it("prices a push only on a whole number", () => {
    expect(ratingsSpread({ ...base, marketSpread: -26.5 }).pushProb).toBe(0);
    expect(ratingsSpread({ ...base, marketSpread: -26 }).pushProb!).toBeGreaterThan(0);
  });
  it("keeps the three outcome probabilities summing to one", () => {
    for (const spread of [-26, -20.5, -33, -3]) {
      const r = ratingsSpread({ ...base, marketSpread: spread });
      expect(r.homeCoverProb! + r.awayCoverProb! + r.pushProb!).toBeCloseTo(1, 9);
    }
  });
  it("warns that CFB key numbers are flatter, and NFL's are not", () => {
    expect(ratingsSpread(base).notes.join(" ")).toMatch(/FLATTER/);
    expect(
      ratingsSpread({ ...base, sport: "nfl" }).notes.join(" "),
    ).toMatch(/25-30 cents/);
  });
  it("uses a wider margin SD for CFB than the NFL", () => {
    expect(CFB_MARGIN_SD).toBeGreaterThan(NFL_MARGIN_SD);
    expect(ratingsSpread(base).sdUsed).toBe(CFB_MARGIN_SD);
    expect(ratingsSpread({ ...base, sport: "nfl" }).sdUsed).toBe(NFL_MARGIN_SD);
  });
  it("labels its SD as a prior", () => {
    expect(ratingsSpread(base).notes.join(" ")).toMatch(/prior, not a measurement/);
  });
});

describe("projectBoth — the 3.2a both-forms rule", () => {
  // DET @ BUF, 2026-09-17. The inputs are the ones from the report that lost 2u.
  const detBuf = {
    homeTeam: "BUF", awayTeam: "DET",
    homeOff: 28.9, homeDefAllowed: 22.9,
    awayOff: 28.6, awayDefAllowed: 24.3,
    sport: "nfl" as const,
  };

  it("runs both forms and never discards one", () => {
    const r = projectBoth({ ...detBuf, leagueMean: 22.9 });
    expect(r.additive.total).toBeCloseTo(52.35, 2);
    expect(r.multiplicative.total).toBeCloseTo(59.27, 2);
    // The multiplicative form is the HIGHER one. Calling it "absurd" is what cost 2u.
    expect(r.multiplicative.total).toBeGreaterThan(r.additive.total);
    expect(r.range).toEqual([r.additive.total, r.multiplicative.total]);
  });

  it("REGRESSION: refuses a directional read on DET-BUF because 54.5 sits inside the range", () => {
    // This is the bet that lost. The market total fell between the two forms, so
    // there was never a directional read to take — under either league mean.
    for (const leagueMean of [22.9, NFL_LEAGUE_MEAN_PPG]) {
      const r = projectBoth({ ...detBuf, leagueMean, marketTotal: 54.5 });
      expect(r.marketTotal).toBe(54.5);
      expect(r.range[0]).toBeLessThan(54.5);
      expect(r.range[1]).toBeGreaterThan(54.5);
      expect(r.leanVsMarket).toMatch(/none/);
      expect(r.leanVsMarket).toMatch(/INSIDE/);
      expect(r.notes.join(" ")).toMatch(/do not have a directional read/);
    }
  });

  it("caps the stake at 1u when a named input was unavailable", () => {
    // My own sensitivity table called pace "the under's kill switch" and I bet 2u anyway.
    const r = projectBoth({
      ...detBuf, leagueMean: 22.9, marketTotal: 54.5,
      unavailableInputs: ["pace / plays per game"],
    });
    expect(r.maxStakeUnits).toBe(1.0);
    expect(r.notes.join(" ")).toMatch(/CAPPED at 1u/);
    expect(r.notes.join(" ")).toMatch(/pace/);
  });
  it("allows 2u only when every input was available", () => {
    expect(projectBoth({ ...detBuf, leagueMean: 22.9 }).maxStakeUnits).toBe(2.0);
  });

  it("declares nothing playable past the divergence gate", () => {
    // A great offense against a terrible defense blows the forms apart.
    const r = projectBoth({
      homeTeam: "Elite", awayTeam: "Sieve",
      homeOff: 38, homeDefAllowed: 14,
      awayOff: 34, awayDefAllowed: 40,
      leagueMean: 22, sport: "nfl", marketTotal: 60,
    });
    expect(r.divergence).toBeGreaterThan(10);
    expect(r.playable).toBe(false);
    expect(r.maxStakeUnits).toBe(0);
    expect(r.notes.join(" ")).toMatch(/no playable number/);
  });
  it("respects a custom gate", () => {
    expect(projectBoth({ ...detBuf, leagueMean: 22.9, gate: 3 }).playable).toBe(false);
    expect(projectBoth({ ...detBuf, leagueMean: 22.9, gate: 20 }).playable).toBe(true);
  });

  it("calls OVER only when both forms clear the market", () => {
    const r = projectBoth({ ...detBuf, leagueMean: 22.9, marketTotal: 44 });
    expect(r.leanVsMarket).toMatch(/^OVER/);
  });
  it("calls UNDER only when both forms sit below the market", () => {
    const r = projectBoth({ ...detBuf, leagueMean: 22.9, marketTotal: 66 });
    expect(r.leanVsMarket).toMatch(/^UNDER/);
  });

  it("uses the corrected NFL league mean, not the stale 2025 figure", () => {
    expect(NFL_LEAGUE_MEAN_PPG).toBe(23.8);
    expect(CFB_LEAGUE_MEAN_PPG).toBeGreaterThan(NFL_LEAGUE_MEAN_PPG);
  });
  it("a lower league mean inflates the multiplicative form", () => {
    const stale = projectBoth({ ...detBuf, leagueMean: 22.9 });
    const fixed = projectBoth({ ...detBuf, leagueMean: 23.8 });
    expect(stale.multiplicative.total).toBeGreaterThan(fixed.multiplicative.total);
    // The additive form is untouched by the league mean.
    expect(stale.additive.total).toBeCloseTo(fixed.additive.total, 12);
  });
  it("always warns against double-counting market absorption", () => {
    expect(projectBoth({ ...detBuf }).notes.join(" ")).toMatch(/double-counts/);
  });
});

describe("teamTotals", () => {
  it("splits a total by margin and round-trips", () => {
    const { home, away } = teamTotals(54.5, 6.5);
    expect(home).toBeCloseTo(30.5, 9);
    expect(away).toBeCloseTo(24, 9);
    expect(home + away).toBeCloseTo(54.5, 9);
    expect(home - away).toBeCloseTo(6.5, 9);
  });
  it("handles a pick'em", () => {
    const { home, away } = teamTotals(44, 0);
    expect(home).toBe(away);
  });
});
