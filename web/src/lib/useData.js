import { useState } from 'react'

// This build runs as a self-contained Cowork Artifact rather than against the
// API/static-file setup the rest of this comment used to describe: there is
// no server to fetch from, so the data this dashboard reads is embedded
// directly on the page as `window.__DASHBOARD_DATA__` (see the script block
// the Cowork job writes ahead of this bundle). A daily refresh replaces that
// block and republishes the page; this bundle itself doesn't change.
function readEmbeddedBundle() {
  if (typeof window === 'undefined' || !window.__DASHBOARD_DATA__) {
    return { status: 'error', error: 'Embedded dashboard data was not found on the page.' }
  }
  const { timeseries, meta, commentary } = window.__DASHBOARD_DATA__
  const observations = timeseries?.observations ?? []
  if (!observations.length) {
    return { status: 'error', error: 'The embedded timeseries data contained no observations.' }
  }
  return {
    status: 'ready',
    observations,
    meta: meta ?? {},
    events: meta?.events ?? [],
    mpcDecisions: meta?.mpc_decisions ?? [],
    mpcSummaries: meta?.mpc_summaries ?? {},
    mpcNews: meta?.mpc_news ?? {},
    upcomingReleases: meta?.upcoming_releases ?? [],
    syntheticCurve: meta?.synthetic_mpc_curve ?? null,
    commentary: commentary?.entries ?? [],
    generatedAt: timeseries?.generated_at ?? meta?.generated_at ?? null,
  }
}

export function useData() {
  const [state] = useState(readEmbeddedBundle)
  return state
}
