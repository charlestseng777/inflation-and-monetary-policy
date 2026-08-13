import { useEffect, useState } from 'react'

const FILES = {
  timeseries: 'data/timeseries.json',
  meta: 'data/meta.json',
  commentary: 'data/commentary.json',
}

async function loadJson(path, { optional = false } = {}) {
  const response = await fetch(`${import.meta.env.BASE_URL}${path}`)
  if (!response.ok) {
    if (optional) return null
    throw new Error(`Could not load ${path} (${response.status})`)
  }
  return response.json()
}

export function useData() {
  const [state, setState] = useState({ status: 'loading' })

  useEffect(() => {
    let cancelled = false

    Promise.all([
      loadJson(FILES.timeseries),
      loadJson(FILES.meta),
      loadJson(FILES.commentary, { optional: true }),
    ])
      .then(([timeseries, meta, commentary]) => {
        if (cancelled) return
        const observations = timeseries?.observations ?? []
        if (!observations.length) {
          throw new Error('timeseries.json contained no observations')
        }
        setState({
          status: 'ready',
          observations,
          meta: meta ?? {},
          events: meta?.events ?? [],
          commentary: commentary?.entries ?? [],
          generatedAt: timeseries?.generated_at ?? meta?.generated_at ?? null,
        })
      })
      .catch((error) => {
        if (!cancelled) setState({ status: 'error', error: error.message })
      })

    return () => { cancelled = true }
  }, [])

  return state
}
