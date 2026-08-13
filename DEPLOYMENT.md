# Deploying to Render

This guide assumes no prior experience. Every term is explained the first time
it appears. Budget about 30 minutes.

---

## What you are building

Right now the dashboard is four separate jobs that happen to live in one folder.
On Render each becomes its own running piece:

| Piece | Plain English | Render calls it |
|---|---|---|
| **Database** | A filing cabinet that holds every month of inflation data | PostgreSQL |
| **API** | A small program that reads the filing cabinet and hands the numbers out | Web Service |
| **Fetcher** | A robot that wakes up on a timetable, checks the ONS and Bank of England websites, and files anything new | Cron Job |
| **Dashboard** | The charts you actually look at | Static Site |

The flow is: *robot scrapes → files into database → API hands out → dashboard draws.*

You do not need to understand the code to follow this. You do need two free
accounts: **GitHub** (stores the code) and **Render** (runs it).

---

## Step 1 — Put the code on GitHub

Render can only deploy code it can see, so the project needs to live on GitHub
rather than only on your laptop.

1. Make a free account at **github.com** if you don't have one.
2. Download **GitHub Desktop** from `desktop.github.com` and sign in. This is a
   normal app with buttons — you won't need to type commands.
3. In GitHub Desktop: **File → Add Local Repository**, choose this project's
   folder, and click **Add**.
4. Click **Publish repository** (top of the window).
   - Untick **"Keep this code private"** only if you're happy for it to be
     public. Private is fine and works the same.
   - Click **Publish repository**.

The code is now on GitHub. Any time you change something, GitHub Desktop will
show it; click **Commit** then **Push** to send it up.

---

## Step 2 — Create everything on Render

1. Make a free account at **render.com** and connect it to GitHub when asked.
2. Click **New → Blueprint**.
3. Pick this repository from the list.

Render reads the `render.yaml` file in the project and offers to create all four
pieces at once. It will ask you to fill in a few blanks — that's Step 3.

> **A note on cost.** The database, API and dashboard all have free options.
> Scheduled jobs (the robot) are a paid feature on Render. If you'd rather not
> pay, skip to *"Free alternative to the paid robot"* near the bottom — the
> dashboard works identically either way.
>
> Free databases on Render also expire after a set period. Check the current
> terms on the database's page before relying on it long-term.

---

## Step 3 — Fill in the three settings

Render will ask for these because they're deliberately not written into the
code (two are secret, one isn't known until Render creates the services).

**a. `ANTHROPIC_API_KEY`** — on the *fetcher*.
This is what lets Claude write the short commentary note. Get one from
`console.anthropic.com`. If you leave it blank everything still works; you just
get no written note.

**b. `VITE_API_BASE_URL`** — on the *dashboard*.
This tells the charts where to fetch numbers from. You won't know it until
Render has created the API, so:
- Let the blueprint finish.
- Open the **uk-inflation-api** service and copy its address from the top of the
  page — something like `https://uk-inflation-api.onrender.com`.
- Open **uk-inflation-web → Environment**, paste it as the value, and save.
- Click **Manual Deploy → Deploy latest commit** so the dashboard rebuilds with
  the address baked in.

**c. `ALLOWED_ORIGINS`** — on the *API*. Optional.
Leave it as `*` and any website may read your data — harmless for public
statistics. To be tidy, set it to your dashboard's address once you know it.

---

## Step 4 — Get the first data in

The database starts empty. There are two ways to fill it, and the first happens
by itself:

**Automatically.** When the API starts for the first time and finds an empty
database, it loads the data already committed in this project's `data` folder
(currently through June 2026). So the dashboard should have real numbers the
moment it comes up.

**Manually, to pull the very latest.** Open the **uk-inflation-fetcher** job and
click **Trigger Run**. It scrapes the ONS and Bank of England, files anything
new, and finishes in a minute or two. Do this once after setup so you're
current.

---

## Step 5 — Check it worked

Three quick checks, in order:

1. Visit `https://<your-api-address>/health` — you should see
   `{"status":"ok","database":"up","observations":138}` or similar. If
   `observations` is `0`, run the fetcher (Step 4).
2. Visit `https://<your-api-address>/data/meta.json` — a wall of numbers means
   the API and database are talking.
3. Visit your dashboard address. Charts should draw.

If the dashboard is blank but the API works, `VITE_API_BASE_URL` is wrong or the
dashboard hasn't been rebuilt since you set it — redo Step 3b.

---

## How updates happen from here

Once running, you don't touch it:

| When | What happens |
|---|---|
| 07:30, 12:30, 15:30 UTC, weekdays | The robot checks both sources |
| Nothing changed | It stops. No database write, no noise |
| New CPI figures or a rate decision | It files them, writes a Claude note, and the dashboard shows them within a few minutes |

**To force a refresh right now:** open the fetcher job → **Trigger Run**.

**Why three times a day:** the ONS publishes CPI at 07:00 UK and the Bank of
England announces rate decisions at noon UK. Because the UK changes clocks twice
a year but the server's schedule doesn't, each slot is set to land after the
publication in both winter and summer. The third run is a safety net in case the
Bank's database updates late.

---

## Free alternative to the paid robot

If you don't want to pay for a scheduled job, GitHub can run it for free — the
schedule already exists in `.github/workflows/update-data.yml`.

1. On Render, open the database and copy the **External Database URL**.
2. On GitHub: your repository → **Settings → Secrets and variables → Actions →
   New repository secret**.
3. Add one called `DATABASE_URL`, paste the address, save.
4. Add a second called `ANTHROPIC_API_KEY` if you want the commentary.
5. In `.github/workflows/update-data.yml`, add `DATABASE_URL: ${{ secrets.DATABASE_URL }}`
   to the `env:` block of the fetch step.

The fetcher notices `DATABASE_URL` and writes to Postgres instead of files, with
no other change. Delete the `uk-inflation-fetcher` service on Render if you go
this route, so the job doesn't run twice.

---

## Running it locally

Nothing here breaks local development. With no `DATABASE_URL` set, the fetcher
writes flat JSON files exactly as before and the dashboard reads them:

```bash
python fetcher/fetch.py --no-llm
```

```bash
cd web && npm install && npm run dev
```

To point a local dashboard at the deployed API instead, create `web/.env.local`
containing `VITE_API_BASE_URL=https://your-api-address` and restart.

To run the API locally you need a Postgres database on your machine; set
`DATABASE_URL` in a `.env` file (copy `.env.example`) and run:

```bash
pip install -r backend/requirements.txt && uvicorn backend.app:app --reload
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Dashboard is blank, API health is `ok` | Dashboard doesn't know the API address | Set `VITE_API_BASE_URL` and redeploy the dashboard (Step 3b) |
| `{"status":"degraded","database":"unconfigured"}` | API can't see the database | Check `DATABASE_URL` on the API service |
| `observations: 0` | Database is empty | Trigger the fetcher once (Step 4) |
| Charts draw but no written note | No Claude key, or none generated yet | Add `ANTHROPIC_API_KEY` to the fetcher and trigger a run |
| First page load takes ~30 seconds | Free services sleep when idle and take a moment to wake | Expected on the free plan; a paid plan removes it |
| Browser console mentions CORS | `ALLOWED_ORIGINS` excludes your dashboard | Set it to your dashboard address, or `*` |

---

## What is stored where

| Data | Where |
|---|---|
| Every month of CPI and Bank Rate figures | `observations` table |
| Every rate decision with its exact date | `rate_changes` table |
| Macro event markers | `events` table |
| Claude's written notes | `commentary` table |
| Latest values, methodology, source citations | `meta` table |
| A log of every scrape and what changed | `fetch_runs` table |

The `fetch_runs` table is the one to look at if you ever wonder whether the
robot has been doing its job.
