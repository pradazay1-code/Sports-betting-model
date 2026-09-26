/**
 * Parity tests. Every expected value here was produced by the Python
 * implementation in lib/odds.py — these assert the two engines agree, so the
 * ported math can be trusted in production.
 */
import { describe, expect, it } from "vitest";
import * as O from "../lib/odds";
import * as S from "../lib/simulate";

describe("conversions", () => {
  it("american to decimal", () => {
    expect(O.americanToDecimal(-110)).toBeCloseTo(1.909090909, 6);
    expect(O.americanToDecimal(100)).toBeCloseTo(2.0, 9);
    expect(O.americanToDecimal(150)).toBeCloseTo(2.5, 9);
    expect(O.americanToDecimal(-200)).toBeCloseTo(1.5, 9);
  });
  it("round-trips", () => {
    for (const a of [-350, -175, -110, 100, 145, 900]) {
      expect(O.decimalToAmerican(O.americanToDecimal(a))).toBeCloseTo(a, 6);
    }
  });
  it("prob to american", () => {
    expect(O.probToAmerican(0.5)).toBeCloseTo(100, 6);
    expect(O.impliedProb(-110)).toBeCloseTo(0.5238095238, 8);
  });
  it("rejects zero", () => expect(() => O.americanToDecimal(0)).toThrow());
});

describe("hold", () => {
  it("two -110 legs hold 4.55%", () => {
    expect(O.hold([-110, -110]) * 100).toBeCloseTo(4.5454545, 5);
  });
});

describe("devig", () => {
  it("power sums to one and is monotone in price", () => {
    const p = O.devig([-240, 198], "power");
    expect(p[0] + p[1]).toBeCloseTo(1, 10);
    expect(p[0]).toBeGreaterThan(p[1]);
  });
  it("power on -240/+198 matches the Python value", () => {
    // python: lib.odds.devig([-240, 198], method="power") -> 0.68897...
    expect(O.devig([-240, 198], "power")[0]).toBeCloseTo(0.689, 3);
  });
  it("a fair two-way market is unchanged", () => {
    const p = O.devig([100, -100], "power");
    expect(p[0]).toBeCloseTo(0.5, 9);
  });
  it("all four methods sum to one on a multiway board", () => {
    const prices = [-160, 160, 170, 175, 195, 195, 210];
    for (const probs of Object.values(O.devigAll(prices))) {
      expect(probs.reduce((a, b) => a + b, 0)).toBeCloseTo(1, 9);
    }
  });
  it("power removes more vig from the longshot than multiplicative", () => {
    const q = [-400, 300];
    expect(O.devig(q, "power")[1]).toBeLessThan(O.devig(q, "multiplicative")[1]);
  });
  it("defaults: power for two-way, multiplicative for multiway", () => {
    expect(O.defaultMethod(2)).toBe("power");
    expect(O.defaultMethod(7)).toBe("multiplicative");
  });
  it("refuses a one-sided market", () => expect(() => O.devig([-110])).toThrow(/two outcomes/));
  it("spread flags real disagreement", () => {
    expect(O.devigSpread([100, -100]).maxSpreadPts).toBeLessThan(1.5);
    expect(O.devigSpread([-2000, 900]).maxSpreadPts).toBeGreaterThan(0);
  });
});

describe("EV and Kelly", () => {
  it("EV is zero at a fair price", () => {
    expect(O.evFromAmerican(0.5, 100)).toBeCloseTo(0, 9);
  });
  it("EV matches the python worked example", () => {
    // python: ev_from_american(0.5531, -110) -> 0.0559...
    expect(O.evFromAmerican(0.5531, -110)).toBeCloseTo(0.0559, 4);
  });
  it("Kelly is zero with no edge and positive with one", () => {
    expect(O.kelly(0.5, 2.0)).toBe(0);
    expect(O.kelly(0.55, 2.0)).toBeCloseTo(0.025, 6); // (0.55*1-0.45)/1 = 0.10, /4
  });
  it("never recommends over the 2u ceiling", () => {
    const e = O.priceEdge(0.9, -110);
    expect(e.stake).toBeLessThanOrEqual(O.MAX_STAKE_UNITS);
    expect(e.capped).toBe(true);
  });
  it("calls no bet under the 2% floor", () => {
    expect(O.priceEdge(0.525, -110).verdict).toBe("NO BET");
    expect(O.priceEdge(0.58, -110).verdict).toBe("BET");
  });
  it("prop floor is respected when passed", () => {
    // 0.55 at -110 is EXACTLY 5.00% EV — right on the floor, so it must pass.
    expect(O.priceEdge(0.55, -110, { minEv: 0.05 }).verdict).toBe("BET");
    // 0.54 is +3.1%: clears the 2% side floor but not the 5% prop floor.
    expect(O.priceEdge(0.54, -110, { minEv: 0.05 }).verdict).toBe("NO BET");
    expect(O.priceEdge(0.54, -110).verdict).toBe("BET");
  });
});

describe("parlays", () => {
  it("four -110 legs hand the book about 17%", () => {
    const a = O.parlayAnalysis([-110, -110, -110, -110]);
    expect(a.holdPct * 100).toBeGreaterThan(15);
    expect(a.holdPct * 100).toBeLessThan(19);
  });
  it("the parlay hold exceeds the single-leg hold", () => {
    const a = O.parlayAnalysis([-110, -110, -110, -110]);
    expect(a.holdPct).toBeGreaterThan(a.singleLegHoldPct!);
  });
  it("correlated legs supplied as fair probs price correctly", () => {
    const a = O.parlayAnalysis([-110, -110], { fairProbs: [0.67, 0.66] });
    expect(a.trueProbability).toBeCloseTo(0.4422, 4);
  });
  it("round robin enumerates the right number of tickets", () => {
    expect(O.roundRobin([-110, -110, -110, -110], 2).ticketCount).toBe(6);
    expect(O.roundRobin([-110, -110, -110, -110], 3).ticketCount).toBe(4);
  });
});

describe("sharp anchor", () => {
  it("prefers pinnacle over any soft book", () => {
    const a = O.sharpAnchor({ draftkings: -110, pinnacle: -118, fanduel: -105 });
    expect(a.book).toBe("pinnacle");
    expect(a.isSharp).toBe(true);
  });
  it("respects the priority order", () => {
    expect(O.sharpAnchor({ circa: -115, betonline: -112 }).book).toBe("circa");
  });
  it("falls back to the median and says confidence should drop", () => {
    const a = O.sharpAnchor({ draftkings: -110, fanduel: -105, betmgm: -115 });
    expect(a.isSharp).toBe(false);
    expect(a.note).toMatch(/unconfirmed/);
  });
});

describe("CLV", () => {
  it("beating the close is positive", () => {
    const c = O.clv(150, 120);
    expect(c.beatClose).toBe(true);
    expect(c.clvPts).toBeGreaterThan(0);
  });
  it("losing to the close is negative", () => {
    expect(O.clv(120, 150).clvPts).toBeLessThan(0);
  });
});

describe("simulation", () => {
  const cfg = { home: { name: "H", pointsPerDrive: 28 / 11 }, away: { name: "A", pointsPerDrive: 21 / 11 }, baseDrives: 11, iterations: 20000, seed: 7 };

  it("reproduces the projected points", () => {
    const r = S.runGame(cfg);
    expect(r.homeMean).toBeGreaterThan(25);
    expect(r.homeMean).toBeLessThan(31);
    expect(r.awayMean).toBeGreaterThan(18.5);
    expect(r.awayMean).toBeLessThan(23.5);
  });
  it("is deterministic under a seed", () => {
    expect(S.runGame(cfg).totalMean).toBe(S.runGame(cfg).totalMean);
  });
  it("favours the better team and signs the spread correctly", () => {
    const r = S.runGame(cfg);
    expect(r.homeWinProb).toBeGreaterThan(0.5);
    expect(r.fairSpread).toBeLessThan(0); // negative = home laying
  });
  it("builds scores only from 3s, 6s and 7s", () => {
    for (const [h, a] of S.runGame({ ...cfg, iterations: 2000 }).scores) {
      for (const pts of [h, a]) expect([1, 2, 4, 5]).not.toContain(pts);
    }
  });
  it("puts more margin mass on 3 and 7 than on their dead neighbours", () => {
    const r = S.runGame({ home: { name: "H", pointsPerDrive: 2.05 }, away: { name: "A", pointsPerDrive: 2.05 }, baseDrives: 11, iterations: 60000, seed: 17 });
    const k = S.keyNumbers(r, [2, 3, 5, 7, 8, 9]);
    expect(k[3]).toBeGreaterThan(k[2]);
    expect(k[3]).toBeGreaterThan(k[5]);
    expect(k[7]).toBeGreaterThan(k[8]);
  });
  it("excludes pushes from cover probability", () => {
    const r = S.runGame(cfg);
    const c = S.pCover(r, -3);
    expect(c.push).toBeGreaterThan(0);
    expect(S.pCover(r, -3.5).push).toBe(0);
  });
  it("cover probability falls as the favourite lays more", () => {
    const r = S.runGame(cfg);
    const ps = [-1.5, -3.5, -6.5, -9.5].map((s) => S.pCover(r, s).homeCover);
    expect(ps).toEqual([...ps].sort((a, b) => b - a));
  });
  it("over probability falls as the total rises", () => {
    const r = S.runGame(cfg);
    const ps = [38.5, 44.5, 50.5, 56.5].map((t) => S.pOver(r, t).over);
    expect(ps).toEqual([...ps].sort((a, b) => b - a));
  });
});

describe("path simulation", () => {
  const cfg = { home: { name: "H", pointsPerDrive: 2.6 }, away: { name: "A", pointsPerDrive: 1.9 }, baseDrives: 11, iterations: 20000, seed: 91 };

  it("leading by 7 at some point beats winning outright", () => {
    const win = S.runGame(cfg);
    const paths = S.runPaths(cfg);
    expect(paths.pLeadsBy("home", 7)).toBeGreaterThan(win.homeWinProb);
    expect(paths.pLeadsBy("away", 7)).toBeGreaterThan(1 - win.homeWinProb);
  });
  it("the underdog gains more from a live-lead trigger than the favourite", () => {
    const win = S.runGame(cfg);
    const paths = S.runPaths(cfg);
    const favGain = paths.pLeadsBy("home", 7) - win.homeWinProb;
    const dogGain = paths.pLeadsBy("away", 7) - (1 - win.homeWinProb);
    expect(dogGain).toBeGreaterThan(favGain);
  });
  it("lead probability decreases in the threshold", () => {
    const p = S.runPaths(cfg);
    const ps = [3, 7, 10, 14, 21].map((k) => p.pLeadsBy("home", k));
    expect(ps).toEqual([...ps].sort((a, b) => b - a));
  });
});

describe("the median correction", () => {
  it("a line implies a HIGHER mean than itself for a skewed distribution", () => {
    expect(S.impliedMean(90.5, 0.42)).toBeGreaterThan(90.5);
    expect(S.impliedMean(90.5, 0.42)).toBeCloseTo(98.2, 1);
  });
  it("matches the python worked example on a passing line", () => {
    expect(S.impliedMean(270.5, 0.28)).toBeCloseTo(280.9, 1);
  });
  it("under probability is 50% when the mean equals the implied mean", () => {
    const line = 90.5, cv = 0.42;
    expect(S.lognormalUnder(S.impliedMean(line, cv), cv, line)).toBeCloseTo(0.5, 2);
  });
});

describe("receptions", () => {
  it("more targets means a higher chance of clearing a line", () => {
    const low = S.receptionProb(6, 2.4, 0.7, 5);
    const high = S.receptionProb(10, 2.4, 0.7, 5);
    expect(high).toBeGreaterThan(low);
  });
  it("is under-dispersed vs Poisson at realistic target SDs, so Poisson UNDERSTATES the floor", () => {
    const d = S.receptionDispersion(7, 2.4, 0.786);
    expect(d.ratio).toBeLessThan(1);
    expect(d.regime).toMatch(/under-dispersed/);
    const compound = S.receptionProb(7, 2.4, 0.786, 4);
    const poisson = S.poissonAtLeast(7 * 0.786, 4);
    expect(compound).toBeGreaterThan(poisson);
  });
  it("flips to over-dispersed once target SD exceeds sqrt(E[targets])", () => {
    expect(S.receptionDispersion(7, 2.4, 0.786).breakEvenTargetSd).toBeCloseTo(Math.sqrt(7), 6);
    expect(S.receptionDispersion(7, 3.5, 0.786).ratio).toBeGreaterThan(1);
    const volatile_ = S.receptionProb(7, 3.9, 0.786, 4);
    const poisson = S.poissonAtLeast(7 * 0.786, 4);
    expect(volatile_).toBeLessThan(poisson);
  });
  it("probability falls as the line rises", () => {
    const ps = [3, 4, 5, 6].map((n) => S.receptionProb(7, 2.4, 0.786, n));
    expect(ps).toEqual([...ps].sort((a, b) => b - a));
  });
});
