# UK Inflation & Monetary Policy

A macro dashboard that shows how UK inflation evolved and how the Bank of England
responded — headline CPI against Bank Rate, decomposed down to the components the
MPC actually watches.

Data comes from the ONS and the Bank of England directly. Nothing is hardcoded or
hand-entered.

---

## Architecture

```
   ONS MM23 / LMS            Bank of England IADB
   (CPI, weights, AWE)       (daily official Bank Rate)
          │                            │
          └──────────┬─────────────────┘
                     ▼
           fetcher/fetch.py          ← parse, derive, diff vs. stored
                     │
                     ├─→ Claude API  ← plain-English note on what changed
                     ▼
              data/*.json            ← committed back to the repo
                     │
                     ▼
              web/ (Vite + React)    ← rebuilt & redeployed on push
```

| Piece | Where | What it does |
|---|---|---|
| **Fetcher** | `fetcher/fetch.py` | Pulls 20 ONS series + the BoE daily Bank Rate, derives the CPI decomposition, diffs against the last run, asks Claude for a note when something moved. Standard library only, apart from the Claude call. |
| **Scheduler** | `.github/workflows/update-data.yml` | Two weekday cron runs (06:30 and 12:30 UTC) covering the ONS 07:00 release slot and the noon MPC announcement, plus manual dispatch. Commits `data/` back to the repo. |
| **Storage** | `data/*.json` | Flat JSON committed to the repo. Simple, diffable, works with any static host, and every change is visible in git history. |
| **Frontend** | `web/` | Vite + React + Tailwind + Recharts. Reads the JSON at runtime; a push from the fetcher triggers a rebuild on Vercel/Netlify. |
| **AI layer** | inside the fetcher | Writes a short institutional-style note per release and flags when the policy stance looks out of step with the core trend. |

---

## Quick start

```bash
# 1. Fetch the data (no API key needed for this part)
python fetcher/fetch.py --no-llm

# 2. Run the site
npm --prefix web install
npm --prefix web run dev
```

The dev server prints a local URL. `npm run dev` copies `data/*.json` into
`web/public/data` first, so re-run it (or `npm --prefix web run sync-data`) after a
fresh fetch.

> **Windows note.** This project currently sits under a folder called `S&T`. The
> `&` breaks `npm run` on Windows — npm shells out through `cmd.exe`, which treats
> it as a command separator, so you get `Cannot find module …\Career\vite\bin\vite.js`.
> Either move the project to a path without `&`, or invoke the binaries directly:
>
> ```powershell
> cd web
> node scripts\sync-data.mjs
> node node_modules\vite\bin\vite.js          # dev server
> node node_modules\vite\bin\vite.js build    # production build
> ```
>
> CI and Vercel/Netlify are unaffected — the checkout path has no `&` in it.

To include the Claude-written release note:

```bash
export ANTHROPIC_API_KEY=sk-ant-...      # PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."
pip install -r fetcher/requirements.txt
python fetcher/fetch.py
```

---

## Deploying

Push to GitHub, then point Vercel or Netlify at the repo — `vercel.json` and
`netlify.toml` are both committed with the right build command and publish
directory. Add two repository settings so the scheduled job works:

- **Secret** `ANTHROPIC_API_KEY` — enables the commentary step (omit it and the
  fetcher still runs, just without a note).
- **Actions → General → Workflow permissions** → *Read and write*, so the job can
  commit `data/` back.

Every commit the workflow makes triggers a redeploy, so the site tracks the data
without any further intervention.

---

## What's on the dashboard

**Inflation & policy** — headline CPI and Bank Rate on one shared axis (they are
both percentages; a dual axis here would be a lie about scale). Core, services,
goods, food and energy toggle on; Bank Rate and headline stay fixed. Macro event
markers sit on the timeline with explanations on hover. Clicking any point opens
the decomposition panel for that month.

**Headline CPI breakdown** — the slide-in panel, showing the hierarchy the way a
central bank reads it: headline splits into core and non-core, core splits into
services and core goods. Every node carries its own inflation rate, its
contribution to headline in percentage points, its share of the basket, and its
1-month and 12-month changes.

**Where the inflation came from** — stacked contributions summing to headline,
switchable to component rates or index levels. Note that only *contributions*
stack; the rate and index views render as lines, because component rates don't
sum to headline and pretending otherwise would misstate the data.

**What the Bank of England watches** — the indicators ranked by the weight they
actually carry in the decision, each with whether it reflects domestic pressure,
how volatile it is, and how far policy can reach it.

**Inflation vs rates** — the same series with periods of negative and positive
real policy rates shaded, plus the real rate itself as its own chart.

**Insight engine** — hovering any month regenerates a written read of that month
client-side. It is deterministic: it restates arithmetic already in the data and
asserts nothing beyond it. The Claude-written note is a separate, slower layer
covering the latest release.

---

## Data model

`data/timeseries.json` → `observations[]`, one row per month:

```jsonc
{
  "date": "2026-06",
  "headline_cpi": 2.6, "core_cpi": 2.58, "services_cpi": 3.6,
  "goods_cpi": 1.6, "core_goods_cpi": 0.73,
  "food_cpi": 1.7, "energy_cpi": 5.71, "alcohol_tobacco_cpi": 2.1,
  "wage_growth": 3.4,
  "policy_rate": 3.75, "real_rate": 1.15,
  "contributions": { "services": 1.71, "core_goods": 0.23, "food": 0.19,
                     "energy": 0.33, "alcohol_tobacco": 0.08, "other": 0.06 },
  "weights":       { "services": 473.7, "core_goods": 321.2, "food": 109.6,
                     "energy": 58.4, "alcohol_tobacco": 37.2 },
  "index":         { "headline": 141.2, "services": 149.9, "…": 0 },
  "mom":           { "headline_cpi": -0.2, "…": 0 }
}
```

`data/meta.json` holds the latest values, every Bank Rate change with its exact
decision date, the macro event list, the reaction-function flag, the diff from the
last run, source citations, and the full methodology note.

`data/commentary.json` holds the rolling log of Claude-written release notes.

### Series used

| Field | Source | Code |
|---|---|---|
| Headline CPI | ONS MM23 | `D7G7` |
| Services / Goods CPI | ONS MM23 | `D7NN` / `D7NM` |
| Food / Alcohol & tobacco | ONS MM23 | `D7G8` / `D7G9` |
| Core CPI (excl. energy, food, alcohol, tobacco) | ONS MM23 | `DKC6` (index → YoY) |
| Core goods (non-energy industrial goods) | ONS MM23 | `DK9J` (index → YoY) |
| Energy | ONS MM23 | `DK9T` (index → YoY) |
| Basket weights | ONS MM23 | `CHZR`, `CHZS`, `CJVF`, `CJXR` |
| Wage growth (regular pay, 3m YoY, SA) | ONS LMS | `KAI9` |
| Bank Rate | BoE IADB | `IUDBEDR` (daily, taken at month end) |

---

## Methodology, and where to be careful

**Contributions** are `weight/1000 × component rate`. The five modelled components
don't span the basket perfectly, so an explicit `other` residual reconciles them to
published headline CPI. It is shown in the UI rather than hidden — it is typically
under 0.1pp.

**The services weight is derived, not published.** ONS publishes goods and services
*rates* but not their weights in MM23. Since headline is a weighted average of the
two and the weights sum to 1000, the identity

```
w_services = 1000 × (headline − goods) / (services − goods)
```

pins it down each month. When goods and services inflation are within 0.5pp of each
other the denominator is unstable, so the code falls back to the published-basket
approximation. This is the least solid number on the dashboard; treat the services
contribution as indicative rather than exact.

**Core CPI is computed from the index**, not read from a rate series — ONS publishes
`DKC6` as an index only. The annual rate is the 12-month change in that index, which
is how ONS derives its own published rates, so the two agree to rounding.

**Bank Rate is the daily official rate at month end**, not a monthly average. That
keeps the series a step function reflecting actual MPC decisions rather than
smearing a mid-month change across two months. Exact decision dates are in
`meta.json → rate_changes`.

**The real rate is Bank Rate minus realised headline CPI.** The MPC sets policy
against *expected* inflation, so this is a backward-looking approximation — useful
for reading the stance at the time, not a measure the Bank itself targets.

---

## Charts

The categorical palette is validated, not chosen by eye. Colours come from a
validated dark ramp, and the slot order in `web/src/lib/series.js` is load-bearing:
legends, toggle rows and stack order all render in that sequence so every adjacent
pair clears the colour-vision-deficiency separation threshold. Aqua beside magenta,
or violet beside blue, both fail hard under deuteranopia — re-run the validator
before reordering or adding a hue.

Every series carries a legend swatch, and charts with four or fewer series also
carry direct end-of-line labels, so identity is never colour-alone.

---

## Not investment advice

This is a data visualisation of published official statistics. The written
commentary — deterministic and LLM-generated alike — describes what the data did.
It is not a forecast and not a recommendation.
