/**
 * Price math — ported from lib/odds.py with test parity.
 *
 * This is the load-bearing file. Every recommendation the agent makes resolves
 * to a number that comes out of here, so it is pure, dependency-free, and
 * covered by tests that assert the same values the Python implementation
 * produces. If you change a function here, change the Python and the test
 * together or the two engines silently diverge.
 */

const EPS = 1e-12;

export const MIN_EV = 0.02;          // under 2% is inside our own devig error bars
export const MAX_STAKE_UNITS = 2.0;  // a rule, not a setting
export const DEFAULT_KELLY_DIVISOR = 4.0;

export type DevigMethod = "multiplicative" | "proportional" | "additive" | "power" | "shin";

// --- conversions -----------------------------------------------------------

export function americanToDecimal(american: number): number {
  if (american === 0) throw new Error("American odds of 0 are not a price");
  return american > 0 ? 1 + american / 100 : 1 + 100 / Math.abs(american);
}

export function decimalToAmerican(dec: number): number {
  if (dec <= 1) throw new Error(`Decimal odds must exceed 1, got ${dec}`);
  return dec >= 2 ? (dec - 1) * 100 : -100 / (dec - 1);
}

export function impliedProb(american: number): number {
  return 1 / americanToDecimal(american);
}

export function probToDecimal(prob: number): number {
  if (prob <= 0 || prob >= 1) throw new Error(`Probability must be in (0,1), got ${prob}`);
  return 1 / prob;
}

export function probToAmerican(prob: number): number {
  return decimalToAmerican(probToDecimal(prob));
}

function asProbs(prices: number[], decimal = false): number[] {
  return decimal ? prices.map((p) => 1 / p) : prices.map(impliedProb);
}

export function overround(prices: number[], decimal = false): number {
  return asProbs(prices, decimal).reduce((a, b) => a + b, 0);
}

/** The book's theoretical hold: the share of stakes it keeps at these prices. */
export function hold(prices: number[], decimal = false): number {
  const total = overround(prices, decimal);
  return (total - 1) / total;
}

// --- devig -----------------------------------------------------------------

/** Proportional. Overstates longshot fair probability where real bias exists. */
function devigMultiplicative(q: number[]): number[] {
  const total = q.reduce((a, b) => a + b, 0);
  return q.map((x) => x / total);
}

/** Equal share of the overround off each outcome. Mirror bias of multiplicative. */
function devigAdditive(q: number[]): number[] {
  const n = q.length;
  const excess = (q.reduce((a, b) => a + b, 0) - 1) / n;
  let out = q.map((x) => x - excess);
  if (out.some((x) => x <= 0)) {
    out = out.map((x) => Math.max(x, 1e-6));
    const total = out.reduce((a, b) => a + b, 0);
    out = out.map((x) => x / total);
  }
  return out;
}

/**
 * Solve sum(q_i ** k) = 1 for k. Every q_i < 1, so raising to k > 1 shrinks the
 * sum monotonically and bisection is safe. Default for two-way markets: it
 * removes proportionally more vig from the longshot, which is what books do.
 */
function devigPower(q: number[], tol = 1e-12, maxIter = 200): number[] {
  if (q.some((x) => x <= 0 || x >= 1)) return devigMultiplicative(q);

  let lo = 1.0;
  let hi = 2.0;
  let bracketed = false;
  for (let i = 0; i < 60; i++) {
    if (q.reduce((a, x) => a + Math.pow(x, hi), 0) <= 1.0) { bracketed = true; break; }
    lo = hi;
    hi = hi * 2.0;
  }
  if (!bracketed) return devigMultiplicative(q);

  for (let i = 0; i < maxIter; i++) {
    const mid = 0.5 * (lo + hi);
    const s = q.reduce((a, x) => a + Math.pow(x, mid), 0);
    if (Math.abs(s - 1.0) < tol) break;
    if (s > 1.0) lo = mid; else hi = mid;
  }
  const k = 0.5 * (lo + hi);
  const out = q.map((x) => Math.pow(x, k));
  const total = out.reduce((a, b) => a + b, 0);
  return out.map((x) => x / total);
}

/**
 * Shin (1992/1993) — models the overround as protection against a proportion
 * `z` of insider money. Solve for z such that sum(p_i) = 1.
 */
function devigShin(q: number[], tol = 1e-12, maxIter = 200): number[] {
  const pi = q.reduce((a, b) => a + b, 0);
  if (pi <= 1.0 + EPS) return devigMultiplicative(q);

  const probs = (z: number): number[] => {
    if (z <= EPS) return q.map((x) => x / Math.sqrt(pi));
    const denom = 2.0 * (1.0 - z);
    return q.map((x) => (Math.sqrt(z * z + (4.0 * (1.0 - z) * x * x) / pi) - z) / denom);
  };

  let lo = 0.0;
  let hi = 0.99;
  if (probs(hi).reduce((a, b) => a + b, 0) > 1.0) return devigMultiplicative(q);

  for (let i = 0; i < maxIter; i++) {
    const mid = 0.5 * (lo + hi);
    const s = probs(mid).reduce((a, b) => a + b, 0);
    if (Math.abs(s - 1.0) < tol) break;
    if (s > 1.0) lo = mid; else hi = mid;
  }
  const out = probs(0.5 * (lo + hi));
  const total = out.reduce((a, b) => a + b, 0);
  return out.map((x) => x / total);
}

const DEVIG_FNS: Record<DevigMethod, (q: number[]) => number[]> = {
  multiplicative: devigMultiplicative,
  proportional: devigMultiplicative,
  additive: devigAdditive,
  power: devigPower,
  shin: devigShin,
};

/** Power for two-way, multiplicative for multiway — power/Shin get unstable with long tails. */
export function defaultMethod(nOutcomes: number): DevigMethod {
  return nOutcomes <= 2 ? "power" : "multiplicative";
}

export function devig(prices: number[], method?: DevigMethod, decimal = false): number[] {
  if (prices.length < 2) throw new Error("Devig needs at least two outcomes — a one-sided market cannot be devigged");
  const m = method ?? defaultMethod(prices.length);
  const fn = DEVIG_FNS[m];
  if (!fn) throw new Error(`Unknown devig method: ${m}`);
  return fn(asProbs(prices, decimal));
}

export function devigAll(prices: number[], decimal = false): Record<string, number[]> {
  const q = asProbs(prices, decimal);
  return {
    multiplicative: devigMultiplicative(q),
    additive: devigAdditive(q),
    power: devigPower(q),
    shin: devigShin(q),
  };
}

/**
 * How much the methods disagree, in points of probability. When this is wide the
 * honest output is a range, not a point estimate.
 */
export function devigSpread(prices: number[], decimal = false) {
  const all = devigAll(prices, decimal);
  const names = Object.keys(all);
  const n = prices.length;
  const perOutcome = [];
  for (let i = 0; i < n; i++) {
    const vals = names.map((k) => all[k][i]);
    perOutcome.push({ min: Math.min(...vals), max: Math.max(...vals), spreadPts: (Math.max(...vals) - Math.min(...vals)) * 100 });
  }
  const worst = Math.max(...perOutcome.map((o) => o.spreadPts));
  return {
    methods: all,
    perOutcome,
    maxSpreadPts: worst,
    // >1.5 points of probability between methods means quote the range
    disagrees: worst > 1.5,
  };
}

// --- edge and staking ------------------------------------------------------

export function ev(fairProb: number, offeredDecimal: number): number {
  return fairProb * offeredDecimal - 1;
}

export function evFromAmerican(fairProb: number, offeredAmerican: number): number {
  return ev(fairProb, americanToDecimal(offeredAmerican));
}

/** Kelly fraction f = (p*b - q) / b, then divided. Never negative. */
export function kelly(prob: number, offeredDecimal: number, divisor = DEFAULT_KELLY_DIVISOR): number {
  const b = offeredDecimal - 1;
  if (b <= 0) return 0;
  const f = (prob * b - (1 - prob)) / b;
  return f <= 0 ? 0 : f / divisor;
}

export function stakeUnits(prob: number, offeredAmerican: number, divisor = DEFAULT_KELLY_DIVISOR, cap = MAX_STAKE_UNITS) {
  const dec = americanToDecimal(offeredAmerican);
  const f = kelly(prob, dec, divisor);
  const raw = f * 100; // 1u == 1% of bankroll
  return { kellyFraction: f, rawUnits: raw, units: Math.min(raw, cap), capped: raw > cap };
}

export interface EdgeResult {
  fairProb: number;
  fairAmerican: number;
  offeredAmerican: number;
  offeredDecimal: number;
  evPct: number;
  kellyFraction: number;
  stake: number;
  capped: boolean;
  verdict: "BET" | "NO BET";
  note?: string;
}

/**
 * The full edge report: fair price, offered price, EV%, stake. Always all three
 * prices — an EV number with no fair price attached is unauditable.
 */
export function priceEdge(
  fairProb: number,
  offeredAmerican: number,
  opts: { divisor?: number; minEv?: number; cap?: number } = {},
): EdgeResult {
  const { divisor = DEFAULT_KELLY_DIVISOR, minEv = MIN_EV, cap = MAX_STAKE_UNITS } = opts;
  const dec = americanToDecimal(offeredAmerican);
  const evPct = ev(fairProb, dec);
  const st = stakeUnits(fairProb, offeredAmerican, divisor, cap);
  const bet = evPct >= minEv;
  let note: string | undefined;
  if (!bet) note = `EV ${(evPct * 100).toFixed(2)}% is under the ${(minEv * 100).toFixed(0)}% threshold. Noise, not a bet.`;
  else if (st.capped) note = `Kelly wanted ${st.rawUnits.toFixed(2)}u; capped at the ${cap}u ceiling.`;
  return {
    fairProb,
    fairAmerican: probToAmerican(fairProb),
    offeredAmerican,
    offeredDecimal: dec,
    evPct,
    kellyFraction: st.kellyFraction,
    stake: bet ? st.units : 0,
    capped: st.capped,
    verdict: bet ? "BET" : "NO BET",
    note,
  };
}

// --- parlays ---------------------------------------------------------------

export function parlayDecimal(prices: number[]): number {
  return prices.reduce((acc, p) => acc * americanToDecimal(p), 1);
}

/**
 * A parlay of independent legs multiplies the book's hold. This function exists
 * so that claim is always shown with a number attached.
 *
 * `assumedOverround` matters: if you devig each leg off its own posted price you
 * price the vig as truth and the parlay reports 0% hold, which is wrong. Default
 * assumes a standard two-way market per leg.
 */
export function parlayAnalysis(
  prices: number[],
  opts: { fairProbs?: number[]; assumedOverround?: number } = {},
) {
  const STANDARD_TWO_WAY_OVERROUND = 2.0 / americanToDecimal(-110);
  const { fairProbs, assumedOverround = STANDARD_TWO_WAY_OVERROUND } = opts;

  const legDecimals = prices.map(americanToDecimal);
  const rawProbs = prices.map(impliedProb);
  const fair = fairProbs ?? rawProbs.map((q) => q / assumedOverround);

  const combinedDec = legDecimals.reduce((a, b) => a * b, 1);
  const trueProb = fair.reduce((a, b) => a * b, 1);
  const impliedByPayout = 1 / combinedDec;
  const evPct = trueProb * combinedDec - 1;

  const straightHold = 1 - fair.reduce((a, b) => a + b, 0) / rawProbs.reduce((a, b) => a + b, 0);

  return {
    legs: prices.map((p, i) => ({ american: p, decimal: legDecimals[i], rawProb: rawProbs[i], fairProb: fair[i] })),
    combinedDecimal: combinedDec,
    combinedAmerican: decimalToAmerican(combinedDec),
    trueProbability: trueProb,
    impliedProbability: impliedByPayout,
    evPct,
    holdPct: 1 - trueProb / impliedByPayout,
    singleLegHoldPct: Number.isFinite(straightHold) ? straightHold : null,
  };
}

/** Round robins: smaller combos off the same legs, trading upside for variance. */
export function roundRobin(prices: number[], size: number, fairProbs?: number[]) {
  const n = prices.length;
  if (size < 2 || size > n) throw new Error(`Round-robin size must be between 2 and ${n}`);
  const idx = [...Array(n).keys()];
  const combos: number[][] = [];
  const build = (start: number, acc: number[]) => {
    if (acc.length === size) { combos.push([...acc]); return; }
    for (let i = start; i < n; i++) { acc.push(idx[i]); build(i + 1, acc); acc.pop(); }
  };
  build(0, []);
  const tickets = combos.map((c) =>
    parlayAnalysis(c.map((i) => prices[i]), fairProbs ? { fairProbs: c.map((i) => fairProbs[i]) } : {}),
  );
  return {
    ticketCount: tickets.length,
    tickets,
    meanEvPct: tickets.reduce((a, t) => a + t.evPct, 0) / tickets.length,
  };
}

// --- sharp anchoring -------------------------------------------------------

const SHARP_ORDER = ["pinnacle", "circa", "betonline", "bookmaker", "heritage"];

/**
 * Anchor fair probability on the sharpest available price. Soft books are what
 * you bet into, not what you estimate from. Returns the median when no sharp
 * book is present — and says so, because that alone should cut confidence.
 */
export function sharpAnchor(bookPrices: Record<string, number>) {
  const keyed: Record<string, number> = {};
  for (const [k, v] of Object.entries(bookPrices)) keyed[k.toLowerCase().replace(/[^a-z]/g, "")] = v;
  for (const book of SHARP_ORDER) {
    if (book in keyed) return { book, american: keyed[book], isSharp: true, note: `Anchored on ${book}.` };
  }
  const vals = Object.values(bookPrices).map(impliedProb).sort((a, b) => a - b);
  if (!vals.length) throw new Error("No prices supplied");
  const mid = vals.length % 2 ? vals[(vals.length - 1) / 2] : (vals[vals.length / 2 - 1] + vals[vals.length / 2]) / 2;
  return {
    book: "market median",
    american: probToAmerican(mid),
    isSharp: false,
    note: "No sharp book available — anchored on the market median. Treat the edge as unconfirmed and cut confidence.",
  };
}

// --- closing line value ----------------------------------------------------

/** CLV is the only honest scoreboard. Positive means you beat the close. */
export function clv(takenAmerican: number, closingAmerican: number) {
  const pTaken = impliedProb(takenAmerican);
  const pClose = impliedProb(closingAmerican);
  return {
    takenAmerican,
    closingAmerican,
    takenImplied: pTaken,
    closingImplied: pClose,
    clvPts: (pClose - pTaken) * 100,
    beatClose: pClose > pTaken,
    evVsClose: americanToDecimal(takenAmerican) * pClose - 1,
  };
}
