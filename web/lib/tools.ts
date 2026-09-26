/**
 * The agent's calculators. Every number in an answer should come from one of
 * these rather than from prose arithmetic.
 *
 * Plain JSON-Schema tool definitions + a single dispatcher, so the API route can
 * own the agent loop (and therefore own `pause_turn` handling, which the SDK's
 * tool runner does not do for server tools).
 */
import type Anthropic from "@anthropic-ai/sdk";
import * as O from "./odds";
import * as S from "./simulate";
import * as R from "./ratings";
import * as B from "./backtest";
import * as V from "./venues";

export const DESK_TOOLS: Anthropic.Tool[] = [
  {
    name: "devig",
    description:
      "Remove the vig from a market and return fair probabilities and fair American prices. " +
      "Runs all four methods (multiplicative, additive, power, Shin) and reports how much they " +
      "disagree. Power is the default for two-way markets, multiplicative for multiway. " +
      "Requires at least two outcomes — a one-sided market cannot be devigged. Use this before " +
      "any edge claim.",
    input_schema: {
      type: "object",
      properties: {
        labels: { type: "array", items: { type: "string" }, description: "Outcome names, same order as prices." },
        prices: { type: "array", items: { type: "number" }, description: "American odds for every outcome in the market." },
        method: { type: "string", enum: ["power", "multiplicative", "additive", "shin"], description: "Optional override; defaults to power for 2 outcomes, multiplicative for more." },
      },
      required: ["labels", "prices"],
      additionalProperties: false,
    },
  },
  {
    name: "price_edge",
    description:
      "Given a fair probability and an offered American price, return EV%, quarter-Kelly stake in " +
      "units (2u hard cap), and a BET / NO BET verdict against the 2% EV floor. Also returns the " +
      "fair American price so the three-number report (fair / offered / EV) is always available.",
    input_schema: {
      type: "object",
      properties: {
        fair_prob: { type: "number", description: "Your fair probability, 0-1." },
        offered_american: { type: "number", description: "The price you can actually bet." },
        min_ev: { type: "number", description: "EV floor. Default 0.02 for sides/totals; use 0.05 for props." },
      },
      required: ["fair_prob", "offered_american"],
      additionalProperties: false,
    },
  },
  {
    name: "parlay",
    description:
      "Price a parlay honestly: each leg's fair probability, combined true probability, offered " +
      "payout, implied probability, resulting EV, and the book's hold. Shows how a parlay of " +
      "independent legs multiplies the hold. Pass fair_probs when you have devigged the legs " +
      "yourself; otherwise it assumes a standard two-way overround per leg.",
    input_schema: {
      type: "object",
      properties: {
        prices: { type: "array", items: { type: "number" }, description: "American odds per leg." },
        fair_probs: { type: "array", items: { type: "number" }, description: "Optional devigged probability per leg." },
        round_robin_size: { type: "number", description: "Optional: also price all combinations of this size." },
      },
      required: ["prices"],
      additionalProperties: false,
    },
  },
  {
    name: "simulate_game",
    description:
      "Drive-level Monte Carlo. Give each team's projected POINTS and it returns the score, total " +
      "and margin distributions, fair spread, win probability, P(cover) at any spreads, P(over) at " +
      "any totals, key-number mass, and team totals. Scores are built from real 3s and 7s so key " +
      "numbers are reproduced rather than smoothed away. Use drives_per_team 11 for NFL, 12.5 for " +
      "college football.",
    input_schema: {
      type: "object",
      properties: {
        home_name: { type: "string" },
        away_name: { type: "string" },
        home_points: { type: "number", description: "Your projected points for the home team." },
        away_points: { type: "number", description: "Your projected points for the away team." },
        drives_per_team: { type: "number", description: "11 for NFL, 12.5 for CFB. Default 11." },
        home_td_share: { type: "number", description: "Share of scoring drives ending in a TD. League ~0.60." },
        away_td_share: { type: "number" },
        spreads: { type: "array", items: { type: "number" }, description: "Home spreads to price, e.g. [-6.5, -3]." },
        totals: { type: "array", items: { type: "number" }, description: "Totals to price." },
        key_numbers: { type: "array", items: { type: "number" }, description: "Absolute margins to report mass on, e.g. [3,4,6,7,10]." },
        lead_thresholds: { type: "array", items: { type: "number" }, description: "If set, also runs a path simulation and returns P(each side leads by >= k at ANY point). Use for live-lead and instant-win promos." },
        iterations: { type: "number", description: "Default 40000." },
      },
      required: ["home_name", "away_name", "home_points", "away_points"],
      additionalProperties: false,
    },
  },
  {
    name: "yardage_prop",
    description:
      "Price a yardage prop correctly. CRITICAL: a book's yardage line sits near the MEDIAN and " +
      "these distributions are right-skewed, so this returns the mean the LINE implies alongside " +
      "your projected mean. A gap under ~5 yards is noise, not an edge. Typical cv: 0.42 RB " +
      "rushing, 0.28 QB passing, 0.52-0.62 receiving.",
    input_schema: {
      type: "object",
      properties: {
        label: { type: "string" },
        line: { type: "number" },
        projected_mean: { type: "number", description: "Your projected mean, e.g. carries x yards-per-carry." },
        cv: { type: "number", description: "Coefficient of variation. 0.42 RB rush, 0.28 QB pass, 0.55 receiving." },
        offered_american: { type: "number", description: "Optional price to compute EV against." },
        side: { type: "string", enum: ["over", "under"] },
      },
      required: ["label", "line", "projected_mean", "cv"],
      additionalProperties: false,
    },
  },
  {
    name: "reception_prop",
    description:
      "Price a receptions prop. Receptions are NOT Poisson — they are capped by targets, and target " +
      "counts have their own distribution. Poisson forces variance = mean; the real variance is " +
      "E[T]p(1-p) + Var(T)p^2, which is BELOW the mean whenever target SD < sqrt(E[targets]). At " +
      "realistic starter target SDs that makes receptions under-dispersed, so Poisson UNDERSTATES the " +
      "chance of clearing a modest line; the direction flips for a volatile target share. This draws " +
      "targets from a gamma then catches binomially and reports which regime you are in. Also use it " +
      "for any count prop with a volume cap. target_sd is the input the answer turns on — state it.",
    input_schema: {
      type: "object",
      properties: {
        label: { type: "string" },
        line: { type: "number", description: "The market line, e.g. 4.5." },
        mean_targets: { type: "number" },
        target_sd: { type: "number", description: "SD of targets. Roughly 2.0-2.8 for a starter." },
        catch_rate: { type: "number", description: "Career/season catch rate, 0-1." },
        offered_american: { type: "number" },
        side: { type: "string", enum: ["over", "under"] },
      },
      required: ["label", "line", "mean_targets", "catch_rate"],
      additionalProperties: false,
    },
  },
  {
    name: "sharp_anchor",
    description:
      "Pick the sharpest price from a set of book prices, in the order Pinnacle > Circa > " +
      "BetOnline/Bookmaker/Heritage > market median. Soft books are what you bet into, not what you " +
      "estimate from. Says explicitly when no sharp book was available, which should cut confidence.",
    input_schema: {
      type: "object",
      properties: {
        book_prices: { type: "object", description: 'Map of book name to American price, e.g. {"pinnacle": -118, "draftkings": -110}.', additionalProperties: { type: "number" } },
      },
      required: ["book_prices"],
      additionalProperties: false,
    },
  },
  {
    name: "touchdown_board",
    description:
      "Devig an anytime-touchdown board as a multiway market and AUDIT it for the two failure modes " +
      "that make it unusable: prices from mixed markets (anytime vs first-TD), and an incomplete " +
      "board. Converts each price to a Poisson rate, sums them, and compares to the game's projected " +
      "touchdowns. If the listed players account for far fewer touchdowns than the game projects, " +
      "scaling up assigns the missing scores to whoever you have prices for — the tool will tell you " +
      "so and you must report 'no edge found' rather than a board of fake edges.",
    input_schema: {
      type: "object",
      properties: {
        players: {
          type: "array",
          description: "Each listed player and their anytime-TD American price.",
          items: {
            type: "object",
            properties: { name: { type: "string" }, american: { type: "number" } },
            required: ["name", "american"],
            additionalProperties: false,
          },
        },
        projected_game_tds: { type: "number", description: "Total offensive touchdowns your model projects for the game." },
        reserve_for_unlisted: { type: "number", description: "Share of touchdowns to reserve for players not on your list. Default 0.15." },
      },
      required: ["players", "projected_game_tds"],
      additionalProperties: false,
    },
  },
  {
    name: "ratings_spread",
    description:
      "Convert a ratings differential (SP+, FPI or equivalent) plus venue-specific home field into a " +
      "fair spread, and compare it to the market. REQUIRED for any college football side or spread: " +
      "points-per-game projection does not work with 136 teams on wildly different schedules, and this " +
      "tool REFUSES to return a number when a rating is missing rather than returning a bad one. If it " +
      "refuses, say the ratings spine is missing and do not publish a side — totals may still be " +
      "reachable via project_both.",
    input_schema: {
      type: "object",
      properties: {
        home_team: { type: "string" },
        away_team: { type: "string" },
        home_rating: { type: "number", description: "Points above average, e.g. SP+. Omit if you could not retrieve it — do NOT invent one." },
        away_rating: { type: "number", description: "Points above average for the away team. Omit if unavailable." },
        rating_name: { type: "string", description: "What rating this is, e.g. 'SP+' or 'FPI'." },
        hfa: { type: "number", description: "Home-field points from venue_edge. Omit only if you have no venue data; a flat number will be flagged." },
        neutral_site: { type: "boolean" },
        market_spread: { type: "number", description: "The market's HOME spread. -20.5 means home favored by 20.5." },
        sport: { type: "string", enum: ["cfb", "nfl"] },
      },
      required: ["home_team", "away_team"],
      additionalProperties: false,
    },
  },
  {
    name: "project_both",
    description:
      "Project a total by running BOTH projection forms — additive (X_off + Y_def)/2 and multiplicative " +
      "(X_off * Y_def / league_mean) — and report the range. The spread between the forms IS the " +
      "uncertainty. Use this for every total. It enforces three rules learned from a 21-point miss: " +
      "neither form may be discarded for looking implausible; when the forms diverge past the gate " +
      "there is no playable number; and when the market total falls INSIDE the range there is no " +
      "directional read regardless of which form you prefer. Also caps the stake at 1u when you name " +
      "an input you could not retrieve.",
    input_schema: {
      type: "object",
      properties: {
        home_team: { type: "string" },
        away_team: { type: "string" },
        home_off: { type: "number", description: "Home team points scored per game." },
        home_def_allowed: { type: "number", description: "Home team points allowed per game." },
        away_off: { type: "number" },
        away_def_allowed: { type: "number" },
        league_mean: { type: "number", description: "League points per team per game. Defaults to the sport constant." },
        sport: { type: "string", enum: ["nfl", "cfb"] },
        market_total: { type: "number", description: "The posted total, so the tool can tell you whether a directional read exists." },
        gate: { type: "number", description: "Divergence on the total above which nothing is playable. Default 10." },
        unavailable_inputs: {
          type: "array", items: { type: "string" },
          description: "Inputs you could NOT retrieve (pace, weather, a starter's status). Any entry caps the stake at 1u. List them honestly.",
        },
      },
      required: ["home_team", "away_team", "home_off", "home_def_allowed", "away_off", "away_def_allowed"],
      additionalProperties: false,
    },
  },
  {
    name: "venue_edge",
    description:
      "Venue-specific home-field advantage for college football, with crowd and altitude reported " +
      "SEPARATELY so they are not double-counted. Home field is not a constant in this sport — the gap " +
      "between the hardest place to play and an empty stadium is worth four points or more, and most " +
      "public models apply a flat 2.5 to everything. Altitude is priced on the DIFFERENTIAL, not raw " +
      "elevation, and is a fourth-quarter effect that belongs in second-half and live markets. Warns " +
      "loudly instead of inventing a number when a venue is not in the database.",
    input_schema: {
      type: "object",
      properties: {
        home_team: { type: "string" },
        away_team: { type: "string", description: "Needed to price the altitude differential. A high-altitude visitor carries its own acclimation." },
        fcs: { type: "boolean", description: "True for an FCS home venue, which uses a higher baseline." },
      },
      required: ["home_team"],
      additionalProperties: false,
    },
  },
  {
    name: "reality_check",
    description:
      "What a win-loss record actually proves, and how long it takes to prove an edge. Use this whenever " +
      "a user presents a record, is on tilt, is chasing, or believes a cold streak means the process is " +
      "broken. Returns the confidence interval on the true hit rate, a one-sided p-value against " +
      "break-even, how many bets a claimed ROI would need, and a Monte Carlo of the drawdown a genuinely " +
      "winning bettor still experiences. Read 'proves_an_edge' as 'clears a one-sided test at this alpha', " +
      "NOT as 'has an edge' — and remember the p-value assumes this was the only record ever tested.",
    input_schema: {
      type: "object",
      properties: {
        wins: { type: "number" },
        losses: { type: "number" },
        american: { type: "number", description: "Average price of the bets. Default -110." },
        true_prob: { type: "number", description: "A hit rate to run the sample-size and drawdown math on, e.g. 0.55." },
        n_bets: { type: "number", description: "Horizon for the drawdown simulation. Default 500." },
      },
      required: [],
      additionalProperties: false,
    },
  },
  {
    name: "clv",
    description:
      "Closing line value: compare the price you took against the closing price. This is the only honest " +
      "scoreboard — short-run win/loss is noise. Reports the probability points gained or lost and the EV " +
      "of the bet measured against the close.",
    input_schema: {
      type: "object",
      properties: {
        taken_american: { type: "number", description: "The price you actually got." },
        closing_american: { type: "number", description: "The closing price at the same book or the sharp book." },
      },
      required: ["taken_american", "closing_american"],
      additionalProperties: false,
    },
  },
];

const r2 = (x: number) => Math.round(x * 10000) / 10000;
const am = (p: number) => (p > 0 && p < 1 ? Math.round(O.probToAmerican(p)) : null);

/**
 * The tool surface grew inconsistent naming (`home_name` in simulate_game vs
 * `home_team` elsewhere). Rather than let a plausible-but-wrong key through,
 * accept both spellings and validate required fields loudly.
 */
const ALIASES: Record<string, string[]> = {
  home_name: ["home_team"],
  away_name: ["away_team"],
  home_team: ["home_name"],
  away_team: ["away_name"],
  prices: ["legs"],
};

function normalizeInput(name: string, input: Record<string, unknown>): Record<string, unknown> {
  const def = DESK_TOOLS.find((d) => d.name === name);
  if (!def) throw new Error(`Unknown tool: ${name}`);
  const schema = def.input_schema as { properties?: Record<string, unknown>; required?: string[] };
  const props = Object.keys(schema.properties ?? {});
  const out: Record<string, unknown> = { ...input };

  // Fill a declared field from an accepted alias when the caller used the other spelling.
  for (const prop of props) {
    if (out[prop] !== undefined) continue;
    for (const alt of ALIASES[prop] ?? []) {
      if (out[alt] !== undefined) { out[prop] = out[alt]; break; }
    }
  }

  const missing = (schema.required ?? []).filter((k) => out[k] === undefined || out[k] === null);
  if (missing.length) {
    throw new Error(
      `Tool '${name}' is missing required field(s): ${missing.join(", ")}. ` +
        `Accepted fields: ${props.join(", ")}. ` +
        "Re-call the tool with those fields rather than reporting a number without them.",
    );
  }
  return out;
}

export function runTool(name: string, rawInput: Record<string, unknown>): unknown {
  const input = normalizeInput(name, rawInput);
  switch (name) {
    case "devig": {
      const { labels, prices, method } = input as { labels: string[]; prices: number[]; method?: O.DevigMethod };
      const used = method ?? O.defaultMethod(prices.length);
      const fair = O.devig(prices, used);
      const spread = O.devigSpread(prices);
      return {
        method_used: used,
        outcomes: labels.map((l, i) => ({
          label: l, posted: prices[i], raw_implied: r2(O.impliedProb(prices[i])),
          fair_prob: r2(fair[i]), fair_american: am(fair[i]),
        })),
        overround: r2(O.overround(prices)),
        hold_pct: r2(O.hold(prices) * 100),
        method_disagreement_pts: r2(spread.maxSpreadPts),
        methods_disagree: spread.disagrees,
        note: spread.disagrees
          ? "Methods disagree by more than 1.5 points of probability. Quote the range, not a point estimate, and let it widen your uncertainty."
          : "Methods agree closely.",
      };
    }
    case "price_edge": {
      const { fair_prob, offered_american, min_ev } = input as { fair_prob: number; offered_american: number; min_ev?: number };
      const e = O.priceEdge(fair_prob, offered_american, { minEv: min_ev });
      return { ...e, fairAmerican: Math.round(e.fairAmerican), evPct: r2(e.evPct * 100), stake: r2(e.stake) };
    }
    case "parlay": {
      const { prices, fair_probs, round_robin_size } = input as { prices: number[]; fair_probs?: number[]; round_robin_size?: number };
      const a = O.parlayAnalysis(prices, fair_probs ? { fairProbs: fair_probs } : {});
      const out: Record<string, unknown> = {
        legs: a.legs.map((l) => ({ american: l.american, raw_implied: r2(l.rawProb), fair_prob: r2(l.fairProb) })),
        combined_american: Math.round(a.combinedAmerican),
        true_probability: r2(a.trueProbability),
        implied_probability: r2(a.impliedProbability),
        ev_pct: r2(a.evPct * 100),
        parlay_hold_pct: r2(a.holdPct * 100),
        single_leg_hold_pct: a.singleLegHoldPct === null ? null : r2(a.singleLegHoldPct * 100),
        note: "Compare parlay_hold_pct to single_leg_hold_pct. That difference is what stacking independent legs costs.",
      };
      if (round_robin_size) {
        const rr = O.roundRobin(prices, round_robin_size, fair_probs);
        out.round_robin = { size: round_robin_size, tickets: rr.ticketCount, mean_ev_pct: r2(rr.meanEvPct * 100) };
      }
      return out;
    }
    case "simulate_game": {
      const i = input as Record<string, number | string | number[]>;
      const drives = (i.drives_per_team as number) ?? 11;
      const cfg: S.GameSimConfig = {
        home: { name: i.home_name as string, pointsPerDrive: (i.home_points as number) / drives, tdShare: (i.home_td_share as number) ?? 0.6 },
        away: { name: i.away_name as string, pointsPerDrive: (i.away_points as number) / drives, tdShare: (i.away_td_share as number) ?? 0.6 },
        baseDrives: drives,
        iterations: (i.iterations as number) ?? 40000,
      };
      const res = S.runGame(cfg);
      const out: Record<string, unknown> = {
        iterations: res.n,
        projected: { [i.home_name as string]: r2(res.homeMean), [i.away_name as string]: r2(res.awayMean) },
        total_mean: r2(res.totalMean), total_sd: r2(res.totalSd),
        fair_spread_home: r2(res.fairSpread), margin_sd: r2(res.marginSd),
        home_win_prob: r2(res.homeWinProb), home_fair_ml: am(res.homeWinProb), away_fair_ml: am(1 - res.homeWinProb),
      };
      if (i.spreads) out.spreads = (i.spreads as number[]).map((s) => {
        const c = S.pCover(res, s);
        return { home_spread: s, home_cover_prob: r2(c.homeCover), home_fair: am(c.homeCover), away_fair: am(1 - c.homeCover), push_prob: r2(c.push) };
      });
      if (i.totals) out.totals = (i.totals as number[]).map((t) => {
        const p = S.pOver(res, t);
        return { total: t, over_prob: r2(p.over), over_fair: am(p.over), under_prob: r2(p.under), under_fair: am(p.under), push_prob: r2(p.push) };
      });
      if (i.key_numbers) out.key_number_mass = S.keyNumbers(res, i.key_numbers as number[]);
      if (i.lead_thresholds) {
        const paths = S.runPaths(cfg);
        out.lead_probabilities = (i.lead_thresholds as number[]).map((k) => ({
          threshold: k,
          home_leads_by_at_any_point: r2(paths.pLeadsBy("home", k)),
          away_leads_by_at_any_point: r2(paths.pLeadsBy("away", k)),
          either: r2(paths.pEitherLeadsBy(k)),
        }));
        out.lead_note = "Leading by k at some point is far more likely than winning, and the gap is much larger for the underdog — a favourite that goes up k was probably winning anyway.";
      }
      return out;
    }
    case "yardage_prop": {
      const { label, line, projected_mean, cv, offered_american, side } = input as
        { label: string; line: number; projected_mean: number; cv: number; offered_american?: number; side?: "over" | "under" };
      const implied = S.impliedMean(line, cv);
      const pu = S.lognormalUnder(projected_mean, cv, line);
      const gap = projected_mean - implied;
      const out: Record<string, unknown> = {
        label, line, your_mean: projected_mean,
        mean_the_line_implies: r2(implied),
        gap_yards: r2(gap),
        verdict: Math.abs(gap) >= 5 ? "real gap" : "noise — under 5 yards of gap is not an edge",
        under_prob: r2(pu), under_fair: am(pu), over_prob: r2(1 - pu), over_fair: am(1 - pu),
      };
      if (offered_american && side) {
        const p = side === "under" ? pu : 1 - pu;
        out.ev_pct = r2(O.evFromAmerican(p, offered_american) * 100);
      }
      return out;
    }
    case "reception_prop": {
      const { label, line, mean_targets, target_sd, catch_rate, offered_american, side } = input as
        { label: string; line: number; mean_targets: number; target_sd?: number; catch_rate: number; offered_american?: number; side?: "over" | "under" };
      const need = Math.ceil(line);
      const po = S.receptionProb(mean_targets, target_sd ?? 2.4, catch_rate, need);
      const out: Record<string, unknown> = {
        label, line, need_at_least: need,
        mean_receptions: r2(mean_targets * catch_rate),
        over_prob: r2(po), over_fair: am(po), under_prob: r2(1 - po), under_fair: am(1 - po),
        dispersion: (() => {
          const d = S.receptionDispersion(mean_targets, target_sd ?? 2.4, catch_rate);
          return {
            regime: d.regime,
            variance_to_mean_ratio: r2(d.ratio),
            break_even_target_sd: r2(d.breakEvenTargetSd),
            note: d.ratio < 1
              ? "Under-dispersed: a Poisson on receptions would UNDERSTATE this probability."
              : "Over-dispersed: a Poisson on receptions would OVERSTATE this probability.",
          };
        })(),
        note: "Modelled as gamma targets then binomial catches, not Poisson. The target SD drives the tails — say what you used.",
      };
      if (offered_american && side) {
        const p = side === "over" ? po : 1 - po;
        out.ev_pct = r2(O.evFromAmerican(p, offered_american) * 100);
      }
      return out;
    }
    case "sharp_anchor":
      return O.sharpAnchor((input as { book_prices: Record<string, number> }).book_prices);
    case "touchdown_board": {
      const { players, projected_game_tds, reserve_for_unlisted } = input as
        { players: Array<{ name: string; american: number }>; projected_game_tds: number; reserve_for_unlisted?: number };
      const reserve = reserve_for_unlisted ?? 0.15;
      const rows = players.map((p) => {
        const raw = O.impliedProb(p.american);
        return { ...p, raw, lambda: -Math.log(1 - raw) };
      });
      const boardTds = rows.reduce((a, r) => a + r.lambda, 0);
      const target = projected_game_tds * (1 - reserve);
      const scale = target / boardTds;
      const priced = rows.map((r) => {
        const fair = 1 - Math.exp(-r.lambda * scale);
        return {
          name: r.name, offered: r.american, raw_implied: r2(r.raw),
          fair_prob: r2(fair), fair_american: am(fair),
          ev_pct: r2(O.evFromAmerican(fair, r.american) * 100),
        };
      });
      const evs = priced.map((p) => p.ev_pct as number);
      const evRange = Math.max(...evs) - Math.min(...evs);
      const warnings: string[] = [];
      if (scale > 1.05) warnings.push(
        `INCOMPLETE BOARD: your ${players.length} listed players imply only ${r2(boardTds)} touchdowns against a projected ${projected_game_tds}. ` +
        `Scaling up by ${r2(scale)}x assigns the missing scores to whoever you happen to have prices for. DO NOT report these EVs as edges — ` +
        `either retrieve the full board or report that the board cannot be devigged.`);
      if (evRange < 3) warnings.push(
        "NO DIFFERENTIATION: every outcome came back within 3 points of the same EV. The scaling is doing all the work and you have found nothing. " +
        "Report 'no edge found', not a board of bets.");
      const sorted = [...rows].sort((a, b) => b.raw - a.raw);
      if (sorted.length > 2 && sorted[0].raw > 0.5 && sorted[sorted.length - 1].raw < 0.12) warnings.push(
        "POSSIBLE MIXED MARKET: this board spans a very wide price range. Check that no first-touchdown prices were scraped in with the anytime prices — " +
        "a mixed board cannot be devigged.");
      return {
        projected_game_tds, board_implied_tds: r2(boardTds), scale_factor: r2(scale),
        reserved_for_unlisted: reserve, players: priced,
        ev_range_pts: r2(evRange),
        warnings: warnings.length ? warnings : ["Board looks internally consistent and reasonably complete."],
      };
    }
    case "ratings_spread": {
      const i = input as Record<string, any>;
      return R.ratingsSpread({
        homeTeam: i.home_team, awayTeam: i.away_team,
        homeRating: i.home_rating ?? null, awayRating: i.away_rating ?? null,
        ratingName: i.rating_name ?? "rating",
        hfa: i.hfa, neutralSite: i.neutral_site ?? false,
        marketSpread: i.market_spread ?? null, sport: i.sport ?? "cfb",
      });
    }
    case "project_both": {
      const i = input as Record<string, any>;
      return R.projectBoth({
        homeTeam: i.home_team, awayTeam: i.away_team,
        homeOff: i.home_off, homeDefAllowed: i.home_def_allowed,
        awayOff: i.away_off, awayDefAllowed: i.away_def_allowed,
        leagueMean: i.league_mean, sport: i.sport ?? "nfl",
        marketTotal: i.market_total ?? null, gate: i.gate ?? 10,
        unavailableInputs: i.unavailable_inputs ?? [],
      });
    }
    case "venue_edge": {
      const i = input as { home_team: string; away_team?: string; fcs?: boolean };
      return V.homeEdge(i.home_team, i.away_team, i.fcs ?? false);
    }
    case "reality_check": {
      const i = input as Record<string, any>;
      const out: Record<string, unknown> = {};
      const american = i.american ?? -110;
      if (i.wins != null && i.losses != null) {
        out.record = B.realityCheck(i.wins, i.losses, american);
        out.how_to_read =
          "'proves_an_edge' means the record clears a one-sided binomial test at alpha=0.05. It does " +
          "NOT mean an edge is established: the interval is usually tens of points wide, and the " +
          "p-value assumes this was the only record you were ever going to test, which is never true " +
          "of a streak someone chose to show you.";
      }
      const p = i.true_prob ?? 0.55;
      out.sample_size_needed = B.requiredSampleSize(p, american);
      out.drawdown = B.drawdownSimulation(p, i.n_bets ?? 500, american);
      out.seven_bet_losing_streak_prob = r2(B.losingStreakProbability(p, 7, i.n_bets ?? 500));
      return out;
    }
    case "clv": {
      const i = input as { taken_american: number; closing_american: number };
      const c = O.clv(i.taken_american, i.closing_american);
      return {
        ...c,
        clv_pts: r2(c.clvPts), ev_vs_close_pct: r2(c.evVsClose * 100),
        note: c.beatClose
          ? "Beat the close. This is the signal that matters; results are noise by comparison."
          : "Did not beat the close. Consistently closing worse than you bet means no edge, whatever the record says.",
      };
    }
    default:
      throw new Error(`Unknown tool: ${name}`);
  }
}
