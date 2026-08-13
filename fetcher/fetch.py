#!/usr/bin/env python3
"""
UK inflation & monetary policy fetcher.

Pulls CPI series from the ONS and Bank Rate from the Bank of England's
Interactive Database, derives the CPI decomposition used by the dashboard,
diffs the result against what was last stored, and (optionally) asks Claude
to write a short plain-English note about what changed.

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
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"

# Run as `python fetcher/fetch.py`, sys.path[0] is fetcher/ — put the repo root
# on the path so the shared database layer in backend/ is importable.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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


def fetch_ons_series(config: dict, cdid: str, dataset: str) -> dict:
    """Return {'title', 'months': {YYYY-MM: float}, 'years': {YYYY: float}}."""
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

    title = ((payload.get("description") or {}).get("title") or cdid).strip()
    log(f"ONS {cdid.upper():6s} {len(months):4d} months  {title[:60]}")
    return {"title": title, "months": months, "years": years}


# --------------------------------------------------------------------------
# Bank of England
# --------------------------------------------------------------------------

def fetch_bank_rate(config: dict, start: str) -> tuple[dict[str, float], list[dict]]:
    """
    Fetch the daily official Bank Rate and reduce it to:
      - a month-end series {YYYY-MM: rate}
      - the list of rate changes {date, from, to, change}
    """
    boe = config["boe"]
    start_dt = datetime.strptime(start + "-01", "%Y-%m-%d")
    params = {
        "csv.x": "yes",
        "Datefrom": start_dt.strftime("%d/%b/%Y"),
        "Dateto": "now",
        "SeriesCodes": boe["series"],
        "CSVF": "TN",
        "UsingCodes": "Y",
        "VPD": "Y",
        "VFD": "N",
    }
    url = boe["url"] + "?" + urllib.parse.urlencode(params)
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
        raise RuntimeError("Bank of England returned no usable Bank Rate observations")

    monthly: dict[str, float] = {}
    for when, value in daily:
        monthly[month_key(when.year, when.month)] = value  # last write wins = month end

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

    log(f"BoE  {boe['series']} {len(daily)} daily obs, {len(changes)} rate changes, "
        f"latest {rounded(daily[-1][1])}%")
    return monthly, changes


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
                bank_rate: dict[str, float]) -> list[dict]:
    start = config["start"]
    fallbacks = config["weight_fallbacks"]

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

        # Skip months with no CPI reading at all (e.g. a partial current month).
        if headline is None:
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
            "policy_rate": rounded(bank_rate.get(key)),
            "contributions": {
                **contributions,
                # Residual: rounding, unallocated basket items, and the
                # approximation in the weighted-average identity above.
                "other": rounded(headline - accounted),
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
                      "wage_growth", "policy_rate"):
            current, prior = row.get(field), (previous or {}).get(field)
            row["mom"][field] = (rounded(current - prior)
                                 if current is not None and prior is not None else None)

        if row["policy_rate"] is not None and row["headline_cpi"] is not None:
            row["real_rate"] = rounded(row["policy_rate"] - row["headline_cpi"])
        else:
            row["real_rate"] = None

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
               "wage_growth", "policy_rate")

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
            "bank_rate": latest["policy_rate"],
            "real_policy_rate": latest["real_rate"],
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
    bank_rate, rate_changes = fetch_bank_rate(config, config["start"])

    panel = build_panel(config, rates, indices, weights, bank_rate)
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

    latest = panel[-1]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

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
        },
        "mom": latest["mom"],
        "rate_changes": rate_changes,
        "events": events,
        "reaction_function_flag": alert,
        "diff": diff,
        "sources": [
            {
                "name": "Office for National Statistics",
                "dataset": "MM23 Consumer price inflation time series",
                "url": "https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/consumerpriceindices",
                "series": sorted({spec["cdid"] for spec in config["rates"].values()}
                                 | {spec["cdid"] for spec in config["indices"].values()}),
            },
            {
                "name": "Bank of England",
                "dataset": "Interactive Statistical Database",
                "url": "https://www.bankofengland.co.uk/boeapps/database/",
                "series": [config["boe"]["series"]],
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
