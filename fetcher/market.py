"""
MPC decisions and the "Synthetic MPC OIS Curve" — a market-implied Bank Rate
path built from public Bank of England data, standing in for Refinitiv's
meeting-dated OIS quotes (GBPMPCOISM1 / GBPMPCOISM2), to which we have no
entitled access. See docs/synthetic-mpc-ois-methodology.md for the full
analyst-facing writeup; this docstring is the short version.

Three things live here, all sourced from the Bank of England:

  * the voting history — every MPC Bank Rate decision since 1997 with the rate
    each individual member voted for, which is what lets the dashboard say who
    was hawkish and who was dovish at any given meeting;

  * the Bank's own calendar of scheduled-but-undecided future meeting dates,
    needed because the voting history only ever lists meetings that have
    already happened; and

  * the synthetic MPC OIS curve itself — a curve-implied OIS rate to each of
    the next few meeting dates, bootstrapped into the average SONIA the market
    expects between consecutive meetings, then converted to a Bank Rate
    expectation. See `bootstrap_expected_path` and `synthetic_mpc_curve` for
    the mechanics; both work entirely in discount-factor space (`curve_rate`,
    `curve_discount_factor`) rather than interpolating rates directly — see
    those functions' docstrings for why that distinction matters here.

If you do have the real Refinitiv meeting-dated quotes, drop a CSV at
data/ois_meetings.csv (columns: date,m1,m2, in percent) and it is used in
preference to the curve reconstruction on any date it covers.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import math
import re
import zipfile
from pathlib import Path

from .xlsx import Workbook, excel_date

# The two OIS legs are annualised percentages; ACT/365 matches the SONIA OIS
# convention the Bank's own curve is fitted to.
DAY_COUNT = 365.0

# Below this the bootstrap divides by a very small time gap and the result is
# noise rather than signal. Consecutive MPC meetings are never this close.
MIN_WINDOW_YEARS = 14.0 / DAY_COUNT

# The Bank's shortest published tenor is 1 month. Below this there is no curve
# point to interpolate from at all.
MIN_CURVE_TENOR_YEARS = 1.0 / 12.0


# --------------------------------------------------------------------------
# MPC voting history
# --------------------------------------------------------------------------

def _clean_name(raw: str) -> str:
    return " ".join(raw.replace("\n", " ").split())


def parse_mpc_votes(payload: bytes, sheet: str, start_month: str) -> list[dict]:
    """
    Parse the Bank's mpcvoting.xlsx into one record per meeting.

    Layout: a header row carries member names across the columns, then one row
    per meeting holding the meeting-end date, the Bank Rate that was decided,
    and — under each member's column — the Bank Rate that member voted for.
    Rates are stored as fractions (0.0425), so everything is scaled to percent.
    """
    book = Workbook(payload)
    rows = list(book.rows(sheet))

    names: dict[int, str] = {}
    for cells in rows:
        labels = [value for value in cells.values() if isinstance(value, str)]
        if "Current members" in labels:
            for column, value in cells.items():
                if column < 3 or not isinstance(value, str):
                    continue
                if value in ("Current members", "Past members"):
                    continue
                names[column] = _clean_name(value)
            break
    if not names:
        raise RuntimeError("could not find the member header row in the MPC voting sheet")

    meetings: list[dict] = []
    for cells in rows:
        when = excel_date(cells.get(1))
        if when is None:
            continue
        try:
            decided = float(cells.get(2)) * 100.0
        except (TypeError, ValueError):
            continue

        votes: dict[str, float] = {}
        for column, name in names.items():
            raw = cells.get(column)
            if raw is None:
                continue
            try:
                votes[name] = round(float(raw) * 100.0, 4)
            except (TypeError, ValueError):
                continue
        if not votes:
            continue

        meetings.append({
            "date": when.isoformat(),
            "month": f"{when.year:04d}-{when.month:02d}",
            "bank_rate": round(decided, 4),
            "votes": votes,
        })

    meetings.sort(key=lambda entry: entry["date"])
    # Keep one meeting of run-up before the dashboard window so the first
    # in-window decision can still be described as a cut, hold or rise.
    keep_from = next((i for i, m in enumerate(meetings) if m["month"] >= start_month), 0)
    return meetings[max(0, keep_from - 1):]


def summarise_votes(meetings: list[dict]) -> list[dict]:
    """
    Turn each meeting into the shape the dashboard renders: what was decided,
    how the vote split, and which members sat on which side of it.

    A member is hawkish at a meeting if the rate they voted for was above the
    rate the Committee settled on, and dovish if it was below — which is the
    only definition the published data supports, and the one the Bank's own
    minutes use when they describe members as preferring a higher or lower rate.
    """
    summaries: list[dict] = []
    previous: float | None = None

    for meeting in meetings:
        decided = meeting["bank_rate"]
        votes = meeting["votes"]

        with_majority, hawks, doves = [], [], []
        for name, vote in sorted(votes.items()):
            entry = {"name": name, "vote": vote}
            if vote > decided + 1e-9:
                hawks.append({**entry, "gap": round(vote - decided, 4)})
            elif vote < decided - 1e-9:
                doves.append({**entry, "gap": round(vote - decided, 4)})
            else:
                with_majority.append(entry)

        change = None if previous is None else round(decided - previous, 4)
        if change is None:
            action = "unknown"
        elif change > 1e-9:
            action = "hike"
        elif change < -1e-9:
            action = "cut"
        else:
            action = "hold"

        summaries.append({
            "date": meeting["date"],
            "month": meeting["month"],
            "bank_rate": decided,
            "previous_rate": previous,
            "change": change,
            "action": action,
            "split": f"{len(with_majority)}–{len(hawks) + len(doves)}",
            "majority": len(with_majority),
            "dissent": len(hawks) + len(doves),
            "unanimous": not hawks and not doves,
            "members": with_majority,
            "hawks": hawks,
            "doves": doves,
        })
        previous = decided

    return summaries


# --------------------------------------------------------------------------
# OIS curve
# --------------------------------------------------------------------------

def _short_end_sheet(book: Workbook) -> str:
    """
    The sheet carrying spot rates on the monthly tenor grid.

    Workbooks from 2016 onwards split the curve into a short end and a long
    end; the 2009-2015 workbook predates that split and publishes only the
    short grid, under the plain name.
    """
    spot = [name for name in book.sheet_names if "spot" in name.lower()]
    for name in spot:
        if "short" in name.lower():
            return name
    if spot:
        return spot[0]
    raise RuntimeError(f"no spot curve sheet in workbook ({', '.join(book.sheet_names)})")


def parse_ois_workbook(payload: bytes, start: dt.date,
                       curves: dict[str, list[tuple[float, float]]]) -> None:
    """
    Read one OIS workbook into `curves` as {ISO date: [(tenor years, rate %)]}.

    The Bank publishes the short end on a monthly tenor grid starting at one
    month. The header carries the grid twice, in months and in years; the years
    row is used because the bootstrap works in years.
    """
    book = Workbook(payload)
    tenors: list[tuple[int, float]] | None = None

    for cells in book.rows(_short_end_sheet(book)):
        label = (cells.get(0) or "").strip().lower()

        if label.startswith("years"):
            grid = []
            for column, value in sorted(cells.items()):
                if column == 0:
                    continue
                try:
                    grid.append((column, float(value)))
                except (TypeError, ValueError):
                    continue
            tenors = grid or None
            continue

        if tenors is None:
            continue

        when = excel_date(cells.get(0))
        if when is None or when < start:
            continue

        curve = []
        for column, tenor in tenors:
            raw = cells.get(column)
            if raw is None:
                continue
            try:
                curve.append((tenor, float(raw)))
            except (TypeError, ValueError):
                continue
        if len(curve) >= 2:
            curves[when.isoformat()] = curve


def parse_ois_archive(payload: bytes, start: dt.date,
                      curves: dict[str, list[tuple[float, float]]]) -> list[str]:
    """
    The Bank ships the OIS history as a zip of per-era workbooks.

    A workbook that cannot be read is skipped rather than fatal: the layout has
    changed once already, and losing one era of history is a better outcome
    than losing the whole series. Returns whatever went wrong, for logging.
    """
    problems: list[str] = []
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for name in archive.namelist():
            if not name.lower().endswith(".xlsx") or "ois" not in name.lower():
                continue
            try:
                parse_ois_workbook(archive.read(name), start, curves)
            except Exception as error:  # noqa: BLE001 - one bad era, not all of them
                problems.append(f"{name}: {error}")
    return problems


def _discount_factor(rate_pct: float, tenor: float) -> float:
    """
    ACT/365 discount factor implied by a continuously-compounded rate, in
    percent. The Bank's own yield-curve FAQ states plainly: "the yields (spot
    and forward) are continuously compounded and quoted on an annual basis" —
    so DF(T) = exp(-rT), not the simple-interest 1/(1+rT) an earlier version
    of this module used without checking the source's documented convention.
    """
    return math.exp(-rate_pct / 100.0 * tenor)


def _rate_from_df(df: float, tenor: float) -> float:
    """Invert a discount factor back to a continuously-compounded rate, in percent."""
    return -math.log(df) / tenor * 100.0


def curve_discount_factor(curve: list[tuple[float, float]], tenor: float) -> float | None:
    """
    Read the OIS curve's discount factor at `tenor` (years) by log-linear
    interpolation of discount factors between the two bracketing grid points.
    No extrapolation outside the published grid.

    Log-linear DF interpolation — equivalently, linear interpolation of the
    continuously-compounded zero rate, which is exactly what these rates are
    (see `_discount_factor`) — is the standard, arbitrage-consistent
    convention for curve building: it implies a piecewise-*flat* instantaneous
    forward rate between grid nodes. Linearly interpolating the simple rates
    instead — the previous approach here — implies no particular forward
    shape at all; it is just whatever curvature falls out of subtracting two
    lines, which has no term-structure interpretation and can, away from the
    calm middle of a curve, produce a forward rate that briefly runs the wrong
    way between two nodes even when the underlying rates are monotonic. That
    matters more here than on a generic curve, because the segment being read
    (a few weeks to a few months) is exactly where MPC-meeting-driven
    curvature is sharpest.
    """
    if not curve or tenor < curve[0][0] or tenor > curve[-1][0]:
        return None
    for (t0, r0), (t1, r1) in zip(curve, curve[1:]):
        if t0 <= tenor <= t1:
            if t1 - t0 < 1e-12:
                return _discount_factor(r0, t0)
            df0 = _discount_factor(r0, t0)
            df1 = _discount_factor(r1, t1)
            weight = (tenor - t0) / (t1 - t0)
            # Geometric interpolation of discount factors == linear
            # interpolation of ln(DF), i.e. a flat forward between the nodes.
            return df0 ** (1 - weight) * df1 ** weight
    return None


def curve_rate(curve: list[tuple[float, float]], tenor: float) -> float | None:
    """The curve's simple OIS rate at `tenor`, via discount-factor interpolation."""
    df = curve_discount_factor(curve, tenor)
    return None if df is None else _rate_from_df(df, tenor)


# --------------------------------------------------------------------------
# upcoming meeting dates
# --------------------------------------------------------------------------

_MONTHS_FULL = ["January", "February", "March", "April", "May", "June", "July",
                "August", "September", "October", "November", "December"]
_WEEKDAYS = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"


def parse_upcoming_meetings(html: str) -> list[str]:
    """
    Bank Rate decision dates that have not happened yet, from
    bankofengland.co.uk/monetary-policy/upcoming-mpc-dates.

    mpcvoting.xlsx only carries meetings that have already been decided, so it
    cannot tell the synthetic curve what "the next meeting" is on the days
    between the latest decided meeting and the next one — a gap of up to seven
    weeks. This page is the Bank's own published calendar (confirmed for the
    current year, provisional for next), and every row on it is an MPC Summary
    and minutes date, i.e. a Bank Rate decision.
    """
    month_number = {name: index + 1 for index, name in enumerate(_MONTHS_FULL)}
    cleaned = html.replace("&nbsp;", " ")
    months_pattern = "|".join(_MONTHS_FULL)

    dates: list[str] = []
    for year_block in re.finditer(
        r"<h2>\s*(\d{4})\s+(?:confirmed|provisional)\s+dates\s*</h2>(.*?)</table>",
        cleaned, re.S | re.I,
    ):
        year = int(year_block.group(1))
        for row in re.finditer(
            rf"<td>\s*(?:{_WEEKDAYS})\s+(\d{{1,2}})\s+({months_pattern})",
            year_block.group(2),
        ):
            day, month_name = int(row.group(1)), row.group(2)
            dates.append(f"{year:04d}-{month_number[month_name]:02d}-{day:02d}")

    return sorted(set(dates))


# --------------------------------------------------------------------------
# the SONIA-to-Bank-Rate spread
# --------------------------------------------------------------------------

# Walk-forward validated against 3 years of daily out-of-sample 1-day-ahead
# prediction error (MAE): Holt's linear trend beat every fixed-window
# trailing average tested (a 60-day trailing mean scored ~5x worse) and beat
# the best plain EWMA too, without that estimator's boundary-optimum
# ambiguity (EWMA's out-of-sample score kept improving as the halflife
# shrank, all the way to the edge of the grid tested — a sign it was
# degenerating toward "just use today", the single-noisy-day estimate this
# was built to avoid in the first place, rather than converging on a stable
# optimum). See docs/synthetic-mpc-ois-methodology.md for the full analysis,
# including why a flat multi-year average is actively wrong here: the spread
# ran ~4bp through the low-rate 2015-2020 era, 5-7bp through the 2021-2023
# hiking/QT-ramp-up cycle, and has been compressing back down since —
# 6.9bp (2023) to under 2bp (2026) — a genuine multi-year trend a flat
# average lags behind, not noise a flat average correctly smooths away.
HOLT_ALPHA = 0.3   # level smoothing
HOLT_BETA = 0.1    # trend smoothing


def holt_spread_series(dates: list[str], bank_rate: dict[str, float],
                       sonia: dict[str, float],
                       alpha: float = HOLT_ALPHA, beta: float = HOLT_BETA) -> dict[str, float]:
    """
    The SONIA-to-Bank-Rate spread (basis points), smoothed and trend-tracked
    day by day with Holt's linear method, across the full history.

    Holt's method keeps two running estimates — a level and a trend — and
    updates both from each new observation:

        level_t = alpha * y_t + (1 - alpha) * (level_{t-1} + trend_{t-1})
        trend_t = beta * (level_t - level_{t-1}) + (1 - beta) * trend_{t-1}

    `dates[i]`'s entry in the returned series is the level *after* folding in
    that day's observation — i.e. it is the estimate available at the close
    of that day, safe to use as "today's spread" with no look-ahead. This
    replaces a single fixed constant (or a flat trailing average, which the
    walk-forward test showed actively lags a real multi-year trend) with an
    estimator that adapts to the current regime while still not reacting to
    any single day's idiosyncratic noise the way using the raw daily spread
    outright would.
    """
    ordered = [d for d in dates if d in bank_rate and d in sonia]
    if not ordered:
        return {}

    series: dict[str, float] = {}
    first = (bank_rate[ordered[0]] - sonia[ordered[0]]) * 100.0
    level, trend = first, 0.0

    for when in ordered:
        y = (bank_rate[when] - sonia[when]) * 100.0
        prev_level = level
        level = alpha * y + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
        series[when] = level

    return series


# --------------------------------------------------------------------------
# the bootstrap
# --------------------------------------------------------------------------

def load_ois_override(path: Path) -> dict[str, tuple[float, float]]:
    """
    Optional Refinitiv passthrough: data/ois_meetings.csv with columns
    date,m1,m2 holding GBPMPCOISM1 and GBPMPCOISM2 in percent. Any date present
    here wins over the curve reconstruction.
    """
    if not path.exists():
        return {}
    override: dict[str, tuple[float, float]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            keys = {key.strip().lower(): value for key, value in row.items() if key}
            when, m1, m2 = keys.get("date"), keys.get("m1"), keys.get("m2")
            if not when or m1 in (None, "") or m2 in (None, ""):
                continue
            try:
                override[when.strip()[:10]] = (float(m1), float(m2))
            except ValueError:
                continue
    return override


def implied_probability(pricing_bp: float | None, step: float = 25.0) -> dict:
    """
    Quantise a continuous bp-priced move onto whole `step`-sized decisions.

    Trading desks reduce a priced move to "X% chance of a 25bp cut" by
    assuming the Committee only ever moves in whole steps — no 50bp surprises,
    no probability mass on anything but 0bp or `step`bp. Under that
    assumption, `pricing_bp` basis points priced decomposes into some number
    of *fully* priced steps plus a fractional next step:

        12.5bp priced  -> 0 full steps, 50% chance of the next 25bp step
        30.0bp priced  -> 1 full step (~certain), 20% chance of a second

    This is a simplification the desk itself knows is a simplification — real
    pricing can and does reflect a 50bp possibility — but it is the standard
    first-order read and it is what "probability of a cut" means in practice.
    """
    if pricing_bp is None:
        return {"direction": None, "full_steps_priced": None, "probability_next_step_pct": None}

    direction = "hike" if pricing_bp > 1e-9 else "cut" if pricing_bp < -1e-9 else "none"
    magnitude = abs(pricing_bp)
    full_steps = int(magnitude // step)
    remainder = magnitude - full_steps * step
    return {
        "direction": direction,
        "full_steps_priced": full_steps,
        "probability_next_step_pct": round(remainder / step * 100.0, 1),
    }


def _forward_leg(
    t1: float,
    t2: float,
    curve: list[tuple[float, float]],
    sonia_rate: float | None,
    override_leg: tuple[float, float] | None,
) -> tuple[float | None, float | None, str]:
    """
    The two discount factors needed for one bootstrap, plus where they came
    from. `override_leg`, if given, is (m1, m2) in percent from the Refinitiv
    passthrough CSV — used as-is rather than read off the curve.
    """
    if override_leg is not None:
        m1, m2 = override_leg
        return _discount_factor(m1, t1), _discount_factor(m2, t2), "refinitiv"

    df1 = curve_discount_factor(curve, t1)
    source = "boe_ois_curve"
    if df1 is None and t1 < MIN_CURVE_TENOR_YEARS and sonia_rate is not None:
        # No published grid point covers a meeting inside the next month (an
        # emergency meeting, or the last few days before a scheduled one) —
        # the shortest tenor the Bank publishes is 1 month. SONIA today is
        # the best available floor for that short a stub only; it is not used
        # anywhere else in this bootstrap.
        df1 = _discount_factor(sonia_rate, t1)
        source = "boe_ois_curve+sonia_floor"

    df2 = curve_discount_factor(curve, t2)
    return df1, df2, source


def bootstrap_expected_path(
    meeting_dates: list[str],
    sonia: dict[str, float],
    bank_rate: dict[str, float],
    curves: dict[str, list[tuple[float, float]]],
    spread: dict[str, float],
    override: dict[str, tuple[float, float]] | None = None,
) -> dict[str, dict]:
    """
    The average SONIA the market expects to prevail between the next MPC
    meeting (T1) and the one after it (T2), converted to a Bank Rate
    expectation — the "synthetic MPC OIS" forward for meeting 1.

    Two synthetic OIS legs are read off the curve on each date d:

        OIS(T1) = curve rate from d to the next meeting date
        OIS(T2) = curve rate from d to the meeting after that

    Both legs come from the same curve read, at the two meeting-date tenors —
    see `curve_rate`. (An earlier version of this function substituted today's
    SONIA fixing for OIS(T1), reasoning that no MPC decision falls before T1
    so the path must already be "known". That understates what OIS(T1) prices:
    the realised average of daily SONIA fixings between now and T1 is not a
    single known number even absent a rate change — it carries the market's
    read on money-market liquidity, and in particular the month-end and
    quarter-end reserve-scarcity effects that push SONIA away from Bank Rate
    on specific calendar dates, which a curve reading captures and a static
    spot fixing cannot.)

    Both legs are converted to discount factors and the forward is bootstrapped
    in discount-factor space. Because these are continuously-compounded rates
    (see `_discount_factor`), the exact forward identity is the log-difference
    of the two discount factors, not the simple ratio-minus-one:

        F = -ln(DF(T2) / DF(T1)) / (T2 - T1)

    F is a SONIA-space forward. SONIA structurally fixes below Bank Rate (the
    corridor the Bank's operations are run within), so `spread` — the Holt's-
    smoothed spread estimate for this date, see `holt_spread_series` — converts
    it onto the Bank Rate scale:

        implied_rate = F + spread[when] / 100

    The remaining approximation: the Bank's curve is a smoothing fit across
    all tenors, so it blurs the step the market actually prices at each
    meeting date rather than reproducing it exactly the way a genuinely
    meeting-dated quote (Refinitiv GBPMPCOISM1/M2) would. See the module
    docstring for the CSV override that removes this approximation entirely
    when those quotes are available.
    """
    override = override or {}
    boundaries = sorted(set(meeting_dates))

    path: dict[str, dict] = {}

    for when in sorted(set(curves) | set(override)):
        upcoming = [date for date in boundaries if date > when][:2]
        if len(upcoming) < 2:
            continue

        day = dt.date.fromisoformat(when)
        t1 = (dt.date.fromisoformat(upcoming[0]) - day).days / DAY_COUNT
        t2 = (dt.date.fromisoformat(upcoming[1]) - day).days / DAY_COUNT
        if t1 <= 0 or t2 - t1 < MIN_WINDOW_YEARS:
            continue

        policy = bank_rate.get(when)
        spread_bp = spread.get(when)
        if policy is None or spread_bp is None:
            continue

        df1, df2, source = _forward_leg(
            t1, t2, curves.get(when) or [], sonia.get(when), override.get(when),
        )
        if df1 is None or df2 is None:
            continue

        forward = -math.log(df2 / df1) / (t2 - t1) * 100.0
        implied_rate = forward + spread_bp / 100.0
        pricing_bp = (implied_rate - policy) * 100.0

        path[when] = {
            "date": when,
            "meeting_1": upcoming[0],
            "meeting_2": upcoming[1],
            "ois_m1": round(_rate_from_df(df1, t1), 4),
            "ois_m2": round(_rate_from_df(df2, t2), 4),
            "implied_sonia": round(forward, 4),
            "implied_rate": round(implied_rate, 4),
            "bank_rate": round(policy, 4),
            "spread_bps": round(spread_bp, 2),
            "pricing_bp": round(pricing_bp, 1),
            **implied_probability(pricing_bp),
            "source": source,
        }

    return path


def monthly_expected_path(path: dict[str, dict]) -> dict[str, dict]:
    """Reduce the daily path to month-end, matching how Bank Rate is stored."""
    monthly: dict[str, dict] = {}
    for when in sorted(path):
        monthly[when[:7]] = path[when]  # last write wins = month end
    return monthly


def synthetic_mpc_curve(
    when: str,
    meeting_dates: list[str],
    curves: dict[str, list[tuple[float, float]]],
    sonia: dict[str, float],
    bank_rate: dict[str, float],
    spread_bps: float,
    override: dict[str, tuple[float, float]] | None = None,
    n: int = 3,
) -> list[dict]:
    """
    The full synthetic MPC OIS curve as of one date: the next `n` meetings,
    row i showing what meeting i is expected to *decide*.

    That is the forward rate for the window starting right after meeting i's
    decision and running to the meeting after it — [T_i, T_{i+1}) — not the
    window ending at T_i. An earlier version of this function attributed the
    window *ending* at each meeting to that meeting's row, which for the
    first meeting in particular is wrong in a way that matters: the window
    [when, T_1) can't contain any decision at all (nothing falls before the
    first meeting), so it is close to the current rate almost by definition,
    telling you essentially nothing about what that meeting will do. What the
    market actually expects meeting i to decide only shows up in the *next*
    leg — the window immediately after it. Because row i needs the meeting
    *after* it to compute its own forward, this function looks one meeting
    further than `n` — `n + 1` dates — to be able to fill in all `n` rows.
    """
    override = override or {}
    upcoming = sorted(date for date in set(meeting_dates) if date > when)[:n + 1]
    if len(upcoming) < 2:
        return []

    curve = curves.get(when) or []
    sonia_rate = sonia.get(when)
    policy = bank_rate.get(when)
    day = dt.date.fromisoformat(when)

    def df_at(meeting: str, tenor: float) -> tuple[float | None, str]:
        if meeting in override:
            m1, _ = override[meeting]
            return _discount_factor(m1, tenor), "refinitiv"
        df = curve_discount_factor(curve, tenor)
        if df is None and tenor < MIN_CURVE_TENOR_YEARS and sonia_rate is not None:
            return _discount_factor(sonia_rate, tenor), "boe_ois_curve+sonia_floor"
        return df, "boe_ois_curve"

    legs = []
    for meeting in upcoming:
        tenor = (dt.date.fromisoformat(meeting) - day).days / DAY_COUNT
        df, source = df_at(meeting, tenor)
        legs.append((meeting, tenor, df, source))

    rows: list[dict] = []
    for (m_cur, t_cur, df_cur, source_cur), (_, t_next, df_next, _) in zip(legs, legs[1:]):
        if df_cur is None or df_next is None or policy is None:
            rows.append({
                "meeting": m_cur, "tenor_days": round(t_cur * DAY_COUNT),
                "synthetic_ois": None, "implied_sonia": None, "implied_rate": None,
                "pricing_bp": None, "direction": None,
                "full_steps_priced": None, "probability_next_step_pct": None,
                "source": None,
            })
            continue

        forward = -math.log(df_next / df_cur) / (t_next - t_cur) * 100.0
        implied_rate = forward + spread_bps / 100.0
        pricing_bp = (implied_rate - policy) * 100.0

        rows.append({
            "meeting": m_cur,
            "tenor_days": round(t_cur * DAY_COUNT),
            "synthetic_ois": round(_rate_from_df(df_cur, t_cur), 4),
            "implied_sonia": round(forward, 4),
            "implied_rate": round(implied_rate, 4),
            "pricing_bp": round(pricing_bp, 1),
            **implied_probability(pricing_bp),
            "source": source_cur,
        })

    return rows


def attach_market_pricing(decisions: list[dict], path: dict[str, dict]) -> None:
    """
    For every decision, what the market had priced going into it.

    The value is taken from the last date before the meeting on which the
    bootstrap produced a number — on that date, meeting 1 *is* this meeting, so
    the forward is precisely the level the market expected this meeting to set.
    """
    dates = sorted(path)
    fields = ("priced", "priced_on", "surprise", "pricing_bp", "direction",
              "full_steps_priced", "probability_next_step_pct")

    for decision in decisions:
        prior = [when for when in dates if when < decision["date"]]
        entry = path[prior[-1]] if prior else None

        # Only meaningful if the bootstrap was looking at this meeting.
        if entry is None or entry["meeting_1"] != decision["date"]:
            for field in fields:
                decision[field] = None
            continue

        decision["priced"] = entry["implied_rate"]
        decision["priced_on"] = entry["date"]
        decision["surprise"] = round(decision["bank_rate"] - entry["implied_rate"], 4)
        decision["pricing_bp"] = entry["pricing_bp"]
        decision["direction"] = entry["direction"]
        decision["full_steps_priced"] = entry["full_steps_priced"]
        decision["probability_next_step_pct"] = entry["probability_next_step_pct"]
