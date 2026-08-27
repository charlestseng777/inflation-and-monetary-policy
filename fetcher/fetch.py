#!/usr/bin/env python3
"""
UK inflation & monetary policy fetcher.

Pulls CPI series from the ONS and Bank Rate, SONIA, the OIS curve and the MPC
voting history from the Bank of England, derives the CPI decomposition and the
market-implied policy path used by the dashboard, diffs the result against what
was last stored, and (optionally) asks Claude to write a short plain-English
note about what changed.

Everything except the Claude call uses the standard library, so the script
runs on a bare Python 3.9+ install. The Claude step is skipped with a warning
if `anthropic` is not installed or ANTHROPIC_API_KEY is unset.

Usage:
    python fetcher/fetch.py                # fetch, diff, write, comment
    python fetcher/fetch.py --no-llm       # skip the commentary step
    python fetcher/fetch.py --force        # write + comment even with no diff
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"

# Run as `python fetcher/fetch.py`, sys.path[0] is fetcher/ — put the repo root
# on the path so the shared database layer in backend/ and this package's own
# sibling modules are importable either way.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fetcher import market, mpc_news, mpc_summary  # noqa: E402 - needs the sys.path line above

USER_AGENT = "uk-inflation-dashboard/1.0 (+https://github.com/)"
TIMEOUT = 60

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Series where a month-on-month move of this size or more is worth flagging
# in the commentary prompt as a notable change.
NOTABLE_MOVE_PP = 0.3


# --------------------------------------------------------------------------
# plumbing
# --------------------------------------------------------------------------

def log(msg: str) -> None:
    print(f"[fetch] {msg}", flush=True)


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def http_get_json(url: str) -> Any:
    return json.loads(http_get(url).decode("utf-8"))


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def month_key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def shift_month(key: str, delta: int) -> str:
    year, month = int(key[:4]), int(key[5:7])
    total = year * 12 + (month - 1) + delta
    return month_key(total // 12, total % 12 + 1)


def rounded(value: float | None, places: int = 2) -> float | None:
    return None if value is None else round(value + 0.0, places)


# --------------------------------------------------------------------------
# ONS
# --------------------------------------------------------------------------

def parse_ons_month(entry: dict) -> str | None:
    """ONS month entries look like {"date": "2021 JAN", "month": "January", ...}."""
    month_name = (entry.get("month") or "").strip().lower()[:3]
    year_text = (entry.get("year") or "").strip()
    if month_name in MONTHS and year_text.isdigit():
        return month_key(int(year_text), MONTHS[month_name])

    parts = (entry.get("date") or "").strip().split()
    if len(parts) == 2 and parts[0].isdigit():
        abbrev = parts[1].lower()[:3]
        if abbrev in MONTHS:
            return month_key(int(parts[0]), MONTHS[abbrev])
    return None


def parse_value(raw: Any) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "")
    if text in ("", "..", "-", "n/a"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_ons_next_release(text: str | None) -> str | None:
    """ONS gives this as free text like '19 August 2026' (occasionally with a
    doubled space) -- normalise and parse to an ISO date, or None if it isn't
    a clean single date (ONS sometimes writes a range or 'To be confirmed')."""
    if not text:
        return None
    cleaned = " ".join(text.split())
    try:
        return datetime.strptime(cleaned, "%d %B %Y").date().isoformat()
    except ValueError:
        return None


def fetch_ons_series(config: dict, cdid: str, dataset: str) -> dict:
    """Return {'title', 'months': {YYYY-MM: float}, 'years': {YYYY: float}, 'next_release'}."""
    template = config["ons"]["datasets"][dataset]
    url = config["ons"]["base"] + template.format(cdid=cdid.lower())
    payload = http_get_json(url)

    months: dict[str, float] = {}
    for entry in payload.get("months") or []:
        key = parse_ons_month(entry)
        value = parse_value(entry.get("value"))
        if key and value is not None:
            months[key] = value

    years: dict[str, float] = {}
    for entry in payload.get("years") or []:
        year_text = str(entry.get("year") or entry.get("date") or "").strip()
        value = parse_value(entry.get("value"))
        if year_text.isdigit() and value is not None:
            years[year_text] = value

    description = payload.get("description") or {}
    title = (description.get("title") or cdid).strip()
    next_release = parse_ons_next_release(description.get("nextRelease"))
    log(f"ONS {cdid.upper():6s} {len(months):4d} months  {title[:60]}")
    return {"title": title, "months": months, "years": years, "next_release": next_release}


# --------------------------------------------------------------------------
# Bank of England
# --------------------------------------------------------------------------

def fetch_iadb_daily(config: dict, series: str, start: str) -> list[tuple[date, float]]:
    """Fetch one daily series from the Bank's Interactive Database as (date, value)."""
    start_dt = datetime.strptime(start + "-01", "%Y-%m-%d")
    params = {
        "csv.x": "yes",
        "Datefrom": start_dt.strftime("%d/%b/%Y"),
        "Dateto": "now",
        "SeriesCodes": series,
        "CSVF": "TN",
        "UsingCodes": "Y",
        "VPD": "Y",
        "VFD": "N",
    }
    url = config["boe"]["url"] + "?" + urllib.parse.urlencode(params)
    text = http_get(url).decode("utf-8", errors="replace")

    daily: list[tuple[date, float]] = []
    for line in text.splitlines()[1:]:
        parts = line.strip().split(",")
        if len(parts) < 2:
            continue
        value = parse_value(parts[1])
        if value is None:
            continue
        try:
            when = datetime.strptime(parts[0].strip(), "%d %b %Y").date()
        except ValueError:
            continue
        daily.append((when, value))

    daily.sort(key=lambda row: row[0])
    if not daily:
        raise RuntimeError(f"Bank of England returned no usable {series} observations")
    log(f"BoE  {series:8s} {len(daily)} daily obs, latest {rounded(daily[-1][1])}%")
    return daily


def fetch_bank_rate(config: dict, start: str) -> tuple[dict[str, float], dict[str, float],
                                                       list[dict]]:
    """
    Fetch the daily official Bank Rate and reduce it to:
      - a month-end series {YYYY-MM: rate}
      - the daily series {YYYY-MM-DD: rate}, which the OIS bootstrap needs
      - the list of rate changes {date, from, to, change}
    """
    daily = fetch_iadb_daily(config, config["boe"]["series"], start)

    monthly: dict[str, float] = {}
    by_date: dict[str, float] = {}
    for when, value in daily:
        monthly[month_key(when.year, when.month)] = value  # last write wins = month end
        by_date[when.isoformat()] = value

    changes: list[dict] = []
    previous = daily[0][1]
    for when, value in daily[1:]:
        if abs(value - previous) > 1e-9:
            changes.append({
                "date": when.isoformat(),
                "month": month_key(when.year, when.month),
                "from": rounded(previous),
                "to": rounded(value),
                "change": rounded(value - previous),
            })
            previous = value

    log(f"BoE  Bank Rate: {len(changes)} rate changes since {start}")
    return monthly, by_date, changes


def fetch_sonia(config: dict, start: str) -> dict[str, float]:
    """SONIA, the overnight rate the GBP OIS curve is written on."""
    daily = fetch_iadb_daily(config, config["boe"]["sonia"], start)
    return {when.isoformat(): value for when, value in daily}


def fetch_ois_curves(config: dict, start: str) -> dict[str, list[tuple[float, float]]]:
    """
    The Bank's published OIS spot curve, short end, daily.

    The archive covers 2009 to the end of the last complete month; the latest
    bundle carries the current month on top of it.
    """
    spec = config["market"]["ois"]
    start_date = datetime.strptime(start + "-01", "%Y-%m-%d").date()
    curves: dict[str, list[tuple[float, float]]] = {}

    problems = market.parse_ois_archive(http_get(spec["archive"]), start_date, curves)
    log(f"BoE  OIS curve: {len(curves)} daily curves from the archive")

    problems += market.parse_ois_archive(http_get(spec["latest"]), start_date, curves)
    for problem in problems:
        log(f"BoE  OIS curve: skipped {problem}")
    if curves:
        log(f"BoE  OIS curve: {len(curves)} daily curves in total, "
            f"latest {max(curves)}")
    return curves


def fetch_mpc_votes(config: dict, start: str) -> list[dict]:
    """Every MPC Bank Rate decision, with the rate each member voted for."""
    spec = config["market"]["mpc_votes"]
    meetings = market.parse_mpc_votes(http_get(spec["url"]), spec["sheet"], start)
    log(f"BoE  MPC votes: {len(meetings)} meetings from {meetings[0]['date']} "
        f"to {meetings[-1]['date']}")
    return meetings


def fetch_upcoming_meetings(config: dict) -> list[str]:
    """
    Scheduled Bank Rate decisions that have not happened yet.

    mpcvoting.xlsx only ever lists meetings that already have a result, so it
    cannot say what "the next meeting" is on any day between the last decided
    meeting and the next one. This is the Bank's own published calendar.
    """
    url = config["market"]["upcoming_dates_url"]
    html = http_get(url).decode("utf-8", errors="replace")
    dates = market.parse_upcoming_meetings(html)
    log(f"BoE  upcoming MPC dates: {len(dates)} scheduled ({', '.join(dates[:3])}...)"
        if dates else "BoE  upcoming MPC dates: none found")
    return dates


def fetch_mpc_summaries(config: dict, decisions: list[dict], cache: dict) -> dict:
    """
    The Bank's own "Monetary Policy Summary" text for each meeting, scraped
    verbatim -- see fetcher/mpc_summary.py. `cache` is whatever the last run
    already had (keyed by month), so a normal run only fetches the meeting(s)
    that are new since then rather than re-scraping the Bank's site on every
    run. Meetings before ~August 2021 have no HTML summary on the Bank's site
    (PDF only) and are silently skipped, same as any page that fails to parse.
    """
    base = config["market"]["mps_url_base"]
    summaries = dict(cache)
    fetched = 0

    for decision in decisions:
        month = decision["month"]
        if month in summaries:
            continue
        url = mpc_summary.summary_url(base, decision["date"])
        try:
            page = http_get(url).decode("utf-8", errors="replace")
        except urllib.error.URLError as error:
            log(f"MPC summary fetch failed for {month} ({url}): {error}")
            continue
        parsed = mpc_summary.parse_summary_page(page)
        if parsed is None:
            log(f"MPC summary: no HTML text on the Bank's page for {month} ({url})")
            continue
        summaries[month] = {
            "date": decision["date"],
            "url": url,
            "heading": parsed["heading"],
            "paragraphs": parsed["paragraphs"],
        }
        fetched += 1

    if fetched:
        log(f"BoE  Monetary Policy Summary: fetched {fetched} new meeting(s), "
            f"{len(summaries)} in total")
    return summaries


def load_previous_mpc_summaries(target: str) -> dict:
    """Whatever the last run already scraped, so this run only fetches what's new."""
    if target in ("db", "both"):
        try:
            from backend import database
            with database.connect() as conn:
                database.init_schema()
                return database.load_meta_values(conn).get("mpc_summaries") or {}
        except Exception as error:  # noqa: BLE001 - a first run has no store yet
            log(f"could not read previous MPC summaries from Postgres ({error}); "
                f"starting fresh")
            return {}
    return (load_json(DATA_DIR / "meta.json", {}) or {}).get("mpc_summaries", {})


def fetch_mpc_news(config: dict, names: list[str], per_member: int = 5) -> dict:
    """
    Recent news for each sitting MPC member, via Google News RSS -- see
    fetcher/mpc_news.py. Unlike the MPC summaries, this is refetched from
    scratch every run rather than cached: the point is what's recent, so a
    stale cache would defeat it. One request per member, so this is cheap
    even at the fetcher's every-run cadence.
    """
    base = config["market"]["news_search_url"]
    by_member: dict[str, list[dict]] = {}

    for name in names:
        url = mpc_news.search_url(base, name)
        try:
            xml_bytes = http_get(url)
        except urllib.error.URLError as error:
            log(f"news fetch failed for {name} ({error})")
            continue
        try:
            by_member[name] = mpc_news.parse_news_feed(xml_bytes, limit=per_member)
        except ET.ParseError as error:
            log(f"news feed for {name} did not parse ({error})")

    total = sum(len(items) for items in by_member.values())
    log(f"MPC member news: {total} headlines across {len(by_member)} member(s)")
    return by_member


def extract_curve_series(curves: dict[str, list[tuple[float, float]]],
                         tenor_years: float) -> dict[str, float]:
    """One constant-maturity point (e.g. 3M, 2Y) read off every day's curve."""
    series: dict[str, float] = {}
    for when, curve in curves.items():
        rate = market.curve_rate(curve, tenor_years)
        if rate is not None:
            series[when] = rate
    return series


def monthly_last(daily: dict[str, float]) -> dict[str, float]:
    """Reduce a {ISO date: value} series to month-end, last write wins."""
    monthly: dict[str, float] = {}
    for when in sorted(daily):
        monthly[when[:7]] = daily[when]
    return monthly


# --------------------------------------------------------------------------
# derivations
# --------------------------------------------------------------------------

def yoy_from_index(index: dict[str, float], key: str) -> float | None:
    now, then = index.get(key), index.get(shift_month(key, -12))
    if now is None or then is None or then == 0:
        return None
    return (now / then - 1.0) * 100.0


def weight_for(series: dict, key: str, fallback: float) -> float:
    """CPI weights are published annually; use the current year, else carry back."""
    year = int(key[:4])
    years = series.get("years") or {}
    for candidate in range(year, year - 6, -1):
        if str(candidate) in years:
            return years[str(candidate)]
    return fallback


def derive_services_weight(headline: float | None, services: float | None,
                           goods: float | None, fallback: float) -> float:
    """
    Headline is a weighted average of goods and services, and the two weights
    sum to 1000. That identity pins down the implied services weight:

        headline = (w_s * services + w_g * goods) / 1000,  w_s + w_g = 1000
        =>  w_s = 1000 * (headline - goods) / (services - goods)

    When services and goods inflation are close the denominator is unstable,
    so fall back to the published-basket approximation in that case.
    """
    if headline is None or services is None or goods is None:
        return fallback
    spread = services - goods
    if abs(spread) < 0.5:
        return fallback
    weight = 1000.0 * (headline - goods) / spread
    if not 250.0 <= weight <= 750.0:
        return fallback
    return weight


def build_panel(config: dict, rates: dict, indices: dict, weights: dict,
                bank_rate: dict[str, float],
                expected_path: dict[str, dict] | None = None,
                ois_3m: dict[str, float] | None = None,
                ois_2y: dict[str, float] | None = None) -> list[dict]:
    start = config["start"]
    fallbacks = config["weight_fallbacks"]
    expected_path = expected_path or {}
    ois_3m = ois_3m or {}
    ois_2y = ois_2y or {}

    keys = sorted(set(rates["headline_cpi"]["months"]) | set(bank_rate))
    keys = [k for k in keys if k >= start]

    panel: list[dict] = []
    for key in keys:
        def rate(name: str) -> float | None:
            spec = config["rates"][name]
            series = rates[name]
            if spec["kind"] == "yoy_from_index":
                return yoy_from_index(series["months"], key)
            return series["months"].get(key)

        headline = rate("headline_cpi")
        services = rate("services_cpi")
        goods = rate("goods_cpi")
        policy = bank_rate.get(key)

        # Skip months with neither a CPI print nor a Bank Rate observation --
        # nothing to show. A month with Bank Rate/OIS data but no CPI yet (the
        # gap between the latest MPC meeting and the next CPI release) still
        # gets a row, with the CPI-derived fields left null, so the rates
        # chart isn't held back waiting on ONS.
        if headline is None and policy is None:
            continue

        w_services = derive_services_weight(headline, services, goods,
                                            fallbacks["services"])
        w_food = weight_for(weights["food"], key, fallbacks["food"])
        w_alcohol = weight_for(weights["alcohol_tobacco"], key,
                               fallbacks["alcohol_tobacco"])
        w_energy = weight_for(weights["energy"], key, fallbacks["energy"])
        w_core_goods = max(0.0, 1000.0 - w_services - w_food - w_alcohol - w_energy)

        components = {
            "services": (rate("services_cpi"), w_services),
            "core_goods": (rate("core_goods_cpi"), w_core_goods),
            "food": (rate("food_cpi"), w_food),
            "energy": (rate("energy_cpi"), w_energy),
            "alcohol_tobacco": (rate("alcohol_tobacco_cpi"), w_alcohol),
        }

        contributions: dict[str, float | None] = {}
        accounted = 0.0
        for name, (component_rate, component_weight) in components.items():
            if component_rate is None:
                contributions[name] = None
                continue
            contribution = component_weight / 1000.0 * component_rate
            contributions[name] = rounded(contribution)
            accounted += contribution

        row = {
            "date": key,
            "headline_cpi": rounded(headline),
            "core_cpi": rounded(rate("core_cpi")),
            "services_cpi": rounded(services),
            "goods_cpi": rounded(goods),
            "core_goods_cpi": rounded(rate("core_goods_cpi")),
            "food_cpi": rounded(rate("food_cpi")),
            "energy_cpi": rounded(rate("energy_cpi")),
            "alcohol_tobacco_cpi": rounded(rate("alcohol_tobacco_cpi")),
            "wage_growth": rounded(rate("wage_growth")),
            "gdp_growth": rounded(rate("gdp_growth")),
            "policy_rate": rounded(bank_rate.get(key)),
            # Market expectations, as at the last business day of the month.
            "expected_rate": rounded((expected_path.get(key) or {}).get("implied_rate")),
            "ois_m1": rounded((expected_path.get(key) or {}).get("ois_m1")),
            "ois_m2": rounded((expected_path.get(key) or {}).get("ois_m2")),
            "pricing_bp": (expected_path.get(key) or {}).get("pricing_bp"),
            # 3-month and 2-year SONIA OIS — read off the same curve, at fixed
            # calendar tenors rather than meeting dates. Context for the
            # meeting-dated curve above: the front end (3M) shows near-term
            # policy expectations broadly, and the 2Y shows where the market
            # expects the cycle to settle.
            "ois_3m": rounded(ois_3m.get(key)),
            "ois_2y": rounded(ois_2y.get(key)),
            "contributions": {
                **contributions,
                # Residual: rounding, unallocated basket items, and the
                # approximation in the weighted-average identity above.
                "other": rounded(headline - accounted) if headline is not None else None,
            },
            "weights": {
                "services": rounded(w_services, 1),
                "core_goods": rounded(w_core_goods, 1),
                "food": rounded(w_food, 1),
                "energy": rounded(w_energy, 1),
                "alcohol_tobacco": rounded(w_alcohol, 1),
            },
            "index": {
                name.replace("_index", ""): rounded(series["months"].get(key))
                for name, series in indices.items()
            },
        }

        row["headline_contribution"] = row["headline_cpi"]
        panel.append(row)

    # month-on-month changes and the real policy rate
    for position, row in enumerate(panel):
        previous = panel[position - 1] if position else None
        row["mom"] = {}
        for field in ("headline_cpi", "core_cpi", "services_cpi", "core_goods_cpi",
                      "food_cpi", "energy_cpi", "alcohol_tobacco_cpi",
                      "wage_growth", "gdp_growth", "policy_rate", "expected_rate",
                      "ois_3m", "ois_2y"):
            current, prior = row.get(field), (previous or {}).get(field)
            row["mom"][field] = (rounded(current - prior)
                                 if current is not None and prior is not None else None)

        if row["policy_rate"] is not None and row["headline_cpi"] is not None:
            row["real_rate"] = rounded(row["policy_rate"] - row["headline_cpi"])
        else:
            row["real_rate"] = None

        # How far the market expected the next meeting to move rates. Positive
        # means the market was priced above where Bank Rate actually sat.
        if row["expected_rate"] is not None and row["policy_rate"] is not None:
            row["expected_gap"] = rounded(row["expected_rate"] - row["policy_rate"])
        else:
            row["expected_gap"] = None

    log(f"panel: {len(panel)} months, {panel[0]['date']} .. {panel[-1]['date']}")
    return panel


# --------------------------------------------------------------------------
# diffing
# --------------------------------------------------------------------------

def diff_panels(old: list[dict], new: list[dict]) -> dict:
    """Compare against the last stored panel and describe what moved."""
    old_by_date = {row["date"]: row for row in old}
    tracked = ("headline_cpi", "core_cpi", "services_cpi", "core_goods_cpi",
               "food_cpi", "energy_cpi", "alcohol_tobacco_cpi",
               "wage_growth", "gdp_growth", "policy_rate", "expected_rate", "ois_3m", "ois_2y")

    added: list[str] = []
    revised: list[dict] = []

    for row in new:
        previous = old_by_date.get(row["date"])
        if previous is None:
            added.append(row["date"])
            continue
        for field in tracked:
            before, after = previous.get(field), row.get(field)
            if before != after and after is not None:
                revised.append({
                    "date": row["date"], "field": field,
                    "from": before, "to": after,
                })

    return {
        "added_months": added,
        "revised_values": revised,
        "has_changes": bool(added or revised),
    }


def flag_reaction_function(panel: list[dict], months_back: int = 6) -> dict | None:
    """
    Flag when the policy stance looks out of step with the recent inflation
    trend: rates held flat while core inflation moved materially, or a rate
    move in the opposite direction to the inflation trend.
    """
    window = [row for row in panel if row["policy_rate"] is not None][-months_back:]
    if len(window) < 3:
        return None

    first, last = window[0], window[-1]
    rate_move = last["policy_rate"] - first["policy_rate"]

    core_first, core_last = first.get("core_cpi"), last.get("core_cpi")
    if core_first is None or core_last is None:
        return None
    core_move = core_last - core_first

    if abs(rate_move) < 1e-9 and abs(core_move) >= 0.5:
        direction = "risen" if core_move > 0 else "fallen"
        return {
            "type": "hold_against_trend",
            "months": len(window),
            "core_move": rounded(core_move),
            "rate_move": 0.0,
            "detail": (f"Bank Rate held at {last['policy_rate']}% over "
                       f"{len(window)} months while core CPI has {direction} "
                       f"{abs(core_move):.1f}pp to {core_last}%."),
        }

    if rate_move * core_move < -1e-9 and abs(rate_move) >= 0.25:
        return {
            "type": "move_against_trend",
            "months": len(window),
            "core_move": rounded(core_move),
            "rate_move": rounded(rate_move),
            "detail": (f"Bank Rate moved {rate_move:+.2f}pp over {len(window)} "
                       f"months while core CPI moved {core_move:+.1f}pp — "
                       f"policy and the core trend are pointing in opposite "
                       f"directions."),
        }
    return None


# --------------------------------------------------------------------------
# Claude commentary
# --------------------------------------------------------------------------

COMMENTARY_SYSTEM = """You are a macro strategist writing the short internal \
note that accompanies a UK inflation and monetary policy dashboard. Your reader \
is a markets professional: assume they know what CPI, Bank Rate and the MPC are.

Write like a sell-side economist summarising a print, not like a press release. \
Be specific about numbers and about the split between headline, core and services \
inflation. Say what the data implies for the Bank's reaction function. Where the \
policy stance and the inflation trend look inconsistent, say so plainly.

Do not speculate beyond the data you are given, do not give investment advice, \
and do not invent figures that are not in the input."""

COMMENTARY_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {
            "type": "string",
            "description": "One-line summary, under 90 characters, no trailing period.",
        },
        "note": {
            "type": "string",
            "description": "Two to four sentences of institutional-style commentary.",
        },
        "stance": {
            "type": "string",
            "enum": ["restrictive", "neutral", "accommodative", "unclear"],
            "description": "How the current policy setting reads against the inflation data.",
        },
        "flag": {
            "type": "string",
            "description": (
                "Empty string if policy looks consistent with the inflation trend; "
                "otherwise one sentence naming the inconsistency."
            ),
        },
    },
    "required": ["headline", "note", "stance", "flag"],
    "additionalProperties": False,
}


def build_commentary_prompt(panel: list[dict], diff: dict, alert: dict | None) -> str:
    recent = panel[-13:]
    latest = panel[-1]

    lines = [
        "Latest UK data (percent, year-on-year unless stated):",
        json.dumps({
            "date": latest["date"],
            "headline_cpi": latest["headline_cpi"],
            "core_cpi": latest["core_cpi"],
            "services_cpi": latest["services_cpi"],
            "core_goods_cpi": latest["core_goods_cpi"],
            "energy_cpi": latest["energy_cpi"],
            "food_cpi": latest["food_cpi"],
            "wage_growth_3m_yoy": latest["wage_growth"],
            "gdp_growth_yoy": latest["gdp_growth"],
            "bank_rate": latest["policy_rate"],
            "real_policy_rate": latest["real_rate"],
            "synthetic_mpc_ois_implied_rate_next_meeting": latest["expected_rate"],
            "synthetic_mpc_ois_pricing_bp": latest.get("pricing_bp"),
            "ois_implied_less_bank_rate_pp": latest["expected_gap"],
            "sonia_ois_3m": latest["ois_3m"],
            "sonia_ois_2y": latest["ois_2y"],
            "month_on_month_changes_pp": latest["mom"],
            "contributions_to_headline_pp": latest["contributions"],
        }, indent=2),
        "",
        "Previous 12 months (date, headline, core, services, bank rate):",
    ]
    for row in recent[:-1]:
        lines.append(f"  {row['date']}  headline {row['headline_cpi']}  "
                     f"core {row['core_cpi']}  services {row['services_cpi']}  "
                     f"bank rate {row['policy_rate']}")

    lines.append("")
    if diff["added_months"]:
        lines.append(f"New months in this release: {', '.join(diff['added_months'])}")
    notable = [r for r in diff["revised_values"]
               if r["from"] is not None and r["to"] is not None
               and abs(r["to"] - r["from"]) >= NOTABLE_MOVE_PP]
    if notable:
        lines.append("Revisions to previously published values:")
        for revision in notable[:10]:
            lines.append(f"  {revision['date']} {revision['field']}: "
                         f"{revision['from']} -> {revision['to']}")

    if alert:
        lines.append("")
        lines.append(f"Reaction-function flag raised by the pipeline: {alert['detail']}")

    lines.append("")
    lines.append("Write the note for this release.")
    return "\n".join(lines)


def generate_commentary(prompt: str) -> dict | None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log("ANTHROPIC_API_KEY not set - skipping commentary")
        return None

    try:
        import anthropic
    except ImportError:
        log("anthropic package not installed - skipping commentary "
            "(pip install -r fetcher/requirements.txt)")
        return None

    model = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")
    client = anthropic.Anthropic(api_key=api_key)

    request = {
        "model": model,
        "max_tokens": 8000,
        "system": COMMENTARY_SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
        "thinking": {"type": "adaptive"},
        "output_config": {
            "effort": "medium",
            "format": {"type": "json_schema", "schema": COMMENTARY_SCHEMA},
        },
    }

    # Claude Opus 5 can decline a request outright; the server-side fallback
    # re-runs it on Anthropic's recommended fallback model in the same call.
    attempts = [
        dict(request, betas=["server-side-fallback-2026-07-01"], fallbacks="default"),
        request,
    ]

    for index, attempt in enumerate(attempts):
        try:
            response = client.beta.messages.create(**attempt)
        except Exception as exc:  # noqa: BLE001 - never fail the pipeline on this
            log(f"commentary attempt {index + 1} failed: {exc}")
            continue

        if response.stop_reason == "refusal":
            log("commentary refused by the model - skipping")
            return None

        text = next((block.text for block in response.content
                     if block.type == "text"), None)
        if not text:
            log("commentary returned no text block - skipping")
            return None

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            log("commentary was not valid JSON - skipping")
            return None

        parsed["model"] = getattr(response, "model", model)
        return parsed

    return None


# --------------------------------------------------------------------------
# storage
# --------------------------------------------------------------------------

def resolve_target(requested: str) -> str:
    """
    Decide where this run writes.

    'auto' keeps both deployment shapes working from one entry point: Postgres
    when DATABASE_URL is present (the Render cron job), flat JSON files when it
    is not (local runs and the GitHub Actions workflow).
    """
    if requested != "auto":
        return requested
    try:
        from backend import database
    except ImportError:
        return "json"
    return "db" if database.is_configured() else "json"


def load_previous_panel(target: str) -> list[dict]:
    """Whatever the last run stored, for diffing against."""
    if target in ("db", "both"):
        try:
            from backend import database
            with database.connect() as conn:
                database.init_schema()
                return database.load_observations(conn)
        except Exception as error:  # noqa: BLE001 - a first run has no store yet
            log(f"could not read the previous panel from Postgres ({error}); "
                f"treating this as a first run")
            return []
    return (load_json(DATA_DIR / "timeseries.json", {}) or {}).get("observations", [])


def write_to_database(panel: list[dict], meta_payload: dict, events: list[dict],
                      rate_changes: list[dict], diff: dict) -> None:
    from backend import database

    database.init_schema()
    with database.connect() as conn:
        database.upsert_observations(conn, panel)
        database.replace_rate_changes(conn, rate_changes)
        database.replace_events(conn, events)
        for key in database.META_KEYS:
            if key in meta_payload:
                database.set_meta(conn, key, meta_payload[key])
        database.record_run(
            conn,
            status="ok",
            months_added=len(diff["added_months"]),
            values_revised=len(diff["revised_values"]),
            latest_month=panel[-1]["date"],
        )
        conn.commit()
    log(f"Postgres updated: {len(panel)} observations, "
        f"{len(rate_changes)} rate changes, {len(events)} events")


def write_commentary(target: str, entry: dict | None, now: str) -> None:
    """Append a note to whichever store is active, keeping the file valid either way."""
    if target in ("db", "both") and entry is not None:
        from backend import database
        with database.connect() as conn:
            database.append_commentary(conn, entry)
            conn.commit()

    if target in ("json", "both"):
        commentary_log = load_json(DATA_DIR / "commentary.json", {"entries": []})
        commentary_log.setdefault("entries", [])
        if entry is not None:
            commentary_log["entries"] = ([entry] + commentary_log["entries"])[:60]
        commentary_log["generated_at"] = now
        write_json(DATA_DIR / "commentary.json", commentary_log)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch UK CPI and Bank Rate data.")
    parser.add_argument("--no-llm", action="store_true",
                        help="skip the Claude commentary step")
    parser.add_argument("--force", action="store_true",
                        help="write output and generate commentary even if nothing changed")
    parser.add_argument("--target", choices=("auto", "db", "json", "both"), default="auto",
                        help="where to write: Postgres, flat JSON files, or both. "
                             "'auto' (the default) picks Postgres when DATABASE_URL is set.")
    args = parser.parse_args()

    target = resolve_target(args.target)
    log(f"storage target: {target}")

    config = load_json(CONFIG_DIR / "series.json")
    events = load_json(CONFIG_DIR / "events.json", [])
    if config is None:
        log("config/series.json is missing")
        return 1

    log("fetching ONS series")
    rates = {name: fetch_ons_series(config, spec["cdid"], spec["dataset"])
             for name, spec in config["rates"].items()}
    indices = {name: fetch_ons_series(config, spec["cdid"], spec["dataset"])
               for name, spec in config["indices"].items()}

    weights: dict[str, dict] = {}
    for name, spec in config["weights"].items():
        combined: dict[str, float] = {}
        for cdid in spec["cdids"]:
            series = fetch_ons_series(config, cdid, spec["dataset"])
            for year, value in series["years"].items():
                combined[year] = combined.get(year, 0.0) + value
        weights[name] = {"title": spec["title"], "months": {}, "years": combined}

    log("fetching Bank of England Bank Rate")
    bank_rate, bank_rate_daily, rate_changes = fetch_bank_rate(config, config["start"])

    log("fetching MPC voting history and the OIS curve")
    meetings = fetch_mpc_votes(config, config["start"])
    decisions = market.summarise_votes(meetings)
    upcoming = fetch_upcoming_meetings(config)
    # Decided meetings plus scheduled-but-undecided ones: the full boundary
    # set the bootstrap needs to know "the next meeting" on every date,
    # including the days between the latest decision and the next meeting.
    all_meeting_dates = sorted(set(m["date"] for m in meetings) | set(upcoming))

    expected_path: dict[str, dict] = {}
    monthly_path: dict[str, dict] = {}
    ois_3m_monthly: dict[str, float] = {}
    ois_2y_monthly: dict[str, float] = {}
    latest_curve: list[dict] = []
    latest_spread_bp: float | None = None
    curves: dict[str, list[tuple[float, float]]] = {}
    try:
        sonia = fetch_sonia(config, config["start"])
        curves = fetch_ois_curves(config, config["start"])
        override = market.load_ois_override(
            ROOT / config["market"]["override_csv"].replace("/", os.sep))
        if override:
            log(f"OIS override: {len(override)} dates read from "
                f"{config['market']['override_csv']}")

        spread_series = market.holt_spread_series(
            sorted(set(bank_rate_daily) | set(sonia)), bank_rate_daily, sonia,
        )
        log(f"SONIA/Bank Rate spread: Holt's estimate, {len(spread_series)} daily "
            f"points, latest {spread_series[max(spread_series)]:.2f}bp"
            if spread_series else "SONIA/Bank Rate spread: no overlapping data")

        expected_path = market.bootstrap_expected_path(
            all_meeting_dates, sonia, bank_rate_daily, curves, spread_series, override,
        )
        monthly_path = market.monthly_expected_path(expected_path)
        log(f"synthetic MPC OIS: {len(expected_path)} daily points, "
            f"{len(monthly_path)} month-ends")

        ois_3m_monthly = monthly_last(extract_curve_series(curves, 0.25))
        ois_2y_monthly = monthly_last(extract_curve_series(curves, 2.0))
        log(f"OIS curve points: {len(ois_3m_monthly)} months of 3M, "
            f"{len(ois_2y_monthly)} months of 2Y")

        if curves and spread_series:
            latest_curve_date = max(curves)
            # The Holt's series only has entries where both Bank Rate and
            # SONIA are available, which can trail the OIS curve by a day or
            # two (SONIA publishes T+1) -- fall back to the latest spread
            # estimate available rather than skip the snapshot entirely.
            latest_spread_bp = spread_series.get(latest_curve_date)
            if latest_spread_bp is None:
                latest_spread_bp = spread_series[max(spread_series)]
            latest_curve = market.synthetic_mpc_curve(
                latest_curve_date, all_meeting_dates, curves, sonia, bank_rate_daily,
                latest_spread_bp, override, n=config["market"]["synthetic_curve_meetings"],
            )
            log(f"synthetic curve snapshot as of {latest_curve_date}: "
                f"{len(latest_curve)} meeting(s), spread {latest_spread_bp:.2f}bp")
    except Exception as error:  # noqa: BLE001 - CPI must still publish without it
        log(f"could not build the synthetic MPC OIS curve ({error}); "
            f"continuing without it")

    market.attach_market_pricing(decisions, expected_path)

    panel = build_panel(config, rates, indices, weights, bank_rate, monthly_path,
                        ois_3m_monthly, ois_2y_monthly)
    if not panel:
        log("no observations built - aborting without writing")
        return 1

    previous_panel = load_previous_panel(target)
    diff = diff_panels(previous_panel, panel)
    alert = flag_reaction_function(panel)

    log(f"diff: {len(diff['added_months'])} new month(s), "
        f"{len(diff['revised_values'])} revised value(s)")

    if not diff["has_changes"] and not args.force:
        log("no changes since last run - nothing to write")
        return 0

    # panel[-1] is the newest row with *any* data, which can now be a month
    # with Bank Rate/OIS data but no CPI print yet (see build_panel). Every
    # "latest" summary below -- stat cards, commentary, the reaction-function
    # flag -- is fundamentally about the latest inflation print, so anchor it
    # to the latest row that actually has one rather than a rates-only stub.
    latest = next((row for row in reversed(panel) if row["headline_cpi"] is not None), panel[-1])
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    windowed_decisions = [d for d in decisions if d["month"] >= config["start"]]
    log("fetching Bank of England Monetary Policy Summaries")
    mpc_summaries = fetch_mpc_summaries(
        config, windowed_decisions, load_previous_mpc_summaries(target))

    log("fetching MPC member news")
    mpc_news_data = fetch_mpc_news(config, mpc_news.member_names(windowed_decisions))

    # Next scheduled release for each of the four things the dashboard is
    # built around. `upcoming` is the Bank's published calendar for the
    # confirmed/provisional year(s) -- it does not stop at "today", it's
    # every meeting date in those years, so the next undecided one is
    # whichever of those falls after the last meeting actually decided. The
    # ONS dates ride along on the series fetches already made above, at no
    # extra HTTP cost.
    next_boe_meeting = next(
        (d for d in sorted(upcoming) if d > windowed_decisions[-1]["date"]), None,
    ) if windowed_decisions else None
    upcoming_releases = [
        {"id": "cpi", "label": "CPI inflation", "source": "ONS",
         "date": rates["headline_cpi"].get("next_release")},
        {"id": "boe_rate", "label": "BoE policy decision", "source": "Bank of England",
         "date": next_boe_meeting},
        {"id": "gdp", "label": "GDP growth", "source": "ONS",
         "date": rates["gdp_growth"].get("next_release")},
        {"id": "wages", "label": "Wage growth", "source": "ONS",
         "date": rates["wage_growth"].get("next_release")},
    ]
    upcoming_releases = sorted(
        (entry for entry in upcoming_releases if entry["date"]),
        key=lambda entry: entry["date"],
    )

    meta_payload = {
        "generated_at": now,
        "start": config["start"],
        "latest_month": latest["date"],
        "latest": {
            "headline_cpi": latest["headline_cpi"],
            "core_cpi": latest["core_cpi"],
            "services_cpi": latest["services_cpi"],
            "policy_rate": latest["policy_rate"],
            "real_rate": latest["real_rate"],
            "wage_growth": latest["wage_growth"],
            "gdp_growth": latest["gdp_growth"],
            "expected_rate": latest["expected_rate"],
            "ois_3m": latest["ois_3m"],
            "ois_2y": latest["ois_2y"],
        },
        "mom": latest["mom"],
        "rate_changes": rate_changes,
        "mpc_decisions": windowed_decisions,
        "mpc_summaries": mpc_summaries,
        "mpc_news": mpc_news_data,
        "upcoming_releases": upcoming_releases,
        "synthetic_mpc_curve": {
            "as_of": max(curves) if curves else None,
            "spread_bps": rounded(latest_spread_bp, 2),
            "spread_method": "holt_linear_trend",
            "meetings": latest_curve,
        },
        "events": events,
        "reaction_function_flag": alert,
        "diff": diff,
        "sources": [
            {
                "name": "Office for National Statistics",
                "dataset": "MM23 Consumer price inflation time series",
                "url": "https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/consumerpriceindices",
                "series": sorted({spec["cdid"] for spec in config["rates"].values()
                                  if spec["dataset"] == "mm23"}
                                 | {spec["cdid"] for spec in config["indices"].values()}),
            },
            {
                "name": "Office for National Statistics",
                "dataset": "GDP monthly estimate, UK (MGDP)",
                "url": "https://www.ons.gov.uk/economy/grossdomesticproductgdp/datasets/gdpmonthlyestimateuktimeseriesdataset",
                "series": [spec["cdid"] for spec in config["rates"].values()
                          if spec["dataset"] == "mgdp"],
            },
            {
                "name": "Office for National Statistics",
                "dataset": "Labour market statistics (average weekly earnings)",
                "url": "https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/earningsandworkinghours",
                "series": [spec["cdid"] for spec in config["rates"].values()
                          if spec["dataset"] == "lms"],
            },
            {
                "name": "Bank of England",
                "dataset": "Interactive Statistical Database",
                "url": "https://www.bankofengland.co.uk/boeapps/database/",
                "series": [config["boe"]["series"], config["boe"]["sonia"]],
            },
            {
                "name": "Bank of England",
                "dataset": "MPC voting history, Bank Rate",
                "url": config["market"]["mpc_votes"]["url"],
                "series": ["mpcvoting.xlsx"],
            },
            {
                "name": "Bank of England",
                "dataset": "UK OIS spot curve, short end",
                "url": "https://www.bankofengland.co.uk/statistics/yield-curves",
                "series": ["oisddata.zip", "latest-yield-curve-data.zip"],
            },
            {
                "name": "Bank of England",
                "dataset": "Upcoming MPC dates",
                "url": config["market"]["upcoming_dates_url"],
                "series": ["upcoming-mpc-dates"],
            },
        ],
        "methodology": {
            "contributions": (
                "Contribution of each component to the headline annual rate is its "
                "CPI basket weight divided by 1000, multiplied by its annual rate. "
                "The 'other' component is the residual between headline CPI and the "
                "sum of the five modelled components."
            ),
            "services_weight": (
                "The services weight is implied each month from the identity "
                "headline = (w_s * services + w_g * goods) / 1000 with w_s + w_g = 1000, "
                "falling back to the published basket approximation when goods and "
                "services inflation are within 0.5pp of each other."
            ),
            "core": (
                "Core CPI is the ONS 'excluding energy, food, alcohol and tobacco' "
                "index (DKC6), converted to an annual rate. Core goods is the "
                "non-energy industrial goods index (DK9J); energy is DK9T."
            ),
            "policy_rate": (
                "Bank Rate is the Bank of England's daily official rate (IUDBEDR), "
                "taken at the last observation of each month so the series is a step "
                "function reflecting actual MPC decisions."
            ),
            "expected_rate": (
                "'Synthetic MPC OIS Curve': market-implied Bank Rate adjustment for "
                "the upcoming MPC meeting, derived from SONIA OIS forward pricing "
                "between consecutive MPC dates. Two synthetic OIS legs are read off "
                "the Bank of England's published OIS spot curve at the next two "
                "meeting-date tenors, T1 and T2 — both from the curve; no SONIA "
                "fixing is substituted for either leg. Curve reads use log-linear "
                "discount-factor interpolation (DF(T) = exp(-rT), continuously "
                "compounded per the Bank's own stated convention, interpolated as "
                "DF(Tx) = DF(Ta)^(1-w) * DF(Tb)^w), not linear interpolation of the "
                "rates themselves, because that is the arbitrage-consistent "
                "convention (a piecewise-flat forward between grid nodes) and this "
                "segment of the curve is exactly where MPC-driven curvature is "
                "sharpest. The forward is then bootstrapped in discount-factor "
                "space, F = -ln(DF(T2)/DF(T1)) / (T2 - T1) — the average SONIA the "
                "market expects to prevail between meeting 1 and meeting 2, i.e. the "
                "level it expects meeting 1 to set. A spread estimate converts that "
                "SONIA-space forward onto the Bank Rate scale — Holt's linear trend "
                "smoothing of the daily SONIA-to-Bank-Rate gap (fetcher/market.py: "
                "holt_spread_series), walk-forward validated against 3 years of "
                "out-of-sample data rather than a fixed constant or a flat trailing "
                "average, both of which lag the multi-year regime shifts the spread "
                "has actually shown since 2015. 'Market pricing' in basis points is "
                "(implied Bank Rate - Bank Rate on the pricing date); the quoted "
                "probability of a 25bp move quantises that onto whole 25bp steps "
                "(e.g. 12.5bp priced = 50% chance of a 25bp move), the standard "
                "first-order desk convention, not a model of 50bp surprises. The "
                "Bank's curve is a smoothing fit across all tenors and so blurs the "
                "step the market prices at each meeting date somewhat; meeting-dated "
                "OIS quotes (Refinitiv GBPMPCOISM1/M2) price that step directly and "
                "can be supplied instead via data/ois_meetings.csv. Full derivation: "
                "docs/synthetic-mpc-ois-methodology.md."
            ),
            "gdp_growth": (
                "Monthly GDP growth: the ONS's monthly GDP estimate (measured as "
                "output-side Gross Value Added, chained volume, seasonally "
                "adjusted — CDID ECY2, dataset MGDP) converted to an annual "
                "(year-on-year) rate via the same yoy_from_index identity used for "
                "core CPI, for consistency with every other rate series on this "
                "dashboard."
            ),
            "ois_3m": (
                "3-month SONIA OIS: the Bank's published OIS spot curve read at the "
                "fixed 0.25-year tenor (discount-factor interpolated, same as the "
                "synthetic MPC curve) rather than at a meeting date."
            ),
            "ois_2y": (
                "2-year SONIA OIS: the Bank's published OIS spot curve read at the "
                "fixed 2-year tenor — a read on where the market expects the cycle "
                "to have settled, beyond the next few meetings."
            ),
            "mpc_votes": (
                "Vote splits come from the Bank of England's published MPC voting "
                "history. A member is counted as hawkish at a meeting if the Bank "
                "Rate they voted for was above the rate the Committee settled on, "
                "and dovish if it was below."
            ),
        },
    }

    if target in ("db", "both"):
        write_to_database(panel, meta_payload, events, rate_changes, diff)

    if target in ("json", "both"):
        write_json(DATA_DIR / "timeseries.json", {
            "generated_at": now,
            "start": config["start"],
            "observations": panel,
        })
        # meta.json carries everything except the panel itself.
        write_json(DATA_DIR / "meta.json",
                   {k: v for k, v in meta_payload.items() if k != "start"})

    if args.no_llm:
        log("--no-llm passed - skipping commentary")
        write_commentary(target, None, now)
        return 0

    prompt = build_commentary_prompt(panel, diff, alert)
    note = generate_commentary(prompt)

    if note:
        entry = {
            "generated_at": now,
            "observation_month": latest["date"],
            "headline": note.get("headline"),
            "note": note.get("note"),
            "stance": note.get("stance"),
            "flag": note.get("flag") or None,
            "model": note.get("model"),
            "context": {
                "headline_cpi": latest["headline_cpi"],
                "core_cpi": latest["core_cpi"],
                "services_cpi": latest["services_cpi"],
                "policy_rate": latest["policy_rate"],
                "new_months": diff["added_months"],
            },
        }
        write_commentary(target, entry, now)
        log(f"commentary written: {entry['headline']}")
    else:
        write_commentary(target, None, now)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.URLError as error:
        log(f"network error: {error}")
        sys.exit(1)
