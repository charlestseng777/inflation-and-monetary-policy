import { useMemo } from 'react'
import { buildInsight, STANCE_STYLES } from '../lib/insight.js'

export function InsightEngineCard({ observations, focusIndex, events, className = '' }) {
  const insight = useMemo(
    () => buildInsight(observations, focusIndex, events),
    [observations, focusIndex, events],
  )

  const stance = STANCE_STYLES[insight?.stance ?? 'unclear']

  return (
    <section className={`card card-pad flex min-h-0 flex-col ${className}`} aria-live="polite" aria-label="Generated commentary">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="label-xs">Insight engine</div>
        <div className="flex items-center gap-2">
          <span className={`rounded-md border px-2 py-0.5 text-[10px] font-medium ${stance.className}`}>
            {stance.label} stance
          </span>
          <span className="num text-[11px] text-faint">{insight?.month ?? '—'}</span>
        </div>
      </div>

      <p
        key={insight?.month}
        className="mt-3 min-h-0 flex-1 animate-fade-up overflow-y-auto text-[13px] leading-relaxed text-ink"
      >
        {insight?.text ?? 'Click a month on the chart to read it.'}
      </p>

      <p className="mt-3 border-t border-hairline pt-2.5 text-[10px] leading-relaxed text-faint">
        Generated deterministically from the published data — it restates arithmetic
        already in the series and asserts nothing beyond it.
      </p>
    </section>
  )
}
