import { describe, it, expect } from "vitest";
import { DESK_TOOLS, runTool } from "../lib/tools";

const CALLS: Array<[string, Record<string, unknown>]> = [
  ["devig", { labels: ["Chiefs", "Bills"], prices: [118, -128] }],
  ["price_edge", { fair_prob: 0.55, offered_american: -110 }],
  ["parlay", { prices: [-110, -110, -110, -110] }],
  ["simulate_game", { home_name: "BUF", away_name: "DET", home_points: 27, away_points: 24 }],
  ["yardage_prop", { label: "Gibbs rush yds", line: 87, projected_mean: 78, cv: 0.45 }],
  ["reception_prop", { label: "Shakir rec", line: 3, mean_targets: 6.5, target_sd: 2.4, catch_rate: 0.72 }],
  ["sharp_anchor", { book_prices: { pinnacle: 118, draftkings: 132 } }],
  ["touchdown_board", { players: [{ name: "A", american: 120 }, { name: "B", american: 180 }], projected_game_tds: 5.2 }],
  ["ratings_spread", { home_team: "Miami", away_team: "Wake Forest", home_rating: 21.4, away_rating: -1.9, market_spread: -20.5 }],
  ["project_both", { home_team: "BUF", away_team: "DET", home_off: 28.9, home_def_allowed: 22.9, away_off: 28.6, away_def_allowed: 24.3 }],
  ["venue_edge", { home_team: "Wyoming", away_team: "Hawaii" }],
  ["reality_check", { wins: 12, losses: 3 }],
  ["clv", { taken_american: -105, closing_american: -120 }],
  ["cfb_ratings", { home_team: "Miami", away_team: "Wake Forest" }],
  ["cfb_slate", { week: 4 }],
  ["cfb_lines", { week: 4 }],
  ["cfb_talent", {}],
];

// The CFBD tools do network I/O and need a key, so they cannot be dispatch-tested
// here. They are covered separately below by asserting they fail loudly.
const NETWORK_TOOLS = new Set(["cfb_ratings", "cfb_slate", "cfb_lines", "cfb_talent"]);

describe("the tool surface", () => {
  it("exposes every tool the dispatcher handles, and vice versa", async () => {
    const defined = DESK_TOOLS.map((t) => t.name).sort();
    const exercised = [...new Set(CALLS.map(([n]) => n))].sort();
    expect(defined).toEqual(exercised);
  });
  it("gives every tool a description and a closed schema", async () => {
    for (const t of DESK_TOOLS) {
      expect(t.description!.length).toBeGreaterThan(80);
      const s = t.input_schema as any;
      expect(s.type).toBe("object");
      expect(s.additionalProperties).toBe(false);
      expect(Object.keys(s.properties).length).toBeGreaterThan(0);
      for (const req of s.required ?? []) expect(s.properties).toHaveProperty(req);
    }
  });
  it("dispatches every pure-math tool without throwing", async () => {
    for (const [name, input] of CALLS) {
      if (NETWORK_TOOLS.has(name)) continue;
      await expect(runTool(name, input), name).resolves.toBeTypeOf("object");
    }
  });
  it("rejects an unknown tool", async () => {
    await expect(runTool("bogus", {})).rejects.toThrow(/Unknown tool/);
  });
});

describe("input validation", () => {
  it("refuses a call missing a required field instead of returning garbage", async () => {
    // simulate_game without home_name previously returned {projected: {undefined: 23.9}},
    // silently losing one team's projection.
    await expect(runTool("simulate_game", { away_name: "DET", home_points: 27, away_points: 24 })).rejects.toThrow(/missing required field\(s\): home_name/);
  });
  it("names the accepted fields so the caller can retry correctly", async () => {
    await expect(runTool("yardage_prop", { line: 87 })).rejects.toThrow(/Accepted fields:.*projected_mean/);
  });
  it("treats null the same as absent", async () => {
    await expect(runTool("clv", { taken_american: -105, closing_american: null })).rejects.toThrow(/missing required field/);
  });
  it("accepts home_team/away_team as aliases for home_name/away_name", async () => {
    const viaAlias = await runTool("simulate_game", { home_team: "BUF", away_team: "DET", home_points: 27, away_points: 24, iterations: 2000 }) as any;
    expect(Object.keys(viaAlias.projected)).toEqual(["BUF", "DET"]);
    expect(Object.keys(viaAlias.projected)).not.toContain("undefined");
  });
  it("accepts legs as an alias for parlay prices", async () => {
    const a = await runTool("parlay", { legs: [-110, -110] }) as any;
    expect(a.legs).toHaveLength(2);
  });
});

describe("tools enforce the discipline rules, not just the math", () => {
  it("ratings_spread refuses a CFB side with no ratings spine", async () => {
    const r = await runTool("ratings_spread", { home_team: "Miami", away_team: "Wake Forest", market_spread: -20.5 }) as any;
    expect(r.playable).toBe(false);
    expect(r.reason).toMatch(/ratings spine/);
  });
  it("project_both finds no directional read when the total sits inside the range", async () => {
    const r = await runTool("project_both", {
      home_team: "BUF", away_team: "DET", home_off: 28.9, home_def_allowed: 22.9,
      away_off: 28.6, away_def_allowed: 24.3, market_total: 54.5,
    }) as any;
    expect(r.leanVsMarket).toMatch(/none/);
  });
  it("project_both caps the stake at 1u on an unavailable input", async () => {
    const r = await runTool("project_both", {
      home_team: "BUF", away_team: "DET", home_off: 28.9, home_def_allowed: 22.9,
      away_off: 28.6, away_def_allowed: 24.3, unavailable_inputs: ["pace"],
    }) as any;
    expect(r.maxStakeUnits).toBe(1);
  });
  it("price_edge returns NO BET below the 2% floor", async () => {
    const r = await runTool("price_edge", { fair_prob: 0.525, offered_american: -110 }) as any;
    expect(r.verdict).toBe("NO BET");
  });
  it("price_edge never stakes more than 2u", async () => {
    const r = await runTool("price_edge", { fair_prob: 0.95, offered_american: 200 }) as any;
    expect(r.stake).toBeLessThanOrEqual(2);
    expect(r.capped).toBe(true);
  });
  it("parlay shows independent legs multiplying the hold", async () => {
    const r = await runTool("parlay", { prices: [-110, -110, -110, -110] }) as any;
    expect(r.parlay_hold_pct).toBeGreaterThan(r.single_leg_hold_pct * 2);
    expect(r.parlay_hold_pct).toBeGreaterThan(15);
  });
  it("touchdown_board warns on an incomplete board rather than reporting edges", async () => {
    const r = await runTool("touchdown_board", {
      players: [{ name: "A", american: 120 }, { name: "B", american: 180 }],
      projected_game_tds: 5.2,
    }) as any;
    expect(r.warnings.join(" ")).toMatch(/INCOMPLETE BOARD/);
  });
  it("venue_edge warns instead of inventing an unknown venue's HFA", async () => {
    const r = await runTool("venue_edge", { home_team: "Nowhere State" }) as any;
    expect(r.venue).toBeNull();
    expect(r.warnings.join(" ")).toMatch(/not treat this as a researched number/i);
  });
  it("reality_check explains that proves_an_edge is not proof of an edge", async () => {
    const r = await runTool("reality_check", { wins: 12, losses: 3 }) as any;
    expect(r.record.provesAnEdge).toBe(true);
    expect(r.how_to_read).toMatch(/does\s+NOT mean an edge is established/);
    expect(r.sample_size_needed.nRequired).toBe(2231);
  });
  it("clv reports beating the close as the signal that matters", async () => {
    const beat = await runTool("clv", { taken_american: -105, closing_american: -120 }) as any;
    expect(beat.beatClose).toBe(true);
    expect(beat.clv_pts).toBeGreaterThan(0);
    const missed = await runTool("clv", { taken_american: -120, closing_american: -105 }) as any;
    expect(missed.beatClose).toBe(false);
    expect(missed.note).toMatch(/no edge/);
  });
});

describe("the CFBD tools fail loudly rather than inventing data", () => {
  // No CFBD_API_KEY in the test environment, which is the common case.
  it.each(["cfb_ratings", "cfb_slate", "cfb_lines", "cfb_talent"])(
    "%s says the key is missing and what to do instead",
    async (name) => {
      const input = name === "cfb_ratings" ? { home_team: "Miami", away_team: "Wake Forest" } : {};
      await expect(runTool(name, input)).rejects.toThrow(/CFBD_API_KEY is not set/);
    },
  );
  it("tells the caller to say the spine is missing rather than guess", async () => {
    await expect(runTool("cfb_ratings", { home_team: "A", away_team: "B" }))
      .rejects.toThrow(/ratings spine is missing|label it with its source/);
  });
  it("still requires both teams before attempting a fetch", async () => {
    await expect(runTool("cfb_ratings", { home_team: "A" }))
      .rejects.toThrow(/missing required field\(s\): away_team/);
  });
});
