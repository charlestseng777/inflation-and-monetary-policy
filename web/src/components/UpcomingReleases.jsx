import { dayLong } from '../lib/format.js'

/** Whole days between now and an ISO 'YYYY-MM-DD' date, rounded up. */
function daysUntil(iso) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const target = new Date(`${iso}T00:00:00`)
  return Math.round((target - today) / 86400000)
}

function countdownLabel(days) {
  if (days < 0) return 'overdue'
  if (days === 0) return 'today'
  if (days === 1) return 'tomorrow'
  return `in ${days}d`
}

/**
 * The next scheduled release of each series the dashboard is built around —
 * ONS's own `nextRelease` field on the CPI, GDP and wage-growth series (no
 * extra fetch: it rides along on the series data already pulled) plus the
 * Bank's published MPC calendar. See fetch_mpc_news/upcoming_releases in
 * fetcher/fetch.py. Refreshed on the fetcher's normal schedule.
 */
export default function UpcomingReleasesCard({ releases, className = '' }) {
  const items = releases ?? []

  return (
    <section className={`card card-pad flex min-h-0 flex-col ${className}`} aria-label="Upcoming data">
      <div className="label-xs">Upcoming data</div>

      {items.length ? (
        <ul className="mt-2.5 min-h-0 flex-1 space-y-2 overflow-y-auto pr-1 scroll-thin">
          {items.map((entry) => {
            const days = daysUntil(entry.date)
            const soon = days <= 3
            return (
              <li
                key={entry.id}
                className={`flex items-center justify-between gap-2 rounded-md border px-2.5 py-2 text-xs ${
                  soon ? 'border-white/15 bg-white/[0.04]' : 'border-hairline'
                }`}
              >
                <div className="min-w-0">
                  <div className="truncate font-medium text-ink">{entry.label}</div>
                  <div className="num mt-0.5 text-[10px] text-faint">
                    {dayLong(entry.date)} · {entry.source}
                  </div>
                </div>
                <span className={`num shrink-0 text-[11px] font-medium ${soon ? 'text-ink' : 'text-faint'}`}>
                  {countdownLabel(days)}
                </span>
              </li>
            )
          })}
        </ul>
      ) : (
        <p className="mt-2.5 min-h-0 flex-1 text-xs leading-relaxed text-muted">
          No upcoming release dates available.
        </p>
      )}

      <p className="mt-3 border-t border-hairline pt-2.5 text-[10px] leading-relaxed text-faint">
        CPI, GDP and wage growth dates come from ONS; the policy decision date
        from the Bank's published MPC calendar.
      </p>
    </section>
  )
}
