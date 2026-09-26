/**
 * Edge-detection statistics — ported from lib/backtest.py.
 *
 * These are the most reassuring true things you can tell someone on a cold
 * streak, and the most deflating true things you can tell someone on a hot one.
 * Both matter.
 */
import { americanToDecimal, impliedProb } from "./odds";

/** Inverse normal CDF (Acklam), accurate to ~1e-9 — enough for power calcs. */
function invNorm(p: number): number {
  if (p <= 0 || p >= 1) throw new Error(`invNorm needs p in (0,1), got ${p}`);
  const a = [-3.969683028665376e1, 2.209460984245205e2, -2.759285104469687e2, 1.38357751867269e2, -3.066479806614716e1, 2.506628277459239];
  const b = [-5.447609879822406e1, 1.615858368580409e2, -1.556989798598866e2, 6.680131188771972e1, -1.328068155288572e1];
  const c = [-7.784894002430293e-3, -3.223964580411365e-1, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783];
  const d = [7.784695709041462e-3, 3.224671290700398e-1, 2.445134137142996, 3.754408661907416];
  const pl = 0.02425;
  let q: number, r: number;
  if (p < pl) {
    q = Math.sqrt(-2 * Math.log(p));
    return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  }
  if (p > 1 - pl) return -invNorm(1 - p);
  q = p - 0.5;
  r = q * q;
  return ((((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q) /
         (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
}

/** The hit rate that makes a price break even. -110 needs 52.38%. */
export function breakevenRate(american: number): number {
  return impliedProb(american);
}

/**
 * Mean and SD of profit per 1u bet. This variance is why betting takes so long
 * to evaluate: at -110 the per-bet SD is ~0.95u while a good edge is worth
 * 0.05u. The noise is nineteen times the signal.
 */
export function profitPerBet(prob: number, american: number): { mean: number; sd: number } {
  const b = americanToDecimal(american) - 1;
  const mean = prob * b - (1 - prob);
  const second = prob * b * b + (1 - prob);
  return { mean, sd: Math.sqrt(Math.max(second - mean * mean, 0)) };
}

/**
 * How many bets to prove an edge is real rather than luck. One-sided test of
 * ROI > 0: n = (z_alpha + z_beta)^2 * sigma^2 / mu^2.
 *
 * The single most clarifying number in betting. A 5% ROI bettor — genuinely
 * excellent, better than most professionals — needs on the order of two
 * thousand bets before the record itself proves anything.
 */
export function requiredSampleSize(trueProb: number, american = -110, alpha = 0.05, power = 0.8) {
  const { mean: mu, sd: sigma } = profitPerBet(trueProb, american);
  const be = breakevenRate(american);
  if (mu <= 0) {
    return { trueProb, breakevenProb: be, roi: mu, nRequired: null as number | null,
      note: "No edge to detect — this price is break-even or worse at that hit rate." };
  }
  const n = ((invNorm(1 - alpha) + invNorm(power)) ** 2 * sigma * sigma) / (mu * mu);
  return {
    trueProb, breakevenProb: be,
    edgePctPoints: (trueProb - be) * 100,
    roi: mu, sdPerBet: sigma, signalToNoise: mu / sigma,
    nRequired: Math.ceil(n), alpha, power,
  };
}

/**
 * Exact probability of a losing streak of at least `streak` within `nBets`, via a
 * DP over current run length. Shows that a 7-game skid is expected, not a sign
 * the model broke.
 */
export function losingStreakProbability(prob: number, streak: number, nBets: number): number {
  const q = 1 - prob;
  let state = new Array(streak).fill(0);
  state[0] = 1;
  let absorbed = 0;
  for (let t = 0; t < nBets; t++) {
    const next = new Array(streak).fill(0);
    for (let i = 0; i < streak; i++) {
      const pi = state[i];
      if (pi === 0) continue;
      next[0] += pi * prob;
      if (i + 1 >= streak) absorbed += pi * q;
      else next[i + 1] += pi * q;
    }
    state = next;
  }
  return absorbed;
}

/** Wilson score interval — correct in the small-sample regime a 40-pick bettor is in. */
export function hitRateCI(wins: number, n: number, confidence = 0.95): [number, number] {
  if (n === 0) return [0, 1];
  const z = invNorm(1 - (1 - confidence) / 2);
  const p = wins / n;
  const denom = 1 + (z * z) / n;
  const centre = (p + (z * z) / (2 * n)) / denom;
  const half = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / denom;
  return [Math.max(0, centre - half), Math.min(1, centre + half)];
}

function logChoose(n: number, k: number): number {
  let s = 0;
  for (let i = 1; i <= k; i++) s += Math.log(n - k + i) - Math.log(i);
  return s;
}

/**
 * What a hot record actually proves. Usually far less than it looks.
 *
 * `provesAnEdge` means "clears a one-sided binomial test at this alpha," NOT
 * "has an edge." 12-3 clears it (p = 0.027) while leaving the true hit rate
 * anywhere in 54.8%-93.0%; 11-4 does not (p = 0.084). Neither sample can
 * establish an ROI, and the p-value assumes the record was the only one ever
 * tested — never true of a streak someone chose to show you.
 */
export function realityCheck(wins: number, losses: number, american = -110) {
  const n = wins + losses;
  if (n === 0) return { note: "no bets" };
  const be = breakevenRate(american);
  const [lo, hi] = hitRateCI(wins, n);
  let pValue = 0;
  for (let k = wins; k <= n; k++) pValue += Math.exp(logChoose(n, k) + k * Math.log(be) + (n - k) * Math.log(1 - be));
  pValue = Math.min(1, pValue);
  return {
    record: `${wins}-${losses}`, n, hitRate: wins / n,
    ci95: [lo, hi] as [number, number],
    breakevenRate: be, pValueVsBreakeven: pValue,
    provesAnEdge: pValue < 0.05,
    ciIncludesBreakeven: lo <= be && be <= hi,
  };
}

/**
 * Drawdown and bust risk for a true-edge bettor. The headline: a true 55%
 * bettor at -110 still loses money over 500 bets a meaningful share of the
 * time. Flat staking, 1u per bet.
 */
export function drawdownSimulation(prob: number, nBets: number, american = -110, iterations = 20000, seed = 12345) {
  let a = seed >>> 0;
  const rand = () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  const b = americanToDecimal(american) - 1;
  const finals: number[] = [];
  const maxDDs: number[] = [];
  const worstRuns: number[] = [];
  let losingRuns = 0;
  for (let i = 0; i < iterations; i++) {
    let bank = 0, peak = 0, dd = 0, streak = 0, worst = 0;
    for (let t = 0; t < nBets; t++) {
      if (rand() < prob) {
        bank += b;
        streak = 0;
      } else {
        bank -= 1;
        streak += 1;
        if (streak > worst) worst = streak;
      }
      if (bank > peak) peak = bank;
      if (peak - bank > dd) dd = peak - bank;
    }
    finals.push(bank);
    maxDDs.push(dd);
    worstRuns.push(worst);
    if (bank < 0) losingRuns++;
  }
  finals.sort((x, y) => x - y);
  maxDDs.sort((x, y) => x - y);
  worstRuns.sort((x, y) => x - y);
  const pct = (arr: number[], q: number) => arr[Math.min(arr.length - 1, Math.floor(q * arr.length))];
  return {
    prob, nBets, american, iterations,
    probOfLosingMoney: losingRuns / iterations,
    finalUnits: { p5: pct(finals, 0.05), median: pct(finals, 0.5), p95: pct(finals, 0.95) },
    maxDrawdownUnits: { median: pct(maxDDs, 0.5), p95: pct(maxDDs, 0.95) },
    worstLosingStreak: { median: pct(worstRuns, 0.5), p95: pct(worstRuns, 0.95), max: worstRuns[worstRuns.length - 1] },
    note: "Flat 1u staking. The chance of finishing down is the number people refuse to believe.",
  };
}
