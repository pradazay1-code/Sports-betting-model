/**
 * The bet log. An untracked bet is an unlearned lesson.
 *
 * Deliberately localStorage-backed: no database to provision, and the log is the
 * user's own data. The point of it is not the win/loss column — that is noise at
 * any sample size a person actually reaches. The point is CLV, which is why
 * `summarize` reports closing-line value first and puts the record behind a
 * sample-size caveat.
 */

import { impliedProb, americanToDecimal } from "./odds";
import { realityCheck, requiredSampleSize } from "./backtest";

export const STORAGE_KEY = "desk.betlog.v1";

export type BetResult = "pending" | "win" | "loss" | "push" | "void";

export interface Bet {
  id: string;
  placedAt: string;          // ISO
  sport: string;
  event: string;             // "DET @ BUF"
  market: string;            // "Total", "Spread", "Shakir receptions"
  selection: string;         // "Under 54.5", "BUF -2.5", "Over 2.5"
  takenAmerican: number;
  book: string;
  stakeUnits: number;
  fairProb?: number | null;      // what you devigged it to when you bet
  closingAmerican?: number | null;
  result: BetResult;
  notes?: string;
}

export function newBet(partial: Partial<Bet> = {}): Bet {
  return {
    id: (globalThis.crypto?.randomUUID?.() ?? `b${Date.now()}${Math.random().toString(36).slice(2, 8)}`),
    placedAt: new Date().toISOString(),
    sport: "", event: "", market: "", selection: "",
    takenAmerican: -110, book: "", stakeUnits: 1,
    fairProb: null, closingAmerican: null, result: "pending",
    ...partial,
  };
}

/** Units won or lost. Pending and void return 0; a push returns 0 by definition. */
export function betProfit(bet: Bet): number {
  if (bet.result === "win") return bet.stakeUnits * (americanToDecimal(bet.takenAmerican) - 1);
  if (bet.result === "loss") return -bet.stakeUnits;
  return 0;
}

/** Probability points gained against the close. Positive means you beat it. */
export function betClvPts(bet: Bet): number | null {
  if (bet.closingAmerican == null || !Number.isFinite(bet.closingAmerican)) return null;
  return (impliedProb(bet.closingAmerican) - impliedProb(bet.takenAmerican)) * 100;
}

/** EV of the bet measured against the closing price rather than your own model. */
export function betEvVsClose(bet: Bet): number | null {
  if (bet.closingAmerican == null || !Number.isFinite(bet.closingAmerican)) return null;
  return americanToDecimal(bet.takenAmerican) * impliedProb(bet.closingAmerican) - 1;
}

export interface LogSummary {
  total: number;
  settled: number;
  pending: number;
  wins: number;
  losses: number;
  pushes: number;
  unitsStaked: number;
  unitsPL: number;
  roiPct: number | null;
  hitRatePct: number | null;
  /** CLV — the scoreboard that matters. */
  clv: {
    tracked: number;
    beatClose: number;
    beatClosePct: number | null;
    meanClvPts: number | null;
    meanEvVsClosePct: number | null;
  };
  record: ReturnType<typeof realityCheck> | null;
  sampleSizeNeeded: number | null;
  verdict: string;
  bySport: Array<{ sport: string; n: number; unitsPL: number; meanClvPts: number | null }>;
}

export function summarize(bets: Bet[]): LogSummary {
  const settledBets = bets.filter((b) => b.result === "win" || b.result === "loss");
  const wins = bets.filter((b) => b.result === "win").length;
  const losses = bets.filter((b) => b.result === "loss").length;
  const pushes = bets.filter((b) => b.result === "push").length;
  const pending = bets.filter((b) => b.result === "pending").length;

  const unitsStaked = settledBets.reduce((a, b) => a + b.stakeUnits, 0);
  const unitsPL = bets.reduce((a, b) => a + betProfit(b), 0);

  const clvVals = bets.map(betClvPts).filter((v): v is number => v != null);
  const evVals = bets.map(betEvVsClose).filter((v): v is number => v != null);
  const beatClose = clvVals.filter((v) => v > 0).length;

  const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);

  const sports = [...new Set(bets.map((b) => b.sport || "unspecified"))];
  const bySport = sports.map((sport) => {
    const rows = bets.filter((b) => (b.sport || "unspecified") === sport);
    return {
      sport,
      n: rows.length,
      unitsPL: rows.reduce((a, b) => a + betProfit(b), 0),
      meanClvPts: mean(rows.map(betClvPts).filter((v): v is number => v != null)),
    };
  }).sort((a, b) => b.n - a.n);

  const settled = settledBets.length;
  const record = settled > 0 ? realityCheck(wins, losses) : null;
  const hitRatePct = settled > 0 ? (wins / settled) * 100 : null;
  const roiPct = unitsStaked > 0 ? (unitsPL / unitsStaked) * 100 : null;

  // The sample size that would be needed to establish the rate actually observed.
  let sampleSizeNeeded: number | null = null;
  if (settled > 0) {
    const observed = wins / settled;
    const r = requiredSampleSize(observed, -110);
    sampleSizeNeeded = r.nRequired ?? null;
  }

  return {
    total: bets.length, settled, pending, wins, losses, pushes,
    unitsStaked, unitsPL, roiPct, hitRatePct,
    clv: {
      tracked: clvVals.length,
      beatClose,
      beatClosePct: clvVals.length ? (beatClose / clvVals.length) * 100 : null,
      meanClvPts: mean(clvVals),
      meanEvVsClosePct: evVals.length ? mean(evVals)! * 100 : null,
    },
    record, sampleSizeNeeded,
    verdict: verdictFor(clvVals, mean(clvVals), settled, sampleSizeNeeded),
    bySport,
  };
}

function verdictFor(
  clvVals: number[], meanClv: number | null, settled: number, needed: number | null,
): string {
  if (clvVals.length < 10) {
    return `Only ${clvVals.length} bet${clvVals.length === 1 ? "" : "s"} have a closing price recorded. ` +
      "CLV is the only honest scoreboard, so fill those in — the win/loss column cannot tell you " +
      "anything at this sample size.";
  }
  if (meanClv == null) return "No CLV recorded.";
  if (meanClv > 0.5) {
    return `Mean CLV of +${meanClv.toFixed(2)} probability points across ${clvVals.length} bets. ` +
      "Beating the close is the signal that you are actually finding edges; short-run results are noise " +
      "by comparison. Keep doing exactly this.";
  }
  if (meanClv < -0.5) {
    return `Mean CLV of ${meanClv.toFixed(2)} probability points across ${clvVals.length} bets. ` +
      "Consistently closing worse than you bet means no edge, whatever the record says. " +
      "Bet later, shop harder, or accept that these markets are beating you.";
  }
  const tail = needed && settled
    ? ` Establishing the rate you have observed would take roughly ${needed.toLocaleString()} bets; you have ${settled} settled.`
    : "";
  return `Mean CLV of ${meanClv >= 0 ? "+" : ""}${meanClv.toFixed(2)} points — essentially flat, ` +
    `which is what betting into the number the market lands on looks like.${tail}`;
}

// ---------------------------------------------------------------------------
// Persistence. Every access is wrapped: storage can be blocked or cleared, and
// the page must render correctly when it comes back empty.
// ---------------------------------------------------------------------------

export function loadBets(): Bet[] {
  try {
    const raw = globalThis.localStorage?.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((b) => b && typeof b.id === "string");
  } catch {
    return [];
  }
}

export function saveBets(bets: Bet[]): boolean {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify(bets));
    return true;
  } catch {
    return false;
  }
}

const CSV_COLUMNS = [
  "placedAt", "sport", "event", "market", "selection", "book",
  "takenAmerican", "closingAmerican", "stakeUnits", "fairProb", "result",
  "profitUnits", "clvPts", "evVsClosePct", "notes",
] as const;

function csvCell(v: unknown): string {
  if (v == null) return "";
  const s = String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCSV(bets: Bet[]): string {
  const rows = bets.map((b) => {
    const clv = betClvPts(b);
    const ev = betEvVsClose(b);
    return [
      b.placedAt, b.sport, b.event, b.market, b.selection, b.book,
      b.takenAmerican, b.closingAmerican ?? "", b.stakeUnits, b.fairProb ?? "", b.result,
      betProfit(b).toFixed(4),
      clv == null ? "" : clv.toFixed(4),
      ev == null ? "" : (ev * 100).toFixed(4),
      b.notes ?? "",
    ].map(csvCell).join(",");
  });
  return [CSV_COLUMNS.join(","), ...rows].join("\n");
}
