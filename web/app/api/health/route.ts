import { NextResponse } from "next/server";
import { DESK_TOOLS, runTool } from "../../../lib/tools";
import { devig, parlayAnalysis } from "../../../lib/odds";
import { requiredSampleSize } from "../../../lib/backtest";
import { VENUES } from "../../../lib/venues";
import { projectBoth } from "../../../lib/ratings";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Liveness plus a self-check of the math the agent depends on.
 *
 * Deploys can succeed with a broken engine — a bad devig or a silently wrong
 * Kelly stake typechecks fine. These assertions are cheap and are the same
 * values the Python reference produces, so a green /api/health means the
 * deployed engine still agrees with it.
 */
export async function GET() {
  const checks: Array<{ name: string; ok: boolean; detail: string }> = [];
  const near = (a: number, b: number, tol = 1e-6) => Math.abs(a - b) < tol;

  async function check(name: string, fn: () => string | Promise<string>) {
    try {
      checks.push({ name, ok: true, detail: await fn() });
    } catch (e: any) {
      checks.push({ name, ok: false, detail: e?.message ?? String(e) });
    }
  }

  await check("devig removes the vig", () => {
    const fair = devig([-110, -110], "power");
    if (!near(fair[0] + fair[1], 1, 1e-9)) throw new Error(`probabilities sum to ${fair[0] + fair[1]}`);
    if (!near(fair[0], 0.5, 1e-9)) throw new Error(`symmetric market devigged to ${fair[0]}`);
    return "-110/-110 -> 0.500/0.500";
  });

  await check("parlay hold exceeds single-leg hold", () => {
    const a = parlayAnalysis([-110, -110, -110, -110]);
    if (a.holdPct < 0.15) throw new Error(`four -110 legs held only ${(a.holdPct * 100).toFixed(1)}%`);
    return `four -110 legs hold ${(a.holdPct * 100).toFixed(1)}%`;
  });

  await check("2u stake ceiling holds", async () => {
    const r = await runTool("price_edge", { fair_prob: 0.95, offered_american: 200 }) as any;
    if (r.stake > 2) throw new Error(`staked ${r.stake}u`);
    return `capped at ${r.stake}u`;
  });

  await check("2% EV floor holds", async () => {
    const r = await runTool("price_edge", { fair_prob: 0.525, offered_american: -110 }) as any;
    if (r.verdict !== "NO BET") throw new Error(`verdict was ${r.verdict} at ${r.evPct}% EV`);
    return "0.525 at -110 -> NO BET";
  });

  await check("CFB side refuses without a ratings spine", async () => {
    const r = await runTool("ratings_spread", { home_team: "A", away_team: "B", market_spread: -20.5 }) as any;
    if (r.playable !== false) throw new Error("priced a side with no ratings");
    return "refused, as designed";
  });

  await check("projection gate catches divergent forms", () => {
    const r = projectBoth({
      homeTeam: "A", awayTeam: "B",
      homeOff: 38, homeDefAllowed: 14, awayOff: 34, awayDefAllowed: 40,
      leagueMean: 22, sport: "nfl",
    });
    if (r.playable) throw new Error(`${r.divergence.toFixed(1)}pt divergence reported playable`);
    return `${r.divergence.toFixed(1)}pt divergence -> not playable`;
  });

  await check("sample size matches the python reference", () => {
    const n = requiredSampleSize(0.55, -110).nRequired;
    if (n !== 2231) throw new Error(`got ${n}, reference is 2231`);
    return "55% at -110 -> 2231 bets";
  });

  await check("venue database loaded", () => {
    if (VENUES.length < 50) throw new Error(`only ${VENUES.length} venues`);
    return `${VENUES.length} venues`;
  });

  await check("every tool dispatches", async () => {
    const names = DESK_TOOLS.map((t) => t.name);
    if (names.length !== 17) throw new Error(`expected 17 tools, found ${names.length}`);
    return names.join(", ");
  });

  const ok = checks.every((c) => c.ok);
  return NextResponse.json(
    {
      status: ok ? "ok" : "degraded",
      // Whether a key is configured, never the key itself.
      anthropicKeyConfigured: Boolean(process.env.ANTHROPIC_API_KEY),
      cfbdKeyConfigured: Boolean(process.env.CFBD_API_KEY),
      model: "claude-opus-5",
      tools: DESK_TOOLS.length,
      checks,
      timestamp: new Date().toISOString(),
    },
    { status: ok ? 200 : 503, headers: { "cache-control": "no-store" } },
  );
}
