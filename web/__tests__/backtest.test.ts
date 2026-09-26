import { describe, it, expect } from "vitest";
import {
  breakevenRate, profitPerBet, requiredSampleSize, losingStreakProbability,
  hitRateCI, realityCheck, drawdownSimulation,
} from "../lib/backtest";

// Every expected value below was produced by lib/backtest.py, which is the
// reference implementation. If one of these fails, the port drifted — fix the
// port, do not relax the assertion.

describe("breakevenRate", () => {
  it("matches -110 and +100", () => {
    expect(breakevenRate(-110)).toBeCloseTo(0.5238095238095238, 12);
    expect(breakevenRate(100)).toBeCloseTo(0.5, 12);
    expect(breakevenRate(-200)).toBeCloseTo(0.6666666666666666, 12);
  });
});

describe("profitPerBet", () => {
  it("55% at -110 is +0.05u with sd 0.9498", () => {
    const { mean, sd } = profitPerBet(0.55, -110);
    expect(mean).toBeCloseTo(0.05, 10);
    expect(sd).toBeCloseTo(0.9497607354199554, 10);
  });
  it("a break-even hit rate returns zero mean", () => {
    expect(profitPerBet(breakevenRate(-110), -110).mean).toBeCloseTo(0, 12);
  });
});

describe("requiredSampleSize", () => {
  it("55% at -110 needs 2231 bets (python parity)", () => {
    const r = requiredSampleSize(0.55, -110);
    expect(r.nRequired).toBe(2231);
    expect(r.roi).toBeCloseTo(0.05, 10);
    expect(r.sdPerBet!).toBeCloseTo(0.9497607354199554, 10);
    expect(r.breakevenProb).toBeCloseTo(0.5238095238095238, 12);
    expect(r.edgePctPoints!).toBeCloseTo(2.619047619047621, 10);
  });
  it("returns null rather than a number when there is no edge to detect", () => {
    const r = requiredSampleSize(0.50, -110);
    expect(r.nRequired).toBeNull();
    expect(r.roi).toBeLessThan(0);
  });
  it("a bigger edge needs a smaller sample", () => {
    expect(requiredSampleSize(0.60, -110).nRequired!).toBeLessThan(
      requiredSampleSize(0.55, -110).nRequired!,
    );
  });
});

describe("losingStreakProbability", () => {
  it("55% bettor hits a 7-streak in 500 bets 64.4% of the time (python parity)", () => {
    expect(losingStreakProbability(0.55, 7, 500)).toBeCloseTo(0.644016, 5);
  });
  it("is monotonic in streak length", () => {
    const p5 = losingStreakProbability(0.55, 5, 500);
    const p7 = losingStreakProbability(0.55, 7, 500);
    const p10 = losingStreakProbability(0.55, 10, 500);
    expect(p5).toBeGreaterThan(p7);
    expect(p7).toBeGreaterThan(p10);
  });
  it("a streak longer than the sample is impossible", () => {
    expect(losingStreakProbability(0.55, 20, 10)).toBe(0);
  });
});

describe("hitRateCI", () => {
  it("12 of 15 gives the Wilson interval python reports", () => {
    const [lo, hi] = hitRateCI(12, 15);
    expect(lo).toBeCloseTo(0.5481455126348068, 9);
    expect(hi).toBeCloseTo(0.9295245065866523, 9);
  });
  it("narrows as n grows", () => {
    const small = hitRateCI(80, 100);
    const big = hitRateCI(800, 1000);
    expect(big[1] - big[0]).toBeLessThan(small[1] - small[0]);
  });
});

describe("realityCheck", () => {
  // The headline case. 12-3 DOES clear a one-sided test — the earlier claim
  // that it "proves nothing" was wrong, and the interval is the real story.
  it("12-3 clears p<0.05 but leaves the true rate between 55% and 93%", () => {
    const r = realityCheck(12, 3) as any;
    expect(r.hitRate).toBeCloseTo(0.8, 12);
    expect(r.pValueVsBreakeven).toBeCloseTo(0.02718071185248264, 9);
    expect(r.provesAnEdge).toBe(true);
    expect(r.ciIncludesBreakeven).toBe(false);
    expect(r.ci95[0]).toBeCloseTo(0.5481455126348068, 9);
    expect(r.ci95[1]).toBeCloseTo(0.9295245065866523, 9);
    // 38 points wide: cannot tell a marginal winner from a world-beater.
    expect(r.ci95[1] - r.ci95[0]).toBeGreaterThan(0.30);
  });
  it("11-4 is the record genuinely indistinguishable from no edge", () => {
    const r = realityCheck(11, 4) as any;
    expect(r.pValueVsBreakeven).toBeCloseTo(0.08434999770257981, 9);
    expect(r.provesAnEdge).toBe(false);
    expect(r.ciIncludesBreakeven).toBe(true);
  });
  it("a coin flip record proves nothing", () => {
    const r = realityCheck(55, 45) as any;
    expect(r.provesAnEdge).toBe(false);
    expect(r.ciIncludesBreakeven).toBe(true);
    expect(r.pValueVsBreakeven).toBeCloseTo(0.3363, 3);
  });
  it("handles an empty record", () => {
    expect((realityCheck(0, 0) as any).note).toBe("no bets");
  });
});

describe("drawdownSimulation", () => {
  // Monte Carlo with a different PRNG than python's, so these are tolerances
  // around the analytic answer rather than exact parity.
  const d = drawdownSimulation(0.55, 500, -110);

  it("a real 55% edge still finishes down ~11% of the time", () => {
    // python: prob_losing_overall = 0.114; analytic ~0.12
    expect(d.probOfLosingMoney).toBeGreaterThan(0.08);
    expect(d.probOfLosingMoney).toBeLessThan(0.15);
  });
  it("median finish is around +25u", () => {
    expect(d.finalUnits.median).toBeGreaterThan(18);
    expect(d.finalUnits.median).toBeLessThan(32);
  });
  it("the 5th percentile is underwater", () => {
    expect(d.finalUnits.p5).toBeLessThan(0);
  });
  it("median worst losing streak is 7 (python parity)", () => {
    expect(d.worstLosingStreak.median).toBeGreaterThanOrEqual(6);
    expect(d.worstLosingStreak.median).toBeLessThanOrEqual(8);
  });
  it("drawdowns are deep even for a winner", () => {
    expect(d.maxDrawdownUnits.median).toBeGreaterThan(10);
  });
  it("is deterministic for a given seed", () => {
    const a = drawdownSimulation(0.55, 200, -110, 2000, 7);
    const b = drawdownSimulation(0.55, 200, -110, 2000, 7);
    expect(a.probOfLosingMoney).toBe(b.probOfLosingMoney);
  });
});
