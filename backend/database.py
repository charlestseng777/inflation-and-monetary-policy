"""
Postgres access for the dashboard.

Shared by the API (reads) and the scheduled fetcher (writes). The read helpers
rebuild exactly the JSON payloads the frontend already consumes, so moving from
flat files to a database required no change to any component.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

OBSERVATION_COLUMNS = (
    "headline_cpi", "core_cpi", "services_cpi", "goods_cpi", "core_goods_cpi",
    "food_cpi", "energy_cpi", "alcohol_tobacco_cpi", "wage_growth",
    "policy_rate", "real_rate",
)

# meta.json keys that live in the key/value table.
META_KEYS = (
    "generated_at", "start", "latest_month", "latest", "mom",
    "reaction_function_flag", "diff", "sources", "methodology",
)


class DatabaseNotConfigured(RuntimeError):
    """Raised when DATABASE_URL is absent but a database operation was asked for."""


def database_url() -> str | None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        return None
    # Render (and Heroku-style providers) hand out `postgres://`, which some
    # drivers reject. psycopg is happy either way, but normalise for clarity.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def is_configured() -> bool:
    return database_url() is not None


@contextmanager
def connect():
    url = database_url()
    if not url:
        raise DatabaseNotConfigured(
            "DATABASE_URL is not set. Set it to a Postgres connection string, "
            "or run the fetcher with --target json to write flat files instead."
        )
    with psycopg.connect(url, row_factory=dict_row, connect_timeout=15) as conn:
        yield conn


def init_schema() -> None:
    """Create tables if they do not exist. Safe to call on every start-up."""
    statements = SCHEMA_PATH.read_text(encoding="utf-8")
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(statements)
        conn.commit()


# ---------------------------------------------------------------------------
# conversion helpers
# ---------------------------------------------------------------------------

def _plain(value: Any) -> Any:
    """Postgres NUMERIC comes back as Decimal; JSON should carry plain floats."""
    if isinstance(value, Decimal):
        return float(value)
    return value


def _row_to_observation(row: dict) -> dict:
    observation = {"date": row["month"]}
    for column in OBSERVATION_COLUMNS:
        observation[column] = _plain(row.get(column))
    observation["contributions"] = row.get("contributions") or {}
    observation["weights"] = row.get("weights") or {}
    observation["index"] = row.get("index_levels") or {}
    observation["mom"] = row.get("mom") or {}
    # Retained for payload fidelity with the original flat-file version.
    observation["headline_contribution"] = observation["headline_cpi"]
    return observation


# ---------------------------------------------------------------------------
# writes
# ---------------------------------------------------------------------------

def upsert_observations(conn, observations: Iterable[dict]) -> int:
    rows = []
    for observation in observations:
        rows.append((
            observation["date"],
            *[observation.get(column) for column in OBSERVATION_COLUMNS],
            Jsonb(observation.get("contributions") or {}),
            Jsonb(observation.get("weights") or {}),
            Jsonb(observation.get("index") or {}),
            Jsonb(observation.get("mom") or {}),
        ))

    assignments = ", ".join(f"{column} = EXCLUDED.{column}" for column in OBSERVATION_COLUMNS)
    statement = f"""
        INSERT INTO observations (
            month, {", ".join(OBSERVATION_COLUMNS)},
            contributions, weights, index_levels, mom
        )
        VALUES (%s, {", ".join(["%s"] * len(OBSERVATION_COLUMNS))}, %s, %s, %s, %s)
        ON CONFLICT (month) DO UPDATE SET
            {assignments},
            contributions = EXCLUDED.contributions,
            weights       = EXCLUDED.weights,
            index_levels  = EXCLUDED.index_levels,
            mom           = EXCLUDED.mom,
            updated_at    = now()
    """
    with conn.cursor() as cur:
        cur.executemany(statement, rows)
    return len(rows)


def replace_rate_changes(conn, changes: Iterable[dict]) -> int:
    rows = [
        (change["date"], change["month"], change["from"], change["to"], change["change"])
        for change in changes
    ]
    with conn.cursor() as cur:
        cur.execute("TRUNCATE rate_changes")
        cur.executemany(
            "INSERT INTO rate_changes (change_date, month, rate_from, rate_to, change) "
            "VALUES (%s, %s, %s, %s, %s)",
            rows,
        )
    return len(rows)


def replace_events(conn, events: Iterable[dict]) -> int:
    rows = [
        (
            event["id"], event["date"], event["label"], event.get("category"),
            event.get("description"), event.get("spanEnd"), event.get("spanLabel"),
            order,
        )
        for order, event in enumerate(events)
    ]
    with conn.cursor() as cur:
        cur.execute("TRUNCATE events")
        cur.executemany(
            "INSERT INTO events (id, month, label, category, description, "
            "span_end, span_label, sort_order) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            rows,
        )
    return len(rows)


def set_meta(conn, key: str, value: Any) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meta (key, value) VALUES (%s, %s) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
            (key, Jsonb(value)),
        )


def append_commentary(conn, entry: dict, keep: int = 60) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO commentary (generated_at, observation_month, headline, "
            "note, stance, flag, model, context) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                entry["generated_at"], entry["observation_month"], entry.get("headline"),
                entry.get("note"), entry.get("stance"), entry.get("flag"),
                entry.get("model"), Jsonb(entry.get("context") or {}),
            ),
        )
        # Keep the log bounded, matching the flat-file behaviour.
        cur.execute(
            "DELETE FROM commentary WHERE id NOT IN "
            "(SELECT id FROM commentary ORDER BY generated_at DESC, id DESC LIMIT %s)",
            (keep,),
        )


def record_run(conn, status: str, months_added: int, values_revised: int,
               latest_month: str | None, detail: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO fetch_runs (finished_at, status, months_added, "
            "values_revised, latest_month, detail) VALUES (now(), %s, %s, %s, %s, %s)",
            (status, months_added, values_revised, latest_month, detail),
        )


# ---------------------------------------------------------------------------
# reads
# ---------------------------------------------------------------------------

def observation_count(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM observations")
        return cur.fetchone()["n"]


def load_observations(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM observations ORDER BY month ASC")
        return [_row_to_observation(row) for row in cur.fetchall()]


def load_meta_values(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT key, value FROM meta")
        return {row["key"]: row["value"] for row in cur.fetchall()}


def load_rate_changes(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM rate_changes ORDER BY change_date ASC")
        return [
            {
                "date": row["change_date"].isoformat(),
                "month": row["month"],
                "from": _plain(row["rate_from"]),
                "to": _plain(row["rate_to"]),
                "change": _plain(row["change"]),
            }
            for row in cur.fetchall()
        ]


def load_events(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM events ORDER BY sort_order ASC, month ASC")
        events = []
        for row in cur.fetchall():
            event = {
                "id": row["id"],
                "date": row["month"],
                "label": row["label"],
                "category": row["category"],
                "description": row["description"],
            }
            # Only events that define a span carry the span keys at all. Adding
            # them as nulls everywhere would still render correctly, but the
            # payload would no longer be identical to the flat-file version.
            if row["span_label"] is not None:
                event["spanEnd"] = row["span_end"]
                event["spanLabel"] = row["span_label"]
            events.append(event)
        return events


def load_commentary(conn, limit: int = 60) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM commentary ORDER BY generated_at DESC, id DESC LIMIT %s",
            (limit,),
        )
        return [
            {
                "generated_at": row["generated_at"].isoformat(),
                "observation_month": row["observation_month"],
                "headline": row["headline"],
                "note": row["note"],
                "stance": row["stance"],
                "flag": row["flag"],
                "model": row["model"],
                "context": row["context"] or {},
            }
            for row in cur.fetchall()
        ]


# ---------------------------------------------------------------------------
# payload assembly — the exact shapes the frontend expects
# ---------------------------------------------------------------------------

def build_timeseries_payload(conn) -> dict:
    meta = load_meta_values(conn)
    return {
        "generated_at": meta.get("generated_at"),
        "start": meta.get("start"),
        "observations": load_observations(conn),
    }


def build_meta_payload(conn) -> dict:
    meta = load_meta_values(conn)
    return {
        "generated_at": meta.get("generated_at"),
        "latest_month": meta.get("latest_month"),
        "latest": meta.get("latest") or {},
        "mom": meta.get("mom") or {},
        "rate_changes": load_rate_changes(conn),
        "events": load_events(conn),
        "reaction_function_flag": meta.get("reaction_function_flag"),
        "diff": meta.get("diff") or {},
        "sources": meta.get("sources") or [],
        "methodology": meta.get("methodology") or {},
    }


def build_commentary_payload(conn) -> dict:
    meta = load_meta_values(conn)
    return {
        "generated_at": meta.get("generated_at"),
        "entries": load_commentary(conn),
    }


# ---------------------------------------------------------------------------
# first-run seeding
# ---------------------------------------------------------------------------

def seed_from_files(conn, data_dir: Path, config_dir: Path) -> bool:
    """
    Load the JSON committed in the repo into an empty database, so a fresh
    deploy serves real data before the first scheduled run. No-op if the
    observations table already has rows.
    """
    if observation_count(conn) > 0:
        return False

    timeseries_path = data_dir / "timeseries.json"
    if not timeseries_path.exists():
        return False

    timeseries = json.loads(timeseries_path.read_text(encoding="utf-8"))
    observations = timeseries.get("observations") or []
    if not observations:
        return False

    upsert_observations(conn, observations)

    meta_path = data_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}

    set_meta(conn, "generated_at", timeseries.get("generated_at"))
    set_meta(conn, "start", timeseries.get("start"))
    for key in ("latest_month", "latest", "mom", "reaction_function_flag",
                "diff", "sources", "methodology"):
        if key in meta:
            set_meta(conn, key, meta[key])

    if meta.get("rate_changes"):
        replace_rate_changes(conn, meta["rate_changes"])

    events_path = config_dir / "events.json"
    if events_path.exists():
        replace_events(conn, json.loads(events_path.read_text(encoding="utf-8")))
    elif meta.get("events"):
        replace_events(conn, meta["events"])

    commentary_path = data_dir / "commentary.json"
    if commentary_path.exists():
        commentary = json.loads(commentary_path.read_text(encoding="utf-8"))
        for entry in reversed(commentary.get("entries") or []):
            append_commentary(conn, entry)

    conn.commit()
    return True
