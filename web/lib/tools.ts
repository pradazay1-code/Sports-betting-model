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
];

const r2 = (x: number) => Math.round(x * 10000) / 10000;
const am = (p: number) => (p > 0 && p < 1 ? Math.round(O.probToAmerican(p)) : null);

export function runTool(name: string, input: Record<string, unknown>): unknown {
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
    default:
      throw new Error(`Unknown tool: ${name}`);
  }
}
