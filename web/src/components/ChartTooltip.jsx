import { monthLong, pct, pp } from '../lib/format.js'

/**
 * Shared crosshair tooltip. Always shows the four series the MPC frames its
 * decisions around, then whatever else is currently plotted, so the reader can
 * compare like for like even when they have toggled extra lines on.
 */
const ALWAYS = [
  { id: 'headline_cpi', label: 'Headline CPI' },
  { id: 'core_cpi', label: 'Core CPI' },
  { id: 'services_cpi', label: 'Services CPI' },
  { id: 'policy_rate', label: 'Bank Rate' },
]

export default function ChartTooltip({ active, payload, label, extras = [], colors = {} }) {
  if (!active || !payload?.length) return null

  const row = payload[0]?.payload
  if (!row) return null

  const shown = new Set(ALWAYS.map((item) => item.id))
  const extraRows = extras.filter((item) => !shown.has(item.id))

  return (
    <div className="pointer-events-none w-[266px] rounded-lg border border-hairline bg-[#10131A]/95 p-3 shadow-2xl backdrop-blur">
      <div className="num text-xs font-semibold text-ink">{monthLong(label)}</div>
      <div className="mt-0.5 text-[10px] uppercase tracking-[0.12em] text-faint">
        Annual rate · change on previous month
      </div>

      <div className="mt-2.5 space-y-1.5">
        {[...ALWAYS, ...extraRows].map((item) => {
          const value = row[item.id]
          if (value === null || value === undefined) return null
          const change = row.mom?.[item.id]
          return (
            <div key={item.id} className="flex items-center gap-2 text-xs">
              <span
                className="h-2 w-2 shrink-0 rounded-sm"
                style={{ backgroundColor: colors[item.id] ?? '#5A6273' }}
                aria-hidden="true"
              />
              <span className="flex-1 truncate text-muted">{item.label}</span>
              <span className="num w-12 text-right font-medium text-ink">
                {pct(value, item.id === 'policy_rate' ? 2 : 1)}
              </span>
              <span className="num w-16 text-right text-faint">{pp(change)}</span>
            </div>
          )
        })}
      </div>

      {row.real_rate !== null && row.real_rate !== undefined && (
        <div className="mt-2.5 flex items-center justify-between border-t border-hairline pt-2 text-[11px]">
          <span className="text-faint">Real policy rate</span>
          <span className="num text-ink">{pp(row.real_rate)}</span>
        </div>
      )}
    </div>
  )
}
