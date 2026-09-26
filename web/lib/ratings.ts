/**
 * Ratings spine and projection discipline.
 *
 * Two hard rules from CLAUDE.md are ENFORCED here in code rather than left to
 * the model's judgement, because in both cases judgement already failed:
 *
 *  §3.4b — College football spreads require a ratings spine (SP+, FPI or
 *          equivalent). A points-per-game model on 136 teams with wildly
 *          different schedules carries almost no signal: one produced a
 *          pick'em against a market of Miami -20.5. `ratingsSpread` REFUSES
 *          to return a number without ratings instead of returning a bad one.
 *
 *  §3.2a — Run BOTH projection forms, always. The spread between them IS the
 *          uncertainty, and when they disagree by more than ~10 points on a
 *          total there is no playable number. DET @ BUF 2026-09-17: additive
 *          said 50.8, multiplicative said 61, I called 61 "absurd", bet 2u on
 *          the under, and the game went 72. `projectBoth` will not let either
 *          form be discarded.
 */

import { normCdf } from "./simulate";

// ---------------------------------------------------------------------------
// Priors. These are priors, not measurements, and are labelled as such wherever
// they surface. Override them when you have a measured value.
// ---------------------------------------------------------------------------

/** SD of actual margin around a ratings-based projection. CFB runs wider than the NFL. */
export const CFB_MARGIN_SD = 16.5;
export const NFL_MARGIN_SD = 13.5;

/**
 * Points per team per game. NFL was corrected upward from 22.9 (a 2025 figure)
 * after Week 1 of 2026 averaged 49.44 points per game — 24.72 per team. A stale
 * league mean biases every multiplicative projection low, which is exactly the
 * direction the DET-BUF miss ran.
 */
export const NFL_LEAGUE_MEAN_PPG = 23.8;
export const CFB_LEAGUE_MEAN_PPG = 27.5;

export type Sport = "nfl" | "cfb";

function marginSd(sport: Sport): number {
  return sport === "cfb" ? CFB_MARGIN_SD : NFL_MARGIN_SD;
}
function leagueMeanFor(sport: Sport): number {
  return sport === "cfb" ? CFB_LEAGUE_MEAN_PPG : NFL_LEAGUE_MEAN_PPG;
}

// ---------------------------------------------------------------------------
// Ratings -> spread
// ---------------------------------------------------------------------------

export interface RatingsSpreadInput {
  homeTeam: string;
  awayTeam: string;
  /** Points above average, e.g. SP+ or FPI. Omit either and this refuses to price. */
  homeRating?: number | null;
  awayRating?: number | null;
  ratingName?: string;
  /** Home-field points. Pass the venue-specific number from `homeEdge`, not a flat 2.5. */
  hfa?: number;
  neutralSite?: boolean;
  /** The market's home spread, e.g. -20.5 means home favored by 20.5. */
  marketSpread?: number | null;
  sport?: Sport;
  /** SD of margin around the projection. Defaults to the sport prior. */
  sd?: number;
}

export interface RatingsSpreadResult {
  playable: boolean;
  reason?: string;
  homeTeam: string;
  awayTeam: string;
  ratingName?: string;
  projectedMargin?: number;
  fairHomeSpread?: number;
  marketSpread?: number | null;
  disagreement?: number;
  homeCoverProb?: number;
  awayCoverProb?: number;
  pushProb?: number;
  hfaUsed?: number;
  sdUsed?: number;
  leanSide?: string;
  notes: string[];
}

/**
 * Convert a ratings differential into a fair spread, and compare it to market.
 *
 * Sign convention: `projectedMargin` is from the HOME side, positive = home
 * favored. `fairHomeSpread` is the number a book would post, so it is the
 * negative of the margin.
 */
export function ratingsSpread(input: RatingsSpreadInput): RatingsSpreadResult {
  const {
    homeTeam, awayTeam, homeRating, awayRating,
    ratingName = "rating", neutralSite = false,
    marketSpread = null, sport = "cfb",
  } = input;
  const notes: string[] = [];

  // §3.4b — no spine, no number. This is the whole point of the module.
  const missing: string[] = [];
  if (homeRating == null || !Number.isFinite(homeRating)) missing.push(homeTeam);
  if (awayRating == null || !Number.isFinite(awayRating)) missing.push(awayTeam);
  if (missing.length) {
    return {
      playable: false,
      reason:
        `No ${ratingName} available for ${missing.join(" and ")}. ` +
        "Per CLAUDE.md 3.4b a side or spread number requires a ratings spine (SP+, FPI or " +
        "equivalent); points-per-game projection does not work in this sport. " +
        "Say the spine is missing rather than publishing a spread. Totals may still be " +
        "reachable via projectBoth if the forms converge.",
      homeTeam, awayTeam, ratingName,
      notes: ["Spine missing — no side published."],
    };
  }

  const hfa = neutralSite ? 0 : (input.hfa ?? (sport === "cfb" ? 2.5 : 2.0));
  if (neutralSite) notes.push("Neutral site — no home-field points applied.");
  else if (input.hfa == null) {
    notes.push(
      `No venue-specific home-field number supplied, so a flat ${hfa} was used. ` +
        "In college football HFA is NOT a constant — the spread between the hardest place " +
        "to play and an empty stadium is worth four points or more. Pass homeEdge() instead.",
    );
  }

  const sd = input.sd ?? marginSd(sport);
  const projectedMargin = homeRating! - awayRating! + hfa;
  const fairHomeSpread = -projectedMargin;

  // P(home margin > -spread), i.e. home covers its own posted number.
  let homeCoverProb: number | undefined;
  let awayCoverProb: number | undefined;
  let pushProb: number | undefined;
  let disagreement: number | undefined;
  let leanSide: string | undefined;

  if (marketSpread != null && Number.isFinite(marketSpread)) {
    const needed = -marketSpread;               // margin the home team must exceed
    homeCoverProb = 1 - normCdf((needed - projectedMargin) / sd);
    // A whole-number spread can push; a half-point cannot.
    const isWhole = Math.abs(marketSpread % 1) < 1e-9;
    pushProb = isWhole ? pushMass(needed, projectedMargin, sd) : 0;
    awayCoverProb = 1 - homeCoverProb - pushProb;
    disagreement = fairHomeSpread - marketSpread;
    // disagreement < 0 means our fair number has home favored by MORE than market.
    if (Math.abs(disagreement) < 0.5) {
      leanSide = "none — inside half a point of the market";
      notes.push("Our number and the market agree. No side.");
    } else {
      leanSide = disagreement < 0 ? homeTeam : awayTeam;
    }
    if (Math.abs(disagreement) >= 3) {
      notes.push(
        `Our number is ${Math.abs(disagreement).toFixed(1)} points off the market. ` +
          "The base rate says the market is right and the model is wrong. Re-check the " +
          "ratings, the HFA and any injury news before acting on a gap this size.",
      );
    }
  }

  notes.push(
    sport === "cfb"
      ? "CFB key numbers are FLATTER than the NFL's — take the better price over the better number."
      : "NFL key numbers 3 and 7 dominate. Crossing the 3 is worth 25-30 cents, not 10.",
  );
  notes.push(`Margin SD of ${sd} is a prior, not a measurement.`);

  return {
    playable: true,
    homeTeam, awayTeam, ratingName,
    projectedMargin, fairHomeSpread, marketSpread, disagreement,
    homeCoverProb, awayCoverProb, pushProb,
    hfaUsed: hfa, sdUsed: sd, leanSide, notes,
  };
}

/** Approximate mass on an exact whole-number margin, for push probability. */
function pushMass(k: number, mean: number, sd: number): number {
  return normCdf((k + 0.5 - mean) / sd) - normCdf((k - 0.5 - mean) / sd);
}

// ---------------------------------------------------------------------------
// Both projection forms, with the convergence gate
// ---------------------------------------------------------------------------

export interface BothFormsInput {
  homeTeam: string;
  awayTeam: string;
  /** Home offense points/game. */
  homeOff: number;
  /** Home defense points allowed/game. */
  homeDefAllowed: number;
  awayOff: number;
  awayDefAllowed: number;
  leagueMean?: number;
  sport?: Sport;
  marketTotal?: number | null;
  /** Divergence on the total above which nothing is playable. */
  gate?: number;
  /**
   * Inputs you could not retrieve (pace, weather, a starter's status...). Any
   * entry here caps the stake at 1u per CLAUDE.md 3.2a — writing a risk down is
   * not the same as pricing it.
   */
  unavailableInputs?: string[];
}

export interface BothFormsResult {
  playable: boolean;
  homeTeam: string;
  awayTeam: string;
  additive: { home: number; away: number; total: number };
  multiplicative: { home: number; away: number; total: number };
  /** Midpoint of the two forms. Use the RANGE, not this, as the projection. */
  midpoint: number;
  range: [number, number];
  divergence: number;
  gate: number;
  marketTotal?: number | null;
  leanVsMarket?: string;
  maxStakeUnits: number;
  notes: string[];
  reason?: string;
}

/**
 * Run both projection forms and report the range. Neither form may be discarded
 * because its answer "looks implausible" — that is aesthetics overriding a model,
 * and it has already cost real money.
 */
export function projectBoth(input: BothFormsInput): BothFormsResult {
  const {
    homeTeam, awayTeam, homeOff, homeDefAllowed, awayOff, awayDefAllowed,
    sport = "nfl", marketTotal = null, gate = 10,
    unavailableInputs = [],
  } = input;
  const leagueMean = input.leagueMean ?? leagueMeanFor(sport);
  const notes: string[] = [];

  // Additive: stable, shrinks toward the mean.
  const addHome = (homeOff + awayDefAllowed) / 2;
  const addAway = (awayOff + homeDefAllowed) / 2;
  // Multiplicative: compounds when a good offense meets a bad defense.
  const mulHome = (homeOff * awayDefAllowed) / leagueMean;
  const mulAway = (awayOff * homeDefAllowed) / leagueMean;

  const addTotal = addHome + addAway;
  const mulTotal = mulHome + mulAway;
  const divergence = Math.abs(addTotal - mulTotal);
  const lo = Math.min(addTotal, mulTotal);
  const hi = Math.max(addTotal, mulTotal);
  const midpoint = (addTotal + mulTotal) / 2;

  const playable = divergence <= gate;
  if (!playable) {
    notes.push(
      `The two forms disagree by ${divergence.toFixed(1)} points, more than the ${gate}-point ` +
        "gate. There is no playable number here — say so and move on, however tempting the " +
        "market price looks.",
    );
  } else {
    notes.push(
      `The forms land ${divergence.toFixed(1)} points apart. Convergence IS the confidence ` +
        "signal, so quote the range, not the midpoint.",
    );
  }

  let leanVsMarket: string | undefined;
  if (marketTotal != null && Number.isFinite(marketTotal)) {
    if (marketTotal < lo) leanVsMarket = `OVER — both forms sit above ${marketTotal}`;
    else if (marketTotal > hi) leanVsMarket = `UNDER — both forms sit below ${marketTotal}`;
    else {
      leanVsMarket = `none — ${marketTotal} falls INSIDE the projection range ` +
        `[${lo.toFixed(1)}, ${hi.toFixed(1)}]`;
      notes.push(
        "The market total sits between the two forms. One form is on each side of the " +
          "line, so you do not have a directional read no matter which one you prefer.",
      );
    }
  }

  // §3.2a staking rule.
  let maxStakeUnits = 2.0;
  if (unavailableInputs.length) {
    maxStakeUnits = 1.0;
    notes.push(
      `Stake CAPPED at 1u: ${unavailableInputs.join(", ")} ` +
        `${unavailableInputs.length === 1 ? "was" : "were"} unavailable. ` +
        "Naming a risk in a sensitivity table is not the same as pricing it.",
    );
  }
  if (!playable) maxStakeUnits = 0;

  notes.push(
    "Never shrink an adjustment because the market has already absorbed it — the market's " +
      "absorption lives in the market price, and shrinking your own prior double-counts it.",
  );

  return {
    playable, homeTeam, awayTeam,
    additive: { home: addHome, away: addAway, total: addTotal },
    multiplicative: { home: mulHome, away: mulAway, total: mulTotal },
    midpoint, range: [lo, hi], divergence, gate,
    marketTotal, leanVsMarket, maxStakeUnits, notes,
    reason: playable ? undefined : "Projection forms diverge beyond the gate.",
  };
}

/**
 * Turn a projected total and margin into projected team totals.
 * Kept separate so a total read and a side read cannot silently contaminate
 * each other.
 */
export function teamTotals(total: number, homeMargin: number) {
  const home = (total + homeMargin) / 2;
  return { home, away: total - home };
}
