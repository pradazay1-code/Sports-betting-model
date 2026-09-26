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

`app/api/chat/route.ts` sets `maxDuration = 800`. **Vercel caps this by plan —
300s on Hobby, 800s on Pro.** Exceeding your plan's cap fails the deploy. On
Hobby, change it to `300` in both `route.ts` and `vercel.json`.

A full FBS+FCS slate is a genuinely long agentic run — dozens of searches and
many tool calls. On Hobby's 300s ceiling, ask for one conference or one sport at
a time.

---

## Local

```bash
npm install
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env.local
npm run dev            # http://localhost:3000
npm test               # 46 parity tests
npm run typecheck
```

---

## Architecture

```
app/
  page.tsx              chat UI — streaming, markdown tables, tool activity, reasoning panel
  api/chat/route.ts     the agent loop: SSE stream, tool dispatch, pause_turn resume
lib/
  odds.ts               devig (4 methods), EV, Kelly, parlay, round robin, sharp anchor, CLV
  simulate.ts           drive-level Monte Carlo, path sim, median correction, compound receptions
  tools.ts              8 tool definitions + dispatcher
  prompt.ts             the operating manual
__tests__/odds.test.ts  46 tests asserting parity with the Python engine
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

Plus Anthropic's server-side `web_search` for live research.

### Two implementation details that matter

**`pause_turn` is handled explicitly.** The SDK's tool runner does not auto-resume
a paused server-tool turn — it ends the loop and returns a silently truncated
answer. On a full slate that looks like the agent just stopped mid-sentence. The
loop in `route.ts` checks `stop_reason` every iteration and resumes.

**The system prompt is a frozen, cached prefix.** Nothing volatile is interpolated
into it; today's date goes in the user turn. That keeps `cache_read_input_tokens`
non-zero across turns, which is most of the cost on a long conversation.

---

## What it will not do

It refuses to fabricate. If it couldn't retrieve a line, it says so and lowers
confidence rather than filling the hole. It caps at 2 units. It says "no edge"
and "no bet" when that's the answer — which on most slates is the answer for most
games. If you want a tout that always has a pick, this is the wrong tool.
