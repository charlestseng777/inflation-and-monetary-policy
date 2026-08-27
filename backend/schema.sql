-- Schema for the UK inflation dashboard.
--
-- One row per month in `observations`; the nested structures the frontend
-- already expects (contributions, weights, index levels, month-on-month
-- changes) are kept as JSONB rather than exploded into columns, so the API can
-- hand back exactly the same payload shape the static JSON version served.

CREATE TABLE IF NOT EXISTS observations (
    month                TEXT PRIMARY KEY,          -- 'YYYY-MM'
    headline_cpi         NUMERIC,
    core_cpi             NUMERIC,
    services_cpi         NUMERIC,
    goods_cpi            NUMERIC,
    core_goods_cpi       NUMERIC,
    food_cpi             NUMERIC,
    energy_cpi           NUMERIC,
    alcohol_tobacco_cpi  NUMERIC,
    wage_growth          NUMERIC,
    policy_rate          NUMERIC,
    real_rate            NUMERIC,
    expected_rate        NUMERIC,
    expected_gap         NUMERIC,
    ois_m1               NUMERIC,
    ois_m2               NUMERIC,
    contributions        JSONB NOT NULL DEFAULT '{}'::jsonb,
    weights              JSONB NOT NULL DEFAULT '{}'::jsonb,
    index_levels         JSONB NOT NULL DEFAULT '{}'::jsonb,
    mom                  JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS observations_month_idx ON observations (month);

-- Columns added after the first deploy. `CREATE TABLE IF NOT EXISTS` above is a
-- no-op against an existing database, so new columns have to be added here.
ALTER TABLE observations ADD COLUMN IF NOT EXISTS expected_rate NUMERIC;
ALTER TABLE observations ADD COLUMN IF NOT EXISTS expected_gap  NUMERIC;
ALTER TABLE observations ADD COLUMN IF NOT EXISTS ois_m1        NUMERIC;
ALTER TABLE observations ADD COLUMN IF NOT EXISTS ois_m2        NUMERIC;
ALTER TABLE observations ADD COLUMN IF NOT EXISTS pricing_bp    NUMERIC;
ALTER TABLE observations ADD COLUMN IF NOT EXISTS ois_3m        NUMERIC;
ALTER TABLE observations ADD COLUMN IF NOT EXISTS ois_2y        NUMERIC;
ALTER TABLE observations ADD COLUMN IF NOT EXISTS gdp_growth    NUMERIC;

-- Every Bank Rate decision, with the exact date it took effect.
CREATE TABLE IF NOT EXISTS rate_changes (
    change_date  DATE PRIMARY KEY,
    month        TEXT NOT NULL,
    rate_from    NUMERIC,
    rate_to      NUMERIC,
    change       NUMERIC
);

-- Macro event markers, loaded from config/events.json.
CREATE TABLE IF NOT EXISTS events (
    id           TEXT PRIMARY KEY,
    month        TEXT NOT NULL,
    label        TEXT NOT NULL,
    category     TEXT,
    description  TEXT,
    span_end     TEXT,
    span_label   TEXT,
    sort_order   INTEGER NOT NULL DEFAULT 0
);

-- Rolling log of LLM-written release notes, newest first.
CREATE TABLE IF NOT EXISTS commentary (
    id                 BIGSERIAL PRIMARY KEY,
    generated_at       TIMESTAMPTZ NOT NULL,
    observation_month  TEXT NOT NULL,
    headline           TEXT,
    note               TEXT,
    stance             TEXT,
    flag               TEXT,
    model              TEXT,
    context            JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS commentary_generated_idx
    ON commentary (generated_at DESC);

-- Everything else meta.json carries: latest values, the diff from the last
-- run, source citations, the methodology note, the reaction-function flag.
CREATE TABLE IF NOT EXISTS meta (
    key         TEXT PRIMARY KEY,
    value       JSONB NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Audit trail for the scheduled job: did it run, did anything change.
CREATE TABLE IF NOT EXISTS fetch_runs (
    id             BIGSERIAL PRIMARY KEY,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ,
    status         TEXT NOT NULL,
    months_added   INTEGER NOT NULL DEFAULT 0,
    values_revised INTEGER NOT NULL DEFAULT 0,
    latest_month   TEXT,
    detail         TEXT
);

CREATE INDEX IF NOT EXISTS fetch_runs_started_idx
    ON fetch_runs (started_at DESC);
