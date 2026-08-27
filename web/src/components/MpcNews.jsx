/** Days (or hours) since an ISO datetime, as a short relative label. */
function relativeTime(iso) {
  if (!iso) return ''
  const diffMs = Date.now() - new Date(iso).getTime()
  const hours = Math.round(diffMs / 3_600_000)
  if (hours < 1) return 'just now'
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  if (days < 30) return `${days}d ago`
  return `${Math.round(days / 30)}mo ago`
}

/**
 * Recent headlines about each sitting MPC member, one Google News RSS search
 * per name — see fetcher/mpc_news.py. Flattened across every member and
 * sorted newest-first, since the point of this box is "what have the people
 * who set Bank Rate been saying lately", not a per-member breakdown.
 */
export default function LatestNewsCard({ news, className = '', limit = 8 }) {
  const items = Object.entries(news ?? {})
    .flatMap(([member, entries]) => (entries ?? []).map((entry) => ({ member, ...entry })))
    .sort((a, b) => (b.published ?? '').localeCompare(a.published ?? ''))
    .slice(0, limit)

  return (
    <section className={`card card-pad flex min-h-0 flex-col ${className}`} aria-label="Latest news">
      <div className="label-xs">Latest news</div>

      {items.length ? (
        <ul className="mt-2.5 min-h-0 flex-1 space-y-2.5 overflow-y-auto pr-1 scroll-thin">
          {items.map((item, index) => (
            <li key={index} className="border-b border-hairline pb-2.5 last:border-0 last:pb-0">
              <a
                href={item.link}
                target="_blank"
                rel="noreferrer"
                className="text-[13px] font-medium leading-snug text-ink underline decoration-hairline underline-offset-2 hover:text-ink hover:decoration-ink"
              >
                {item.title}
              </a>
              <div className="mt-1 flex flex-wrap items-center gap-x-1.5 text-[10px] text-faint">
                <span className="text-muted">{item.member}</span>
                {item.source && <span>· {item.source}</span>}
                <span className="num">· {relativeTime(item.published)}</span>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2.5 min-h-0 flex-1 text-xs leading-relaxed text-muted">
          No recent coverage found.
        </p>
      )}

      <p className="mt-3 border-t border-hairline pt-2.5 text-[10px] leading-relaxed text-faint">
        Searched by name via Google News — headlines and links are the
        publishers' own, not generated.
      </p>
    </section>
  )
}
