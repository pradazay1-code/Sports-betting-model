/**
 * CollegeFootballData client — the ratings spine's data source.
 *
 * `ratingsSpread` refuses to price a college side without SP+ or an equivalent.
 * Without this module the only way to get SP+ is web search, which is exactly
 * where a precise-looking fabricated number comes from. A retrieved rating is a
 * [FACT]; a remembered one is not.
 *
 * Covers FBS *and* FCS (`division=fcs`), which mainstream feeds do not.
 *
 * Every failure throws with a message the agent can repeat verbatim. It never
 * returns a plausible-looking empty slate — "I could not pull the board" is the
 * correct output when the fetch fails.
 */

const BASE = "https://api.collegefootballdata.com";

export class CfbdError extends Error {}

function apiKey(): string {
  const key = (process.env.CFBD_API_KEY ?? "").trim();
  if (!key) {
    throw new CfbdError(
      "CFBD_API_KEY is not set, so SP+ and college ratings cannot be retrieved. " +
        "Get a free key at https://collegefootballdata.com/key and add it to the environment. " +
        "Until then, research the rating by web search and label it with its source — or say the " +
        "ratings spine is missing and do not publish a college side.",
    );
  }
  return key;
}

/** CFB seasons are labelled by the year they start; the label flips in spring. */
export function currentSeason(now = new Date()): number {
  return now.getUTCMonth() + 1 >= 3 ? now.getUTCFullYear() : now.getUTCFullYear() - 1;
}

async function get<T>(path: string, params: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(BASE + path);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  }
  let res: Response;
  try {
    res = await fetch(url, {
      headers: { Authorization: `Bearer ${apiKey()}`, Accept: "application/json" },
      signal: AbortSignal.timeout(25_000),
      // Ratings move slowly; lines do not. Callers pass their own revalidate below.
      cache: "no-store",
    });
  } catch (e: any) {
    if (e?.name === "TimeoutError") throw new CfbdError(`CFBD ${path} timed out after 25s. Say the fetch failed; do not fill the hole.`);
    throw new CfbdError(`Could not reach CFBD ${path}: ${e?.message ?? e}`);
  }
  if (res.status === 401) throw new CfbdError("401 from CFBD — the configured key is wrong or expired.");
  if (res.status === 429) throw new CfbdError("429 from CFBD — rate limited. Back off before retrying.");
  if (!res.ok) throw new CfbdError(`${res.status} from CFBD ${path}: ${(await res.text()).slice(0, 200)}`);
  return (await res.json()) as T;
}

// ---------------------------------------------------------------------------
// Ratings
// ---------------------------------------------------------------------------

export interface SpRating {
  team: string;
  year: number;
  /** Points per game above average against an average schedule. */
  rating: number;
  offense?: { rating?: number } | null;
  defense?: { rating?: number } | null;
}

export async function spRatings(year?: number, team?: string): Promise<SpRating[]> {
  const rows = await get<SpRating[]>("/ratings/sp", { year: year ?? currentSeason(), team });
  return (rows ?? []).filter((r) => r && typeof r.rating === "number");
}

/**
 * SP+ for exactly the two teams in a matchup, shaped for `ratingsSpread`.
 *
 * Returns nulls for a team it could not find rather than a substitute number —
 * a missing rating must propagate to a refusal, not be papered over.
 */
export async function matchupRatings(homeTeam: string, awayTeam: string, year?: number) {
  const all = await spRatings(year);
  const norm = (s: string) => s.trim().toLowerCase();
  const find = (name: string) => {
    const n = norm(name);
    return (
      all.find((r) => norm(r.team) === n) ??
      all.find((r) => norm(r.team).startsWith(n)) ??
      all.find((r) => norm(r.team).includes(n))
    );
  };
  const h = find(homeTeam);
  const a = find(awayTeam);
  const notes: string[] = [];
  if (!h) notes.push(`No SP+ row matched '${homeTeam}'. Check the spelling CFBD uses, or treat the spine as missing.`);
  if (!a) notes.push(`No SP+ row matched '${awayTeam}'. Check the spelling CFBD uses, or treat the spine as missing.`);
  if (h && norm(h.team) !== norm(homeTeam)) notes.push(`Matched '${homeTeam}' to '${h.team}' — confirm that is the right team.`);
  if (a && norm(a.team) !== norm(awayTeam)) notes.push(`Matched '${awayTeam}' to '${a.team}' — confirm that is the right team.`);
  return {
    year: year ?? currentSeason(),
    ratingName: "SP+",
    teamsRated: all.length,
    home: h ? { team: h.team, rating: h.rating, offense: h.offense?.rating ?? null, defense: h.defense?.rating ?? null } : null,
    away: a ? { team: a.team, rating: a.rating, offense: a.offense?.rating ?? null, defense: a.defense?.rating ?? null } : null,
    notes,
  };
}

export async function talent(year?: number): Promise<Array<{ team: string; talent: number }>> {
  const rows = await get<Array<{ school?: string; team?: string; talent: string | number }>>("/talent", { year: year ?? currentSeason() });
  return (rows ?? []).map((r) => ({ team: r.school ?? r.team ?? "", talent: Number(r.talent) }));
}

// ---------------------------------------------------------------------------
// Schedule — FBS and FCS
// ---------------------------------------------------------------------------

export interface CfbGame {
  id: number;
  week: number;
  season: number;
  seasonType: string;
  startDate: string;
  neutralSite: boolean;
  homeTeam: string;
  awayTeam: string;
  homePoints: number | null;
  awayPoints: number | null;
  venue?: string | null;
  homeClassification?: string | null;
  awayClassification?: string | null;
}

export async function games(opts: {
  year?: number; week?: number; division?: "fbs" | "fcs"; seasonType?: string;
} = {}): Promise<CfbGame[]> {
  const rows = await get<any[]>("/games", {
    year: opts.year ?? currentSeason(),
    week: opts.week,
    division: opts.division,
    seasonType: opts.seasonType ?? "regular",
  });
  return (rows ?? []).map((g) => ({
    id: g.id,
    week: g.week,
    season: g.season,
    seasonType: g.seasonType ?? g.season_type,
    startDate: g.startDate ?? g.start_date,
    neutralSite: Boolean(g.neutralSite ?? g.neutral_site),
    homeTeam: g.homeTeam ?? g.home_team,
    awayTeam: g.awayTeam ?? g.away_team,
    homePoints: g.homePoints ?? g.home_points ?? null,
    awayPoints: g.awayPoints ?? g.away_points ?? null,
    venue: g.venue ?? null,
    homeClassification: g.homeClassification ?? g.home_classification ?? null,
    awayClassification: g.awayClassification ?? g.away_classification ?? null,
  }));
}

/**
 * The full slate for a week across BOTH divisions, which is what a request for
 * "every game including FCS" actually needs. Reports each division's fetch
 * separately so a partial failure is visible rather than silently short.
 */
export async function fullSlate(year?: number, week?: number) {
  const out: { games: CfbGame[]; errors: string[]; byDivision: Record<string, number> } = {
    games: [], errors: [], byDivision: {},
  };
  for (const division of ["fbs", "fcs"] as const) {
    try {
      const rows = await games({ year, week, division });
      out.games.push(...rows);
      out.byDivision[division] = rows.length;
    } catch (e: any) {
      out.errors.push(`${division.toUpperCase()}: ${e?.message ?? e}`);
      out.byDivision[division] = 0;
    }
  }
  // A partial failure is reported so the caller can say the slate is incomplete.
  // A TOTAL failure must throw: returning {count: 0, games: []} invites the agent
  // to present an empty slate as though the week had no games.
  if (out.errors.length === 2) {
    throw new CfbdError(
      `Could not fetch either division. ${out.errors.join(" | ")}`,
    );
  }
  return out;
}

// ---------------------------------------------------------------------------
// Lines
// ---------------------------------------------------------------------------

export interface CfbLine {
  homeTeam: string;
  awayTeam: string;
  week: number;
  lines: Array<{ provider: string; spread: number | null; overUnder: number | null; homeMoneyline: number | null; awayMoneyline: number | null }>;
}

export async function lines(opts: { year?: number; week?: number; team?: string } = {}): Promise<CfbLine[]> {
  const rows = await get<any[]>("/lines", {
    year: opts.year ?? currentSeason(), week: opts.week, team: opts.team, seasonType: "regular",
  });
  return (rows ?? []).map((g) => ({
    homeTeam: g.homeTeam ?? g.home_team,
    awayTeam: g.awayTeam ?? g.away_team,
    week: g.week,
    lines: (g.lines ?? []).map((l: any) => ({
      provider: l.provider,
      spread: l.spread == null ? null : Number(l.spread),
      overUnder: l.overUnder == null && l.over_under == null ? null : Number(l.overUnder ?? l.over_under),
      homeMoneyline: l.homeMoneyline ?? l.home_moneyline ?? null,
      awayMoneyline: l.awayMoneyline ?? l.away_moneyline ?? null,
    })),
  }));
}

/**
 * Consensus spread and total for one game, with book disagreement.
 *
 * None of CFBD's providers are Pinnacle, so the median here is a MEDIAN ANCHOR,
 * not a sharp price. Say so when you use it.
 */
export function consensus(line: CfbLine) {
  const spreads = line.lines.map((l) => l.spread).filter((v): v is number => v != null);
  const totals = line.lines.map((l) => l.overUnder).filter((v): v is number => v != null);
  const med = (xs: number[]) => {
    if (!xs.length) return null;
    const s = [...xs].sort((a, b) => a - b);
    const m = Math.floor(s.length / 2);
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  };
  return {
    homeTeam: line.homeTeam, awayTeam: line.awayTeam,
    providers: line.lines.map((l) => l.provider),
    medianSpread: med(spreads),
    medianTotal: med(totals),
    spreadRange: spreads.length ? [Math.min(...spreads), Math.max(...spreads)] as [number, number] : null,
    totalRange: totals.length ? [Math.min(...totals), Math.max(...totals)] as [number, number] : null,
    note: "CFBD providers are soft books and a consensus. This is a median anchor, not a sharp price — no Pinnacle here.",
  };
}
