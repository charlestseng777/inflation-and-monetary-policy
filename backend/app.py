"""
Read-only API for the UK inflation dashboard.

Serves the same three payloads the frontend already consumed as static files,
at the same paths, so the move to Postgres needed no change to any component
other than pointing the frontend at this origin.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from . import database

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CONFIG_DIR = ROOT / "config"

# The data changes a few times a day at most. A short in-process cache keeps
# the database out of the request path and stays well inside the connection
# limits on small Postgres plans.
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "60"))
BROWSER_CACHE_SECONDS = int(os.environ.get("BROWSER_CACHE_SECONDS", "300"))

logger = logging.getLogger("dashboard.api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

_cache: dict[str, tuple[float, dict]] = {}


def _cached(key: str, builder):
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_TTL_SECONDS:
        return hit[1]

    with database.connect() as conn:
        payload = builder(conn)

    _cache[key] = (now, payload)
    return payload


@asynccontextmanager
async def lifespan(_: FastAPI):
    # A database that is briefly unreachable at boot should not permanently
    # break the service — log it and let the health check report the state.
    if not database.is_configured():
        logger.error("DATABASE_URL is not set; every data endpoint will return 503")
    else:
        try:
            database.init_schema()
            logger.info("schema ready")
            with database.connect() as conn:
                if database.seed_from_files(conn, DATA_DIR, CONFIG_DIR):
                    logger.info("empty database seeded from committed JSON")
        except Exception as error:  # noqa: BLE001 - never crash the process on boot
            logger.exception("start-up database work failed: %s", error)
    yield


app = FastAPI(
    title="UK Inflation & Monetary Policy API",
    description="CPI decomposition and Bank Rate, sourced from the ONS and the Bank of England.",
    version="1.0.0",
    lifespan=lifespan,
)

# The frontend is deployed as a separate static site, so it is a different
# origin. Set ALLOWED_ORIGINS to lock this down to your own domain.
origins = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _serve(response: Response, key: str, builder) -> dict:
    if not database.is_configured():
        raise HTTPException(status_code=503, detail="Database is not configured")
    try:
        payload = _cached(key, builder)
    except HTTPException:
        raise
    except Exception as error:  # noqa: BLE001
        logger.exception("failed to build %s", key)
        raise HTTPException(status_code=503, detail="Data store unavailable") from error

    if not payload.get("observations") and key == "timeseries":
        raise HTTPException(
            status_code=503,
            detail="No observations stored yet — run the fetcher job once.",
        )

    response.headers["Cache-Control"] = f"public, max-age={BROWSER_CACHE_SECONDS}"
    return payload


@app.get("/health")
def health():
    """Liveness plus a real check that the data store answers."""
    if not database.is_configured():
        return {"status": "degraded", "database": "unconfigured"}
    try:
        with database.connect() as conn:
            count = database.observation_count(conn)
        return {"status": "ok", "database": "up", "observations": count}
    except Exception as error:  # noqa: BLE001
        logger.warning("health check could not reach the database: %s", error)
        return Response(
            content='{"status":"degraded","database":"unreachable"}',
            media_type="application/json",
            status_code=503,
        )


@app.get("/")
def index():
    return {
        "name": "UK Inflation & Monetary Policy API",
        "endpoints": [
            "/data/timeseries.json",
            "/data/meta.json",
            "/data/commentary.json",
            "/health",
        ],
        "sources": ["ONS MM23 / LMS", "Bank of England IADB"],
    }


@app.get("/data/timeseries.json")
def timeseries(response: Response):
    return _serve(response, "timeseries", database.build_timeseries_payload)


@app.get("/data/meta.json")
def meta(response: Response):
    return _serve(response, "meta", database.build_meta_payload)


@app.get("/data/commentary.json")
def commentary(response: Response):
    return _serve(response, "commentary", database.build_commentary_payload)
