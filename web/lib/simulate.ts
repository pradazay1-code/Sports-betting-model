/**
 * Drive-level Monte Carlo — ported from lib/simulate.py.
 *
 * Two design choices that matter:
 *
 * 1. Scores are built from drives, not drawn from a continuous distribution.
 *    Points arrive in 3s and 7s, so simulating drive outcomes reproduces the
 *    lumps on 3, 7, 10 and 14 that make key numbers worth paying for. A normal
 *    draw on margin smooths those away and misprices every half point.
 *
 * 2. The two teams are correlated. A game-level pace factor drives both teams'
 *    possession counts and a shared environment factor pushes scoring the same
 *    direction. Independent teams understate the variance of the TOTAL badly,
 *    because real shootouts and real slogs are joint events.
 */

/** Deterministic PRNG (mulberry32) so a seed reproduces a run across runtimes. */
function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function gauss(r: () => number, mean: number, sd: number): number {
  // Box-Muller
  let u = 0;
  let v = 0;
  while (u === 0) u = r();
  while (v === 0) v = r();
  return mean + sd * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

export interface TeamModel {
  name: string;
  /** Points per offensive drive. NFL league average is roughly 2.0. */
  pointsPerDrive: number;
  /** Share of scoring drives ending in a TD rather than a FG. League ~0.60. */
  tdShare?: number;
}

export interface GameSimConfig {
  home: TeamModel;
  away: TeamModel;
  /** Mean offensive possessions per team. NFL ~11, CFB ~12.5. */
  baseDrives?: number;
  paceSd?: number;
  envSd?: number;
  teamSd?: number;
  seed?: number;
  iterations?: number;
}

/** Solve for (P(TD), P(FG)) that produce the target points per drive. */
function driveProbs(t: TeamModel): [number, number] {
  const s = t.tdShare ?? 0.6;
  const ptsPerScore = s * 6.95 + (1 - s) * 3.0;
  const k = Math.min(t.pointsPerDrive / ptsPerScore, 0.95);
  return [s * k, (1 - s) * k];
}

export interface SimResult {
  n: number;
  homeMean: number;
  awayMean: number;
  totalMean: number;
  totalSd: number;
  marginMean: number;
  marginSd: number;
  /** Negative means the home team is laying points. */
  fairSpread: number;
  homeWinProb: number;
  scores: Array<[number, number]>;
}

export function runGame(cfg: GameSimConfig): SimResult {
  const {
    home, away,
    baseDrives = 11.0,
    paceSd = 0.07,
    envSd = 0.12,
    teamSd = 0.17,
    seed = 20260101,
    iterations = 40000,
  } = cfg;

  const r = rng(seed);
  const [hTd, hFg] = driveProbs(home);
  const [aTd, aFg] = driveProbs(away);
  // Floor scales off baseDrives so a half-game sim isn't handed a full game's drives.
  const floor = Math.max(2, Math.round(baseDrives * 0.64));
  const scores: Array<[number, number]> = [];

  for (let i = 0; i < iterations; i++) {
    const pace = Math.max(0.6, gauss(r, 1, paceSd));
    const env = Math.max(0.4, gauss(r, 1, envSd));
    const drives = Math.max(floor, Math.round(baseDrives * pace));

    const score = (pTd: number, pFg: number): number => {
      const mult = env * Math.max(0.3, gauss(r, 1, teamSd));
      const td = Math.min(pTd * mult, 0.75);
      const fg = Math.min(pFg * mult, 0.75 - td);
      let pts = 0;
      for (let d = 0; d < drives; d++) {
        const x = r();
        if (x < td) pts += r() < 0.94 ? 7 : 6;
        else if (x < td + fg) pts += 3;
      }
      return pts;
    };
    scores.push([score(hTd, hFg), score(aTd, aFg)]);
  }

  const h = scores.map((s) => s[0]);
  const a = scores.map((s) => s[1]);
  const margins = scores.map((s) => s[0] - s[1]);
  const totals = scores.map((s) => s[0] + s[1]);
  const mean = (xs: number[]) => xs.reduce((p, c) => p + c, 0) / xs.length;
  const sd = (xs: number[]) => { const m = mean(xs); return Math.sqrt(mean(xs.map((x) => (x - m) ** 2))); };
  const wins = margins.filter((m) => m > 0).length + 0.5 * margins.filter((m) => m === 0).length;

  return {
    n: scores.length,
    homeMean: mean(h), awayMean: mean(a),
    totalMean: mean(totals), totalSd: sd(totals),
    marginMean: mean(margins), marginSd: sd(margins),
    fairSpread: -mean(margins),
    homeWinProb: wins / margins.length,
    scores,
  };
}

/** P(home covers). Pushes are excluded from the denominator, as a book does. */
export function pCover(res: SimResult, homeSpread: number) {
  const need = -homeSpread;
  const m = res.scores.map((s) => s[0] - s[1]);
  const w = m.filter((x) => x > need).length;
  const l = m.filter((x) => x < need).length;
  const p = m.filter((x) => x === need).length;
  return { homeCover: w + l ? w / (w + l) : 0, push: p / m.length };
}

export function pOver(res: SimResult, line: number) {
  const t = res.scores.map((s) => s[0] + s[1]);
  const o = t.filter((x) => x > line).length;
  const u = t.filter((x) => x < line).length;
  const p = t.filter((x) => x === line).length;
  return { over: o + u ? o / (o + u) : 0, under: o + u ? u / (o + u) : 0, push: p / t.length };
}

/** Mass on each absolute margin — this is what a half point is actually worth. */
export function keyNumbers(res: SimResult, values: number[]): Record<number, number> {
  const m = res.scores.map((s) => Math.abs(s[0] - s[1]));
  const out: Record<number, number> = {};
  for (const v of values) out[v] = m.filter((x) => x === v).length / m.length;
  return out;
}

export function teamTotal(res: SimResult, side: "home" | "away", line: number): number {
  const i = side === "home" ? 0 : 1;
  const s = res.scores.map((x) => x[i]);
  const o = s.filter((x) => x > line).length;
  const u = s.filter((x) => x < line).length;
  return o + u ? o / (o + u) : 0;
}

/**
 * Simulate the drive-by-drive SEQUENCE, not just the final score.
 *
 * Needed for anything resolving on the score at a moment rather than at the
 * end: "leads by 7+ at any point", live-lead promos, halftime markets. A
 * final-score sim cannot answer those — a team that loses by 3 very often led
 * by 10 on the way there.
 */
export function runPaths(cfg: GameSimConfig) {
  const {
    home, away,
    baseDrives = 11.0, paceSd = 0.07, envSd = 0.12, teamSd = 0.17,
    seed = 20260101, iterations = 40000,
  } = cfg;
  const r = rng(seed + 7);
  const [hTd, hFg] = driveProbs(home);
  const [aTd, aFg] = driveProbs(away);
  const out: Array<{ h: number; a: number; hi: number; lo: number }> = [];

  for (let i = 0; i < iterations; i++) {
    const pace = Math.max(0.6, gauss(r, 1, paceSd));
    const env = Math.max(0.4, gauss(r, 1, envSd));
    const drives = Math.max(2, Math.round(baseDrives * pace));
    const caps = (pTd: number, pFg: number): [number, number] => {
      const mult = env * Math.max(0.3, gauss(r, 1, teamSd));
      const td = Math.min(pTd * mult, 0.75);
      return [td, Math.min(pFg * mult, 0.75 - td)];
    };
    const hc = caps(hTd, hFg);
    const ac = caps(aTd, aFg);
    const homeFirst = r() < 0.5;
    let hs = 0; let as = 0; let hi = 0; let lo = 0;
    for (let d = 0; d < drives; d++) {
      for (const isHome of homeFirst ? [true, false] : [false, true]) {
        const [td, fg] = isHome ? hc : ac;
        const x = r();
        let pts = 0;
        if (x < td) pts = r() < 0.94 ? 7 : 6;
        else if (x < td + fg) pts = 3;
        if (isHome) hs += pts; else as += pts;
        const m = hs - as;
        if (m > hi) hi = m;
        if (m < lo) lo = m;
      }
    }
    out.push({ h: hs, a: as, hi, lo });
  }
  return {
    n: out.length,
    /** P(side leads by >= k at ANY point). */
    pLeadsBy: (side: "home" | "away", k: number) =>
      out.filter((x) => (side === "home" ? x.hi >= k : -x.lo >= k)).length / out.length,
    pEitherLeadsBy: (k: number) => out.filter((x) => x.hi >= k || -x.lo >= k).length / out.length,
  };
}

// --- count / yardage distributions -----------------------------------------

/**
 * A yardage line sits near the MEDIAN, not the mean, and yardage distributions
 * are right-skewed. Comparing a mean projection straight to the line invents an
 * edge on every right-skewed market. Use `impliedMean` to correct first.
 */
export function lognormalUnder(mean: number, cv: number, line: number): number {
  const s2 = Math.log(1 + cv * cv);
  const mu = Math.log(mean) - s2 / 2;
  const z = (Math.log(line) - mu) / Math.sqrt(s2);
  return 0.5 * (1 + erf(z / Math.SQRT2));
}

/** The mean a book's line implies, given a coefficient of variation. */
export function impliedMean(line: number, cv: number): number {
  return line * Math.exp(Math.log(1 + cv * cv) / 2);
}

function erf(x: number): number {
  // Abramowitz & Stegun 7.1.26
  const s = x < 0 ? -1 : 1;
  const ax = Math.abs(x);
  const t = 1 / (1 + 0.3275911 * ax);
  const y = 1 - ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-ax * ax);
  return s * y;
}

/**
 * Receptions are NOT Poisson — they are capped by targets, and target counts have
 * their own distribution. Poisson forces Var = mean. The real variance is
 *
 *     Var(C) = E[T]·p·(1-p) + Var(T)·p²
 *
 * which is BELOW the mean — under-dispersed — whenever the target SD is less than
 * sqrt(E[T]), and above it otherwise. At realistic starter target SDs (2.2-2.8 on
 * a mean of 6-10) receptions are under-dispersed, so Poisson **understates** the
 * probability of clearing a modest line. The direction flips for a volatile,
 * boom-or-bust target share. Either way the honest move is to model the target
 * distribution rather than assume it — use `receptionDispersion` to see which
 * regime you are in.
 */
export function receptionProb(
  meanTargets: number, targetSd: number, catchRate: number, need: number,
  iterations = 120000, seed = 4242,
): number {
  const r = rng(seed);
  const shape = (meanTargets / targetSd) ** 2;
  const scale = (targetSd * targetSd) / meanTargets;
  let hits = 0;
  for (let i = 0; i < iterations; i++) {
    const t = Math.max(0, Math.round(gammaSample(r, shape, scale)));
    let c = 0;
    for (let j = 0; j < t; j++) if (r() < catchRate) c++;
    if (c >= need) hits++;
  }
  return hits / iterations;
}

/**
 * Which side of Poisson this parameterisation falls on. `ratio` < 1 means
 * under-dispersed (Poisson understates the chance of clearing a modest line);
 * > 1 means over-dispersed (Poisson overstates it). Break-even target SD is
 * sqrt(E[targets]).
 */
export function receptionDispersion(meanTargets: number, targetSd: number, catchRate: number) {
  const mean = meanTargets * catchRate;
  const variance = meanTargets * catchRate * (1 - catchRate) + targetSd * targetSd * catchRate * catchRate;
  return {
    mean,
    variance,
    poissonVariance: mean,
    ratio: variance / mean,
    regime: variance < mean ? "under-dispersed vs Poisson" : "over-dispersed vs Poisson",
    breakEvenTargetSd: Math.sqrt(meanTargets),
  };
}

function gammaSample(r: () => number, shape: number, scale: number): number {
  // Marsaglia-Tsang
  if (shape < 1) return gammaSample(r, shape + 1, scale) * Math.pow(r(), 1 / shape);
  const d = shape - 1 / 3;
  const c = 1 / Math.sqrt(9 * d);
  for (;;) {
    const x = gauss(r, 0, 1);
    const v = (1 + c * x) ** 3;
    if (v <= 0) continue;
    const u = r();
    if (Math.log(u) < 0.5 * x * x + d - d * v + d * Math.log(v)) return d * v * scale;
  }
}

/** P(X >= k) for a Poisson rate — touchdown counts, scoring events. */
export function poissonAtLeast(lambda: number, k: number): number {
  let cum = 0;
  let term = Math.exp(-lambda);
  for (let i = 0; i < k; i++) { cum += term; term = (term * lambda) / (i + 1); }
  return 1 - cum;
}
