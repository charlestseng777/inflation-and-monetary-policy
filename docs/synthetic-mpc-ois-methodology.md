# Synthetic MPC OIS Curve — methodology

**Status:** implemented in [`fetcher/market.py`](../fetcher/market.py), wired in
[`fetcher/fetch.py`](../fetcher/fetch.py), rendered on the dashboard's "Inflation vs
rates" tab.

## 0. Why this exists

The dashboard wants a market-implied Bank Rate path — what OIS pricing says the MPC
will do at its next few meetings. The natural source is Refinitiv's meeting-dated OIS
quotes, `GBPMPCOISM1` / `GBPMPCOISM2` / `GBPMPCOISM3` — the two or three legs a
meeting-to-meeting forward bootstrap needs, already quoted directly against MPC dates
by the market. This deployment has no entitled access to LSEG/Refinitiv data (every
Datastream, QA-macro and historical-pricing tool returns an entitlement error for this
account), so the curve below reconstructs the same quantity from data the Bank of
England itself publishes, for free, with no authentication.

This is a substitute, not a claim of equivalence. Section 7 states plainly where the
two would disagree and by how much.

## 1. Data inputs required

| Input | Source | Series / file | Frequency |
|---|---|---|---|
| Official Bank Rate | BoE Interactive Statistical Database | `IUDBEDR` | Daily |
| SONIA (overnight rate) | BoE Interactive Statistical Database | `IUDSOIA` | Daily |
| UK OIS spot curve, short end | BoE yield-curve archive | `oisddata.zip`, `latest-yield-curve-data.zip`, sheet *"…spot, short end"* | Daily, monthly tenor grid, 1M–60M |
| MPC voting history | BoE `mpcvoting.xlsx` | Sheet *"Bank Rate Decisions"* | Per meeting, back to 1997 |
| Upcoming MPC dates | `bankofengland.co.uk/monetary-policy/upcoming-mpc-dates` | HTML table, confirmed (current year) + provisional (next year) | Per meeting |
| *(optional)* Refinitiv meeting-dated OIS | `data/ois_meetings.csv`, columns `date,m1,m2` | User-supplied | Per day, if available |

All of the above are fetched with the standard library only — no paid data
dependency. See [`fetcher/xlsx.py`](../fetcher/xlsx.py) for the `.xlsx` reader
this pipeline uses instead of a heavyweight spreadsheet library.

## 2. Notation

| Symbol | Meaning |
|---|---|
| `d` | The valuation date (today, or any historical date in the series) |
| `T1, T2, T3, …` | The next MPC meeting dates after `d`, in order |
| `r(T)` | The OIS spot rate to date `T`, read off the curve — continuously compounded, ACT/365 (the Bank's own stated convention; see Section 3) |
| `DF(T)` | The discount factor implied by `r(T)` |
| `B0` | Bank Rate prevailing on `d` |
| `spread` | SONIA-to-Bank-Rate spread, day-by-day, from Holt's linear trend smoothing of the realised gap — not a fixed constant (see Section 7) |

## 3. Curve interpolation — discount factors, not rates

The Bank publishes the curve on a monthly tenor grid (1M, 2M, 3M, … 60M). An MPC
meeting date essentially never lands exactly on a grid point, so every read of the
curve requires interpolation.

**Requirement: interpolate discount factors, not rates directly.**

Convert every grid point to a discount factor first. The Bank's own yield-curve FAQ
states plainly: *"the yields (spot and forward) are continuously compounded and quoted
on an annual basis"* — so, ACT/365, continuously compounded:

```
DF(T) = exp(−r(T) · T)
```

(An earlier version of this pipeline used the simple-interest form, `1/(1+rT)`,
without checking the source's own stated convention. The two agree closely at these
tenors and rates — see the worked example below — but only one of them is what the
Bank actually publishes.)

To read the curve at an arbitrary tenor `Tx` between two grid points `Ta < Tx < Tb`,
interpolate **log-linearly in discount-factor space** — equivalently, linearly
interpolate the continuously-compounded zero rate, which is exactly what these rates
already are:

```
w = (Tx − Ta) / (Tb − Ta)
DF(Tx) = DF(Ta)^(1−w) · DF(Tb)^w
r(Tx) = −ln(DF(Tx)) / Tx
```

Implementation: [`curve_discount_factor`](../fetcher/market.py) /
[`curve_rate`](../fetcher/market.py).

### Why this is mathematically superior to linear rate interpolation

Log-linear DF interpolation is the standard, arbitrage-consistent curve-building
convention because it implies a **piecewise-flat instantaneous forward rate** between
grid nodes — the same "flat forward" assumption every production curve-building
library (QuantLib, Bloomberg's curve construction, etc.) defaults to. Given two spot
points, there is exactly one forward-rate shape between them that is *constant*
(the flat forward); log-linear DF interpolation reproduces it. Linearly interpolating
the *rates* instead has no such interpretation — it is simply the straight line
between two `(T, r)` points, and the forward rate implied by that line has whatever
shape falls out of the subtraction, with no term-structure meaning. Away from the
calm middle of a curve it can even imply the forward running briefly the *wrong way*
between two nodes that are both, individually, unremarkable.

That distinction matters more here than on a generic curve, precisely because the
segment being read — a few weeks to a few months, spanning MPC meeting dates — is
where curvature driven by anticipated policy moves is sharpest. A forward-rate
artefact of the interpolation method is least tolerable exactly where the forward
rate is the object being measured.

**Worked example** (values below verified numerically, not by hand). Suppose the
published grid carries:

| Tenor | Rate |
|---|---|
| 2M (T=0.16667y) | 4.10% |
| 3M (T=0.25000y) | 3.98% |

Target: 83 days out (a meeting date), `Tx = 0.22740y`.

```
DF(2M) = exp(−0.0410 × 0.16667) = 0.993190
DF(3M) = exp(−0.0398 × 0.25000) = 0.990099

w = (0.22740 − 0.16667) / (0.25000 − 0.16667) = 0.72877

DF(Tx) = 0.993190^(1−0.72877) × 0.990099^0.72877
       = 0.993190^0.27123 × 0.990099^0.72877
       = 0.990937

r(Tx) = −ln(0.990937) / 0.22740 × 100 = 4.0039%
```

Plain linear interpolation of the two *rates* over the same weight gives
`4.10 + 0.72877 × (3.98 − 4.10) = 4.0125%` — **0.87bp higher** than the DF-consistent
read on this fairly ordinary, nearly-flat two-point segment. The gap widens with the
curvature between the nodes; near a sharply priced meeting it is larger still. Neither
number is "wrong" in the sense of a bug — they are two different, both internally
consistent, interpolation conventions. The point is that only one of them (DF
log-linear) has a term-structure interpretation, which is why it is the one used here.

## 4. `OIS(T1)` is read from the curve, not proxied by spot SONIA

An earlier version of this pipeline reasoned that, because no MPC decision falls
before the next meeting, the overnight-rate path over `[d, T1)` is "already known", and
substituted today's SONIA fixing for the `OIS(T1)` leg. That understates what a real
`OIS(T1)` quote (or, here, the curve read at `T1`) actually prices:

- **Expected SONIA fixings.** SONIA is not a single fixed number even absent a rate
  change — it is a distribution of daily fixings, and today's single print is one
  draw from it, not the market's expectation of the average over the coming weeks.
- **Liquidity effects.** OIS pricing embeds dealer balance-sheet and funding costs
  that a spot fixing does not.
- **Month-end / quarter-end effects.** GBP money markets see well-documented SONIA
  spikes around regulatory reporting dates (balance-sheet "window dressing"). If
  `[d, T1)` spans a month-end, `OIS(T1)` prices that in; a static SONIA fixing from
  today cannot.
- **Pre-meeting positioning.** A data print or a speech between `d` and `T1` can shift
  the market's near-term rate view before the meeting itself; `OIS(T1)` reflects that
  in real time, a backward-looking fixing does not.

**Fix:** `OIS(T1)` is read off the same curve as `OIS(T2)`, at the `T1` tenor, using the
DF interpolation above — no SONIA substitution. SONIA is retained only as a floor for
the (rare) case where a meeting falls inside the Bank's shortest published tenor
(1 month) — see `MIN_CURVE_TENOR_YEARS` in the code — and is otherwise unused in the
bootstrap.

## 5. The synthetic MPC OIS curve

For a valuation date `d` and the next `n` MPC meeting dates `T1 < T2 < T3 < …`
(sourced from the voting history for past meetings, and from the Bank's own upcoming-
dates calendar for meetings that have not happened yet — the voting history only ever
lists decided meetings, so it cannot say what "the next meeting" is on the days
between the latest decision and the next one):

```
OIS(T1), OIS(T2), OIS(T3), …
```

read directly off the curve at each meeting's tenor. **These are not Bloomberg or
Refinitiv MPC OIS contracts.** They are synthetic points: the generic OIS spot curve,
sampled at MPC-meeting maturities instead of round calendar tenors. Nothing about the
curve's own construction is meeting-aware.

Implementation: [`synthetic_mpc_curve`](../fetcher/market.py).

## 6. Bootstrapping the inter-meeting forward — and which window belongs to which meeting

Given two curve reads at `T1` and `T2` (or `T2` and `T3`, and so on), the average
SONIA the market expects to prevail in the window *between* them is the discount-
factor forward. Because these are continuously-compounded rates (Section 3), the
exact identity is the log-difference of the two discount factors:

```
F(T1,T2) = −ln( DF(T2) / DF(T1) ) / (T2 − T1)
```

not the simple-forward shortcut `(DF(T1)/DF(T2) − 1)/(T2−T1)`, which is only exact
for simple-interest discount factors.

**This window — `[T1, T2)` — is what meeting 1 is expected to *decide*.** It starts
right after meeting 1's decision takes effect and runs to the meeting after it, so it
is the average rate the market expects meeting 1 to set and hold. This point is worth
stating carefully, because an earlier version of the point-in-time snapshot table
(Section 5) got it backwards: it attributed the window *ending* at each meeting —
`[d, T1)` for the first row — to that meeting, reasoning that meeting 1's own
synthetic OIS "is" what's priced for it. That window can't actually reflect meeting
1's decision at all: nothing can move Bank Rate before the meeting happens, so
`[d, T1)` is close to today's rate almost by construction, regardless of what the
market expects meeting 1 to do. What the market expects meeting 1 to decide only
shows up in the *next* leg, `[T1, T2)`. The daily historical bootstrap
(`bootstrap_expected_path`) always used the correct window; the fix was isolated to
`synthetic_mpc_curve`, which now looks one meeting further ahead than it displays —
`n + 1` meeting dates for `n` rows — specifically so each row can compute the forward
that starts at it, not the one that ends at it.

`F` is **the average overnight rate the market expects to prevail in that window** —
it is not a probability distribution over the decision itself, and it is not
guaranteed to equal the rate immediately after the meeting if the market expects the
rate to keep moving mid-window (which does not happen in practice, since Bank Rate
only changes at meetings, but is worth stating precisely: `F` prices the whole
window, not the instant after the decision).

Implementation: [`bootstrap_expected_path`](../fetcher/market.py) (historical, per
day) and [`synthetic_mpc_curve`](../fetcher/market.py) (the full forward-meeting
curve as of one date).

## 7. SONIA → Bank Rate: a trend-tracked spread, not a fixed constant

`F` is a SONIA-space number. SONIA structurally fixes below Bank Rate (a feature of
the corridor the Bank's operations are run within), so:

```
implied_rate = F + spread(d) / 100
```

### Why not a fixed constant

An earlier version of this pipeline used a single fixed assumption for `spread`
everywhere (5bp). Ten years of the Bank's own published Bank Rate and SONIA data says
that is not defensible: the realised spread has moved through genuinely different
regimes, not noise around a stable mean —

| Period | Mean realised spread |
|---|---|
| 2015–2020 (near-zero rates) | ~4bp |
| 2021 | ~5bp |
| 2022–2023 (hiking cycle, QT ramp-up) | ~6–7bp |
| 2024 | ~5bp |
| 2025–2026 (cutting cycle) | compressing toward ~2bp |

A single constant is wrong for most of that history by construction; it can only be
right for whichever regime it happened to be calibrated against.

### Why not the day's raw realised gap, either

The obvious fix — use each day's actual `Bank Rate − SONIA` — was the original
design's explicit reason for *not* doing that: the daily gap is noisy (month-end and
quarter-end reserve effects push it around from one day to the next), and that noise
would leak straight into the rate expectation being estimated.

### What's actually used: Holt's linear trend

`spread(d)` is the Bank Rate-minus-SONIA gap, in basis points, smoothed and
trend-tracked day by day with **Holt's linear method** — two running estimates, a
level and a trend, each updated from every new observation:

```
level_t = α · y_t + (1 − α) · (level_{t−1} + trend_{t−1})
trend_t = β · (level_t − level_{t−1}) + (1 − β) · trend_{t−1}
```

with `α = 0.3`, `β = 0.1` — chosen by walk-forward grid search (see below), not by
inspection. `spread(d)` is `level_d`, i.e. the estimate available at the close of day
`d`, computed from every day back to 2015 for both the historical series and the
live snapshot, so nothing here uses information from after the date it's describing.

**Why Holt's, specifically:** it was one of several candidates tested honestly —
against 3 years of genuine out-of-sample, walk-forward 1-day-ahead prediction error
(never trained or tuned on the day being predicted):

| Estimator | Out-of-sample MAE |
|---|---|
| Fixed 5bp constant | (not comparable — a constant has no forecasting skill by design) |
| 60-day trailing mean | 0.190bp |
| 120-day trailing mean | 0.385bp |
| Short EWMA (10-day halflife) | 0.105bp |
| **Holt's linear trend (α=0.3, β=0.1)** | **0.040bp** |

Flat trailing averages score worse the longer their window, which is the signature of
lagging a real trend rather than smoothing away noise — exactly consistent with the
regime table above. Holt's wins because it can track the trend a flat average always
lags one step behind. It was also tested against a reserves-conditioned linear
regression (spread regressed on the BoE's APF gilt-stock holdings, a plausible causal
driver via QT-induced reserve scarcity): that scored a respectable in-sample R² of
0.36–0.38, but failed badly walk-forward (2.15bp out-of-sample MAE — 11x worse than
Holt's — and it currently overstates the live spread by more than 2x), so it was
rejected despite the appealing in-sample story. Implementation:
[`holt_spread_series`](../fetcher/market.py).

## 8. Basis points priced, and the probability of a 25bp move

For any point on the synthetic curve, with `B0` the Bank Rate prevailing on the
pricing date:

```
pricing_bp = (implied_rate − B0) × 100
```

**Example:** `B0 = 4.25%`, `implied_rate = 4.00%` → `pricing_bp = −25.0` →
**"25bp cut priced."**

### Quantised probability of a 25bp move

Desks reduce a continuous bp-priced move to "X% chance of a 25bp cut" by assuming the
Committee only ever moves in whole 25bp steps — no probability mass on a 50bp
surprise. Under that assumption, `pricing_bp` decomposes into whole fully-priced
steps plus a fractional next step:

```
magnitude = |pricing_bp|
full_steps = floor(magnitude / 25)
remainder = magnitude − full_steps × 25
probability_of_next_step = remainder / 25
```

**Example:** 12.5bp priced → `full_steps = 0`, `remainder = 12.5` →
**50% probability of a 25bp move.** 30bp priced → `full_steps = 1` (a 25bp move
essentially fully priced), `remainder = 5` → **20% probability of a second 25bp move.**

This is a known simplification — real pricing can and does reflect a genuine 50bp
possibility, which this decomposition cannot see — but it is the standard first-order
desk read, and it is what "probability of a cut" conventionally means in practice.

Implementation: [`implied_probability`](../fetcher/market.py).

## 9. Python implementation steps

1. **Fetch.** Daily Bank Rate and SONIA from the IADB; the OIS spot-curve workbooks
   (archive + latest-month); `mpcvoting.xlsx`; the upcoming-MPC-dates HTML page.
   All stdlib `urllib` — see `fetcher/fetch.py`.
2. **Parse.** `xlsx.Workbook` streams the voting and curve workbooks without a
   spreadsheet dependency; `market.parse_mpc_votes` and `market.parse_ois_workbook`
   turn them into `{date: rate}` / `{date: [(tenor, rate)]}` dictionaries;
   `market.parse_upcoming_meetings` regex-parses the calendar HTML.
3. **Curve reads.** `market.curve_discount_factor` / `market.curve_rate` — log-linear
   DF interpolation over continuously-compounded rates, Section 3.
4. **Spread.** `market.holt_spread_series` — Holt's linear trend over the full
   Bank-Rate/SONIA history, Section 7.
5. **Bootstrap.** `market.bootstrap_expected_path` for the full daily history;
   `market.synthetic_mpc_curve` for a point-in-time, multi-meeting snapshot (fetching
   `n + 1` meeting dates for `n` rows — Section 6) — both apply Sections 4–7.
6. **Pricing metrics.** `market.implied_probability`, folded into both of the above.
7. **Attach to decisions.** `market.attach_market_pricing` matches each realised MPC
   decision to what was priced going into it, for the "surprise" read.
8. **Persist.** `fetch.build_panel` writes `expected_rate`, `ois_m1`, `ois_m2`,
   `pricing_bp`, `ois_3m`, `ois_2y` per month; `meta.json` carries `mpc_decisions` and
   the latest `synthetic_mpc_curve` snapshot, including the spread estimate used.

## 10. Output table example

Live snapshot as of **13 August 2026** (Holt's spread estimate: 1.84bp), Bank Rate
3.75%. Each row is what that meeting is expected to decide (Section 6) — note this is
*not* the same window as that meeting's own "Synthetic OIS" column:

| MPC meeting | Synthetic OIS | Implied SONIA | Implied Bank Rate | Market pricing |
|---|---|---|---|---|
| 17 Sep 2026 (T+35d) | 3.73% | 3.79% | 3.81% | 5.6bp hike priced (22.6% prob. of 25bp) |
| 5 Nov 2026 (T+84d) | 3.77% | 3.88% | 3.90% | 15.1bp hike priced (60.6% prob. of 25bp) |
| 17 Dec 2026 (T+126d) | 3.80% | 3.99% | 4.01% | 25.5bp — a 25bp hike essentially fully priced, plus a 2.2% chance of a second |

Read: a steady hawkish drift — rising conviction on a hike at each successive
meeting, consistent with the 2-year OIS point sitting well above spot (Section 11
covers where this reconstruction is likely to be least reliable). This table is
rendered live on the dashboard's rates tab ("Synthetic MPC OIS Curve"), recomputed
from the latest data on every fetcher run.

### Validation against known history

Applied to the historical series, the reconstruction recovers well-known BoE
surprises without being told about them: a −17.2bp dovish surprise at the November
2021 meeting (the widely reported instance of the Bank holding against a near-priced
hike), a +18.6bp hawkish surprise in July 2016 (holding post-Brexit-referendum against
priced cut expectations, which came the following month instead), and a −29.1bp
dovish surprise in September 2022 (a 50bp hike delivered against pricing for more,
the meeting immediately before the mini-Budget). Average absolute surprise across the
102 decisions since 2015 with pricing data is ~3bp — a sane order of magnitude for a
"how close was the market" metric.

## 11. Strengths and limitations

**Strengths**

- Built entirely from data the Bank of England itself publishes — no paid entitlement,
  no third-party dependency, reproducible by anyone.
- Internally consistent curve mathematics throughout: one interpolation convention
  (log-linear DF), one forward-bootstrap identity, applied uniformly from the daily
  historical series through to the point-in-time snapshot table.
- A reasonable, historically-validated proxy for genuine MPC OIS pricing — recovers
  known surprises at plausible magnitudes (Section 10).
- Transparent about its own approximation: every computed point carries a `source`
  tag (`boe_ois_curve`, `boe_ois_curve+sonia_floor`, or `refinitiv` when a real quote
  is supplied), so the provenance of any given number is always inspectable.

**Limitations**

- **The curve is a smoothing fit**, not a meeting-aware instrument. It is fitted
  across all tenors to be smooth; the true expected-rate path is a step function that
  can only move on eight fixed dates a year. The fit blurs that step rather than
  reproducing it, understating the sharpness of pricing around a genuinely contested
  meeting.
- **It does not explicitly incorporate MPC meeting dates** in its own construction —
  meeting-date tenors are simply read off a curve that was built without reference to
  them, which is precisely the gap true meeting-dated OIS quotes (Refinitiv
  `GBPMPCOISM1`/`M2`/`M3`) are designed to close.
- **Interpolation introduces approximation error**, quantified in the worked example
  in Section 3 — small on a calm curve, larger where curvature is sharp.
- **The bootstrapped forward is an average expected overnight rate over a window**,
  not a guaranteed post-meeting Bank Rate — see the precision note at the end of
  Section 6.
- **Market expectations embed risk premia and liquidity effects** beyond a pure
  rate-path forecast; none of the above separates a "pure" expectation from the
  premium riding on top of it.
- **The spread estimator is still a statistical smoother, not a causal model.**
  Holt's linear trend earned its place by walk-forward evidence (Section 7), but it
  is extrapolating the *spread's own recent path* — it has no way to see a genuine
  regime break (a change to the Bank's operational framework, a fiscal-driven reserve
  shock) coming before the data itself starts moving. The reserves-conditioned
  regression that was tried instead — and rejected for scoring 11x worse
  out-of-sample despite a superficially attractive in-sample fit — is a cautionary
  tale for taking any one alternative's in-sample story at face value without the
  same walk-forward test.

If genuine Refinitiv `GBPMPCOISM1`/`M2` access becomes available, supplying it via
`data/ois_meetings.csv` removes the curve-smoothing and interpolation approximations
entirely for any date it covers, with no code change required.

## 12. Use in GBP/USD analysis

A meeting-dated policy curve is most useful for FX not as a level, but as an input to
**relative policy-path pricing**. GBP/USD carry and medium-term positioning are driven
less by the absolute Bank Rate than by how the market's priced BoE path is moving
*relative to* its priced Fed path — the rate-differential trade. Two direct
applications:

1. **Divergence trades.** Compute the same construction for USD (SOFR OIS to FOMC
   meeting dates) and compare `pricing_bp` curves side by side. A widening gap between
   the two — say, the BoE curve building in hikes while the Fed curve is flat or
   easing — is a classic GBP-supportive divergence signal, readable directly off the
   two tables without needing either central bank to have said anything new.
2. **Surprise-driven repricing.** The `surprise` field (Section 10) isolates the part
   of a decision that was *not* already priced in. FX moves on a meeting are
   dominated by the surprise component, not the level — a hold that was 100% priced
   moves GBP far less than a hold that was priced as a 70% chance of a hike. Screening
   historical surprises against realised GBP/USD moves around the same dates is a
   natural way to calibrate how much of this dashboard's "surprise" metric is actually
   FX-relevant at this point in the cycle, versus already arbitraged away by the time
   the fixing prints.

Neither of these requires trusting the curve-smoothing approximation to be perfect —
both work off the *direction and relative size* of the priced move, which is far more
robust to the approximation error in Section 11 than the absolute level is.
