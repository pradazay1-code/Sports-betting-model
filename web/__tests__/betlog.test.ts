import { describe, it, expect } from "vitest";
import { newBet, betProfit, betClvPts, betEvVsClose, summarize, toCSV, type Bet } from "../lib/betlog";

const bet = (o: Partial<Bet>) => newBet({ sport: "NFL", event: "DET @ BUF", market: "Total", selection: "Under 54.5", book: "FanDuel", ...o });

describe("betProfit", () => {
  it("pays the decimal price on a win", () => {
    expect(betProfit(bet({ takenAmerican: -110, stakeUnits: 1, result: "win" }))).toBeCloseTo(0.90909, 4);
    expect(betProfit(bet({ takenAmerican: 150, stakeUnits: 2, result: "win" }))).toBeCloseTo(3.0, 9);
  });
  it("loses the stake on a loss", () => {
    expect(betProfit(bet({ stakeUnits: 1.5, result: "loss" }))).toBe(-1.5);
  });
  it("returns zero on push, void and pending", () => {
    for (const result of ["push", "void", "pending"] as const) {
      expect(betProfit(bet({ result }))).toBe(0);
    }
  });
});

describe("CLV", () => {
  it("is positive when the line moved toward you", () => {
    expect(betClvPts(bet({ takenAmerican: -105, closingAmerican: -120 }))!).toBeCloseTo(3.3259, 3);
  });
  it("is negative when you bet into a worse number than the close", () => {
    expect(betClvPts(bet({ takenAmerican: -120, closingAmerican: -105 }))!).toBeLessThan(0);
  });
  it("is null rather than zero when no closing price was recorded", () => {
    expect(betClvPts(bet({ closingAmerican: null }))).toBeNull();
    expect(betEvVsClose(bet({ closingAmerican: null }))).toBeNull();
  });
  it("EV vs close is positive exactly when the close was beaten", () => {
    expect(betEvVsClose(bet({ takenAmerican: -105, closingAmerican: -120 }))!).toBeGreaterThan(0);
    expect(betEvVsClose(bet({ takenAmerican: -120, closingAmerican: -105 }))!).toBeLessThan(0);
  });
});

describe("summarize", () => {
  it("handles an empty log without dividing by zero", () => {
    const s = summarize([]);
    expect(s.total).toBe(0);
    expect(s.roiPct).toBeNull();
    expect(s.hitRatePct).toBeNull();
    expect(s.record).toBeNull();
    expect(s.clv.meanClvPts).toBeNull();
    expect(s.verdict).toMatch(/closing price/);
  });

  it("counts units and record correctly, excluding pushes from the record", () => {
    const bets = [
      bet({ result: "win", takenAmerican: -110, stakeUnits: 1 }),
      bet({ result: "win", takenAmerican: -110, stakeUnits: 1 }),
      bet({ result: "loss", takenAmerican: -110, stakeUnits: 1 }),
      bet({ result: "push", takenAmerican: -110, stakeUnits: 1 }),
      bet({ result: "pending", takenAmerican: -110, stakeUnits: 1 }),
    ];
    const s = summarize(bets);
    expect(s.total).toBe(5);
    expect(s.settled).toBe(3);
    expect(s.pending).toBe(1);
    expect(s.pushes).toBe(1);
    expect(s.wins).toBe(2);
    expect(s.losses).toBe(1);
    expect(s.unitsStaked).toBe(3);
    expect(s.unitsPL).toBeCloseTo(0.81818, 4);
    expect(s.hitRatePct).toBeCloseTo(66.667, 2);
    expect(s.roiPct).toBeCloseTo(27.27, 1);
  });

  it("puts the record behind a sample-size caveat rather than reporting ROI as fact", () => {
    const bets = Array.from({ length: 15 }, (_, i) => bet({ result: i < 12 ? "win" : "loss" }));
    const s = summarize(bets);
    expect(s.record!.record).toBe("12-3");
    // Even at 80% the honest framing is how many bets it would take to establish.
    expect(s.sampleSizeNeeded).toBeGreaterThan(0);
    expect(s.sampleSizeNeeded).toBeLessThan(200);   // a huge observed edge needs fewer
  });

  it("says roughly 2,200 bets when the observed rate is 55%", () => {
    const bets = Array.from({ length: 100 }, (_, i) => bet({ result: i < 55 ? "win" : "loss" }));
    expect(summarize(bets).sampleSizeNeeded).toBe(2231);
  });

  it("leads with CLV and calls a positive mean the real signal", () => {
    const bets = Array.from({ length: 12 }, () => bet({ takenAmerican: -105, closingAmerican: -125, result: "loss" }));
    const s = summarize(bets);
    expect(s.clv.tracked).toBe(12);
    expect(s.clv.beatClose).toBe(12);
    expect(s.clv.beatClosePct).toBe(100);
    expect(s.clv.meanClvPts!).toBeGreaterThan(0);
    // Every bet lost, and the verdict still says the process is right.
    expect(s.unitsPL).toBeLessThan(0);
    expect(s.verdict).toMatch(/signal that you are actually finding edges/);
  });

  it("calls out negative CLV even when the record is winning", () => {
    const bets = Array.from({ length: 12 }, () => bet({ takenAmerican: -125, closingAmerican: -105, result: "win" }));
    const s = summarize(bets);
    expect(s.unitsPL).toBeGreaterThan(0);
    expect(s.verdict).toMatch(/means no edge, whatever the record says/);
  });

  it("nags for closing prices while fewer than 10 are recorded", () => {
    const bets = [bet({ takenAmerican: -105, closingAmerican: -120, result: "win" })];
    expect(summarize(bets).verdict).toMatch(/only 1 bet|Only 1 bet/);
  });

  it("breaks results down by sport, most bets first", () => {
    const bets = [
      bet({ sport: "NFL", result: "win" }), bet({ sport: "NFL", result: "loss" }),
      bet({ sport: "CFB", result: "win" }), bet({ sport: "", result: "loss" }),
    ];
    const s = summarize(bets);
    expect(s.bySport[0].sport).toBe("NFL");
    expect(s.bySport[0].n).toBe(2);
    expect(s.bySport.map((r) => r.sport)).toContain("unspecified");
  });
});

describe("toCSV", () => {
  it("emits a header and one row per bet", () => {
    const csv = toCSV([bet({ result: "win", closingAmerican: -120 }), bet({ result: "loss" })]);
    const lines = csv.split("\n");
    expect(lines).toHaveLength(3);
    expect(lines[0]).toContain("clvPts");
    expect(lines[0]).toContain("profitUnits");
  });
  it("quotes fields containing commas, quotes and newlines", () => {
    const csv = toCSV([bet({ event: "DET @ BUF, TNF", notes: 'he said "no edge"' })]);
    expect(csv).toContain('"DET @ BUF, TNF"');
    expect(csv).toContain('"he said ""no edge"""');
  });
  it("leaves CLV blank rather than writing 0 when no closing price exists", () => {
    const csv = toCSV([bet({ result: "win" })]);
    const cells = csv.split("\n")[1].split(",");
    expect(cells[7]).toBe("");     // closingAmerican
  });
});

describe("newBet", () => {
  it("gives every bet a distinct id and a timestamp", () => {
    const a = newBet(), b = newBet();
    expect(a.id).not.toBe(b.id);
    expect(Number.isNaN(Date.parse(a.placedAt))).toBe(false);
  });
  it("defaults to pending at 1u and -110", () => {
    const b = newBet();
    expect(b.result).toBe("pending");
    expect(b.stakeUnits).toBe(1);
    expect(b.takenAmerican).toBe(-110);
  });
});
