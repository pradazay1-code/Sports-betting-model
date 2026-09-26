# The Desk — web app

The CLI agent, deployable. Same persona, same discipline rules, same math — but the
math engine is ported to TypeScript so it runs as a single Vercel deployment with
no Python cold starts, and the research happens through Anthropic's server-side
web search so the deployed agent goes and gets live lines and injury news the way
the CLI does.

Ask it anything you'd ask a trader: a full FBS+FCS college football slate, an NFL
game, an NBA card, a single prop, a parlay structure, or just "devig this."

---

## Deploy to Vercel

```bash
cd web
npx vercel            # link the project
npx vercel env add ANTHROPIC_API_KEY    # paste your key, select all environments
npx vercel --prod
```

Or from the dashboard: import the repo, set **Root Directory** to `web`, add
`ANTHROPIC_API_KEY` under Settings → Environment Variables, deploy.

Get a key at [platform.claude.com](https://platform.claude.com) → API keys.

### One thing to check before you deploy

`app/api/chat/route.ts` sets `maxDuration = 300`, which is the **Hobby-safe**
value, so it deploys as-is on any plan. **Vercel caps this by plan — 300s on
Hobby, 800s on Pro — and exceeding your plan's cap makes the deploy fail rather
than clamping.** On Pro, raise it to `800` in both `route.ts` and `vercel.json`;
a full slate will use it.

A full FBS+FCS slate is a genuinely long agentic run — dozens of searches and
many tool calls. On Hobby's 300s ceiling, ask for one conference or one sport at
a time.

---

## Local

```bash
npm install
cp .env.example .env.local     # then add ANTHROPIC_API_KEY (and CFBD_API_KEY for college)
npm run dev            # http://localhost:3000
npm test               # 172 tests, asserted against the Python engine
npm run typecheck
```

---

## Architecture

```
app/
  page.tsx              chat UI — streaming, markdown tables, tool activity, reasoning panel
  log/page.tsx          bet log — CLV tracking, reality check on the record, CSV export
  api/chat/route.ts     the agent loop: SSE stream, tool dispatch, pause_turn resume, rate limit
  api/health/route.ts   liveness + a self-check of the engine's math
lib/
  odds.ts               devig (4 methods), EV, Kelly, parlay, round robin, sharp anchor, CLV
  simulate.ts           drive-level Monte Carlo, path sim, median correction, compound receptions
  ratings.ts            SP+/FPI spread spine, both-forms projection with the divergence gate
  backtest.ts           required sample size, losing streaks, Wilson CI, drawdown MC
  venues.ts             55 CFB venues — crowd and altitude priced separately
  betlog.ts             bet log model, CLV, summary, CSV
  cfbd.ts               CollegeFootballData — SP+, FBS+FCS slate, lines, talent
  tools.ts              17 tool definitions + dispatcher with schema validation
  prompt.ts             the operating manual
__tests__/              155 tests: odds, ratings, backtest, venues, betlog, tools
```

### Why the math is ported rather than called

`lib/odds.py` and `lib/simulate.py` stay in the repo as the reference
implementation and the CLI's engine. The TypeScript port exists so the deployment
is one runtime, and **`__tests__/odds.test.ts` asserts the two agree** — the
expected values in that file were produced by the Python. If you change one
engine, change both and the test, or they silently diverge.

### The tools the agent can call

| Tool | What it's for |
|---|---|
| `devig` | Fair probabilities from a market, all four methods, with the disagreement reported |
| `price_edge` | EV%, quarter-Kelly stake, 2u cap, BET/NO BET against the EV floor |
| `parlay` | True probability, payout, hold, EV; shows what stacking independent legs costs |
| `simulate_game` | Drive-level Monte Carlo: spreads, totals, key numbers, team totals, live-lead paths |
| `yardage_prop` | **Backs the mean out of the line first** — the correction that kills most fake prop edges |
| `reception_prop` | Gamma targets → binomial catches, and reports which side of Poisson you're on |
| `sharp_anchor` | Pinnacle → Circa → BetOnline → median, and says when no sharp book was available |
| `touchdown_board` | Devigs a TD board **and audits it** for mixed markets and incompleteness |
| `project_both` | **Every total.** Both projection forms, the divergence gate, and the 1u cap |
| `ratings_spread` | **Every CFB side.** Refuses to price one without an SP+/FPI spine |
| `venue_edge` | Venue-specific CFB home field; crowd and altitude never stacked naively |
| `reality_check` | What a record proves, drawdowns, sample size. For tilt and cold streaks |
| `clv` | Closing line value — the only honest scoreboard |
| `cfb_ratings` | Retrieves SP+ so a college side rests on a [FACT], not a recollection |
| `cfb_slate` | The week's games across FBS **and** FCS |
| `cfb_lines` | Per-provider college spreads and totals, median and book disagreement |
| `cfb_talent` | Talent composite — predicts blowouts better than efficiency does |

Plus Anthropic's server-side `web_search` for live research.

Two of these exist to stop the model doing something it has already done wrong:

- **`ratings_spread` returns a refusal, not a number**, when a rating is missing.
  A PPG-based college model once produced a pick'em against a market of
  Miami -20.5; the method was broken, not the market. With 136 teams on wildly
  different schedules, two-game scoring averages carry almost no signal.
- **`project_both` will not let either projection form be discarded**, gates on
  their divergence, and reports *no directional read* when the market total falls
  between them. On DET @ BUF the forms bracketed the market at 52.4 and 57.0 with
  the line at 54.5 — there was never a side to take. 2u went on the under and the
  game went 72.

**`cfb_ratings` closes the loop on the refusal.** `ratings_spread` declining to
price without SP+ is only useful if the rating can actually be *retrieved* —
otherwise the agent web-searches for a precise number, which is where a
confident-looking fabrication comes from. With `CFBD_API_KEY` set the rating is a
retrieved `[FACT]`; without it the tool says so and names the fallback. It also
returns `null` for a team it cannot match rather than substituting a number, so a
missing rating propagates to a refusal instead of being papered over. `cfb_slate`
throws when *both* divisions fail rather than returning an empty slate that could
be read as "no games this week."

`runTool` also validates every call against the tool's own schema. It previously
did not, so `simulate_game` missing a `home_name` returned
`{projected: {undefined: 23.9}}` — silently dropping one team's projection.

### Two implementation details that matter

**`pause_turn` is handled explicitly.** The SDK's tool runner does not auto-resume
a paused server-tool turn — it ends the loop and returns a silently truncated
answer. On a full slate that looks like the agent just stopped mid-sentence. The
loop in `route.ts` checks `stop_reason` every iteration and resumes.

**The system prompt is a frozen, cached prefix.** Nothing volatile is interpolated
into it; today's date goes in the user turn. That keeps `cache_read_input_tokens`
non-zero across turns, which is most of the cost on a long conversation.

**Rate limiting is in-memory, and that is a real limitation.** `RATE_LIMIT_PER_HOUR`
(default 30, `0` disables) is enforced per serverless instance and resets on cold
start, so a caller who lands on fresh instances gets more than the stated limit. It
protects against a stuck client running up an API bill. It is **not** protection
against a motivated attacker — for that you need Vercel KV, Upstash, or a WAF rule.

**`/api/health` asserts the math, not just liveness.** A deploy can succeed with a
broken engine: a wrong devig or an uncapped Kelly stake typechecks fine. The
endpoint re-runs nine invariants (the vig comes out, the 2u ceiling holds, the 2%
floor holds, CFB refuses without a spine, the divergence gate fires, the sample
size still matches the Python's 2,231) and returns 503 if any fails. It reports
*whether* a key is configured and never the key itself.

---

## The bet log

`/log` is a client-side log — localStorage, no database, nothing leaves the browser
(which also means it does not sync across devices and is lost if you clear site
data; export to CSV to keep it).

It leads with **closing line value**, not the win/loss column, because that is the
ordering that reflects reality: a log where every bet lost but the mean CLV is
positive gets told the process is right, and a winning record with negative CLV
gets told it has no edge. The record is shown behind its Wilson interval, its
one-sided p-value, and an estimate of how many bets establishing the observed rate
would actually take.

---

## What it will not do

It refuses to fabricate. If it couldn't retrieve a line, it says so and lowers
confidence rather than filling the hole. It caps at 2 units. It says "no edge"
and "no bet" when that's the answer — which on most slates is the answer for most
games. If you want a tout that always has a pick, this is the wrong tool.
