# Pradapicks — Deploy Guide

This is the plain-English guide for getting Pradapicks running so it stays up, keeps its data, and improves itself daily without you babysitting it. If you've been seeing the system "load players every time you open it," you almost certainly skipped the **Postgres** step below.

## TL;DR — what you need

1. A **Postgres database** (otherwise data is wiped every restart).
2. A web service that doesn't sleep, OR an external uptime ping.
3. The scheduler running in-process (default).

The provided `render.yaml` blueprint provisions all of this automatically — if you used "New → Blueprint" on Render, you already have a Postgres + always-on web service.

## Step-by-step on Render

### 1. Make sure the service is using Postgres
- Render dashboard → your `pradapicks-db` (Postgres) — should exist.
- Render dashboard → `pradapicks-api` → **Environment** tab.
- `DATABASE_URL` should be set automatically (linked to the DB). If it's missing, add it: Add Environment Variable → key `DATABASE_URL` → click the little 🔗 icon → pick "From database" → `pradapicks-db` / Connection String.
- Save and redeploy.

**How to verify:** open `https://YOUR-URL/health` and look at the `database_kind` field. It must say `"postgresql"`. If it says `"sqlite"`, you're on the ephemeral filesystem and data will be wiped on every restart — that's the source of the "always re-loading players" problem.

### 2. Plan choice (whether the service sleeps)
- **Starter ($7/mo)** — always on. Recommended.
- **Free** — sleeps after 15 min idle. Workaround: free uptime ping (UptimeRobot, Better Uptime, Cron-Job.org) hitting `/health` every 5 minutes. Pradapicks also self-pings if `RENDER_EXTERNAL_URL` is set, but the very first sleep cycle has no one to wake it.

### 3. Confirm the scheduler is running
Open `/health`. If `RUN_SCHEDULER=true` (the default), you'll see picks and odds timestamps refresh every 30 min in the `last_odds_fetch` and `last_pick_generation` fields.

### 4. Daily rhythm (automatic, you don't touch anything)
- Every **30 min**: pull live odds → regenerate top-25.
- Every **1 hour**: ingest today's in-progress box scores.
- **04:00 ET**: ingest yesterday's final box scores → grade picks → retrain models.

## If Render isn't working out

Three good free / cheap alternatives:

### Option A: Fly.io
- Generous free tier with **persistent volumes** (perfect for a small SQLite that doesn't get wiped).
- `fly launch` from this repo, set `internal_port = 8000`, mount a volume for `./pradapicks.db`, deploy.
- Always-on by default on the hobby plan.

### Option B: Railway
- $5/mo, always-on.
- One-click Postgres + web service.
- Connects to GitHub like Render.

### Option C: GitHub Actions as the scheduler
If you want **zero hosting cost** and don't mind that the dashboard is offline most of the time:
- Host the API on Render Free (sleeps when idle).
- Add a GitHub Actions workflow that hits `/refresh` and `/admin/grade` on a cron schedule (free for public repos).
- The workflow wakes the service, triggers a refresh, then the service goes back to sleep until the next cron run.

I can scaffold any of these — just tell me which one.

## What runs where

| Job | When | Where |
|---|---|---|
| Top-25 picks regenerated | every 30 min | in-process scheduler |
| Today's box scores re-ingested | every hour | in-process scheduler |
| Yesterday graded + nightly retrain | 04:00 ET daily | in-process scheduler |
| Self-keepalive ping | every 10 min | background thread |
| Cold-start backfill | first deploy only | `bootstrap.py` daemon thread |

## Data persistence checklist

After deploy, verify all of these in `/health`:
- `database_kind: "postgresql"`
- `persistent: true`
- `warning: null`
- `last_box_score_date` is recent
- `last_odds_fetch` updates over time
- `picks_today > 0`

If any are wrong, the service will appear to "reset" itself — that's the symptom you've been seeing.
