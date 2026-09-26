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
];

describe("the tool surface", () => {
  it("exposes every tool the dispatcher handles, and vice versa", () => {
    const defined = DESK_TOOLS.map((t) => t.name).sort();
    const exercised = [...new Set(CALLS.map(([n]) => n))].sort();
    expect(defined).toEqual(exercised);
  });
  it("gives every tool a description and a closed schema", () => {
    for (const t of DESK_TOOLS) {
      expect(t.description!.length).toBeGreaterThan(80);
      const s = t.input_schema as any;
      expect(s.type).toBe("object");
      expect(s.additionalProperties).toBe(false);
      expect(Object.keys(s.properties).length).toBeGreaterThan(0);
      for (const req of s.required ?? []) expect(s.properties).toHaveProperty(req);
    }
  });
  it("dispatches every tool without throwing", () => {
    for (const [name, input] of CALLS) {
      expect(() => runTool(name, input), name).not.toThrow();
      expect(runTool(name, input), name).toBeTypeOf("object");
    }
  });
  it("throws on an unknown tool", () => {
    expect(() => runTool("bogus", {})).toThrow(/Unknown tool/);
  });
});

describe("input validation", () => {
  it("refuses a call missing a required field instead of returning garbage", () => {
    // simulate_game without home_name previously returned {projected: {undefined: 23.9}},
    // silently losing one team's projection.
    expect(() => runTool("simulate_game", { away_name: "DET", home_points: 27, away_points: 24 }))
      .toThrow(/missing required field\(s\): home_name/);
  });
  it("names the accepted fields so the caller can retry correctly", () => {
    expect(() => runTool("yardage_prop", { line: 87 })).toThrow(/Accepted fields:.*projected_mean/);
  });
  it("treats null the same as absent", () => {
    expect(() => runTool("clv", { taken_american: -105, closing_american: null }))
      .toThrow(/missing required field/);
  });
  it("accepts home_team/away_team as aliases for home_name/away_name", () => {
    const viaAlias = runTool("simulate_game", { home_team: "BUF", away_team: "DET", home_points: 27, away_points: 24, iterations: 2000 }) as any;
    expect(Object.keys(viaAlias.projected)).toEqual(["BUF", "DET"]);
    expect(Object.keys(viaAlias.projected)).not.toContain("undefined");
  });
  it("accepts legs as an alias for parlay prices", () => {
    const a = runTool("parlay", { legs: [-110, -110] }) as any;
    expect(a.legs).toHaveLength(2);
  });
});

describe("tools enforce the discipline rules, not just the math", () => {
  it("ratings_spread refuses a CFB side with no ratings spine", () => {
    const r = runTool("ratings_spread", { home_team: "Miami", away_team: "Wake Forest", market_spread: -20.5 }) as any;
    expect(r.playable).toBe(false);
    expect(r.reason).toMatch(/ratings spine/);
  });
  it("project_both finds no directional read when the total sits inside the range", () => {
    const r = runTool("project_both", {
      home_team: "BUF", away_team: "DET", home_off: 28.9, home_def_allowed: 22.9,
      away_off: 28.6, away_def_allowed: 24.3, market_total: 54.5,
    }) as any;
    expect(r.leanVsMarket).toMatch(/none/);
  });
  it("project_both caps the stake at 1u on an unavailable input", () => {
    const r = runTool("project_both", {
      home_team: "BUF", away_team: "DET", home_off: 28.9, home_def_allowed: 22.9,
      away_off: 28.6, away_def_allowed: 24.3, unavailable_inputs: ["pace"],
    }) as any;
    expect(r.maxStakeUnits).toBe(1);
  });
  it("price_edge returns NO BET below the 2% floor", () => {
    const r = runTool("price_edge", { fair_prob: 0.525, offered_american: -110 }) as any;
    expect(r.verdict).toBe("NO BET");
  });
  it("price_edge never stakes more than 2u", () => {
    const r = runTool("price_edge", { fair_prob: 0.95, offered_american: 200 }) as any;
    expect(r.stake).toBeLessThanOrEqual(2);
    expect(r.capped).toBe(true);
  });
  it("parlay shows independent legs multiplying the hold", () => {
    const r = runTool("parlay", { prices: [-110, -110, -110, -110] }) as any;
    expect(r.parlay_hold_pct).toBeGreaterThan(r.single_leg_hold_pct * 2);
    expect(r.parlay_hold_pct).toBeGreaterThan(15);
  });
  it("touchdown_board warns on an incomplete board rather than reporting edges", () => {
    const r = runTool("touchdown_board", {
      players: [{ name: "A", american: 120 }, { name: "B", american: 180 }],
      projected_game_tds: 5.2,
    }) as any;
    expect(r.warnings.join(" ")).toMatch(/INCOMPLETE BOARD/);
  });
  it("venue_edge warns instead of inventing an unknown venue's HFA", () => {
    const r = runTool("venue_edge", { home_team: "Nowhere State" }) as any;
    expect(r.venue).toBeNull();
    expect(r.warnings.join(" ")).toMatch(/not treat this as a researched number/i);
  });
  it("reality_check explains that proves_an_edge is not proof of an edge", () => {
    const r = runTool("reality_check", { wins: 12, losses: 3 }) as any;
    expect(r.record.provesAnEdge).toBe(true);
    expect(r.how_to_read).toMatch(/does\s+NOT mean an edge is established/);
    expect(r.sample_size_needed.nRequired).toBe(2231);
  });
  it("clv reports beating the close as the signal that matters", () => {
    const beat = runTool("clv", { taken_american: -105, closing_american: -120 }) as any;
    expect(beat.beatClose).toBe(true);
    expect(beat.clv_pts).toBeGreaterThan(0);
    const missed = runTool("clv", { taken_american: -120, closing_american: -105 }) as any;
    expect(missed.beatClose).toBe(false);
    expect(missed.note).toMatch(/no edge/);
  });
});
