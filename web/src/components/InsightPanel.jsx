import { useMemo } from 'react'
import { buildInsight, STANCE_STYLES } from '../lib/insight.js'
import { monthLong } from '../lib/format.js'

export default function InsightPanel({ observations, focusIndex, events, commentary, flag }) {
  const insight = useMemo(
    () => buildInsight(observations, focusIndex, events),
    [observations, focusIndex, events],
  )

  const stance = STANCE_STYLES[insight?.stance ?? 'unclear']
  const note = commentary?.[0]

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <section className="card card-pad lg:col-span-2" aria-live="polite" aria-label="Generated commentary">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="label-xs">Insight engine</div>
          <div className="flex items-center gap-2">
            <span className={`rounded-md border px-2 py-0.5 text-[10px] font-medium ${stance.className}`}>
              {stance.label} stance
            </span>
            <span className="num text-[11px] text-faint">{insight?.month ?? '—'}</span>
          </div>
        </div>

        <p key={insight?.month} className="mt-3 animate-fade-up text-[13px] leading-relaxed text-ink">
          {insight?.text ?? 'Hover the chart to read any month.'}
        </p>

        <p className="mt-3 border-t border-hairline pt-2.5 text-[10px] leading-relaxed text-faint">
          Generated deterministically from the published data on hover — it restates
          arithmetic already in the series and asserts nothing beyond it.
        </p>
      </section>

      <section className="card card-pad" aria-label="Latest release note">
        <div className="flex items-center justify-between gap-2">
          <div className="label-xs">Release note</div>
          {note?.model && (
            <span className="rounded border border-hairline px-1.5 py-0.5 text-[9px] text-faint">
              {note.model}
            </span>
          )}
        </div>

        {note ? (
          <>
            <h3 className="mt-2.5 text-[13px] font-semibold leading-snug text-ink">
              {note.headline}
            </h3>
            <p className="mt-2 text-xs leading-relaxed text-muted">{note.note}</p>
            {note.flag && (
              <p className="mt-2.5 rounded-md border border-[#c98500]/35 bg-[#c98500]/10 p-2 text-[11px] leading-relaxed text-[#e8bc6a]">
                {note.flag}
              </p>
            )}
            <p className="mt-2.5 text-[10px] text-faint">
              Written by Claude when {monthLong(note.observation_month)} data landed.
            </p>
          </>
        ) : (
          <>
            <p className="mt-2.5 text-xs leading-relaxed text-muted">
              No LLM-written note yet. The fetcher writes one each time new ONS or Bank
              of England data lands, provided <code className="text-faint">ANTHROPIC_API_KEY</code>{' '}
              is set.
            </p>
            {flag && (
              <p className="mt-2.5 rounded-md border border-[#c98500]/35 bg-[#c98500]/10 p-2 text-[11px] leading-relaxed text-[#e8bc6a]">
                {flag.detail}
              </p>
            )}
          </>
        )}
      </section>
    </div>
  )
}
