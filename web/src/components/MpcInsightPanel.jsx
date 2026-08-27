import { MPC_ACTION_LABEL } from '../lib/mpcInsight.js'
import { VOTE_TONE } from '../lib/series.js'
import { dayLong, pct } from '../lib/format.js'

function VoteChip({ name, vote, tone }) {
  return (
    <li className="flex items-center justify-between gap-2 text-[11px]">
      <span className="flex min-w-0 items-center gap-1.5 text-muted">
        <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: tone }} aria-hidden="true" />
        <span className="truncate">{name}</span>
      </span>
      <span className="num shrink-0 text-ink">{pct(vote, 2)}</span>
    </li>
  )
}

function DecisionBadge({ decision }) {
  if (!decision) return null
  return (
    <span className="rounded border border-hairline px-1.5 py-0.5 text-[9px] text-faint">
      {MPC_ACTION_LABEL[decision.action]} · {decision.split} · {dayLong(decision.date)}
    </span>
  )
}

/** Who voted which way at the meeting nearest the clicked month. */
export function VoteBreakdownCard({ decision, className = '' }) {
  return (
    <section className={`card card-pad flex min-h-0 flex-col ${className}`} aria-live="polite" aria-label="Vote breakdown">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="label-xs">Vote breakdown</div>
        <DecisionBadge decision={decision} />
      </div>

      {decision ? (
        <div className="mt-2.5 min-h-0 flex-1 overflow-y-auto pr-1 scroll-thin">
          {decision.hawks.length > 0 && (
            <div className="mb-2.5">
              <div className="mb-1 text-[10px] font-medium uppercase tracking-[0.1em]" style={{ color: VOTE_TONE.hawk }}>
                Hawks · voted higher
              </div>
              <ul className="space-y-1">
                {decision.hawks.map((entry) => (
                  <VoteChip key={entry.name} name={entry.name} vote={entry.vote} tone={VOTE_TONE.hawk} />
                ))}
              </ul>
            </div>
          )}
          {decision.doves.length > 0 && (
            <div className="mb-2.5">
              <div className="mb-1 text-[10px] font-medium uppercase tracking-[0.1em]" style={{ color: VOTE_TONE.dove }}>
                Doves · voted lower
              </div>
              <ul className="space-y-1">
                {decision.doves.map((entry) => (
                  <VoteChip key={entry.name} name={entry.name} vote={entry.vote} tone={VOTE_TONE.dove} />
                ))}
              </ul>
            </div>
          )}
          <div>
            <div className="mb-1 text-[10px] font-medium uppercase tracking-[0.1em] text-faint">
              {decision.unanimous ? 'Unanimous' : 'With the majority'}
            </div>
            <ul className="space-y-1">
              {decision.members.map((entry) => (
                <VoteChip key={entry.name} name={entry.name} vote={entry.vote} tone="#5A6273" />
              ))}
            </ul>
          </div>
        </div>
      ) : (
        <p className="mt-2.5 min-h-0 flex-1 text-xs leading-relaxed text-muted">
          No meeting data for this point in the series.
        </p>
      )}
    </section>
  )
}

/**
 * The Bank of England's own Monetary Policy Summary for the meeting nearest
 * the clicked month — copied verbatim from bankofengland.co.uk, not
 * generated. See fetcher/mpc_summary.py for how it's scraped. Meetings before
 * August 2021 have no HTML summary on the Bank's site (PDF only), in which
 * case this falls back to a link into the Bank's own archive.
 */
export function MonetaryPolicySummaryCard({ decision, summary }) {
  return (
    <section className="card card-pad" aria-live="polite" aria-label="Monetary Policy Summary">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="label-xs">Monetary Policy Summary</div>
        <DecisionBadge decision={decision} />
      </div>

      {summary ? (
        <>
          <h3 className="mt-2.5 text-[13px] font-semibold leading-snug text-ink">
            {summary.heading}
          </h3>
          <div className="mt-2 space-y-2.5 text-[13px] leading-relaxed text-muted">
            {summary.paragraphs.map((paragraph, index) => (
              <p key={index}>{paragraph}</p>
            ))}
          </div>
          <a
            href={summary.url}
            target="_blank"
            rel="noreferrer"
            className="mt-3 inline-block text-[11px] text-muted underline decoration-hairline underline-offset-2 hover:text-ink"
          >
            Read the full Monetary Policy Summary and minutes on bankofengland.co.uk ↗
          </a>
        </>
      ) : decision ? (
        <p className="mt-2.5 text-xs leading-relaxed text-muted">
          The Bank of England only began publishing this as readable text in August
          2021 — earlier meetings are PDF-only. See the{' '}
          <a
            href="https://www.bankofengland.co.uk/monetary-policy-summary-and-minutes"
            target="_blank"
            rel="noreferrer"
            className="underline decoration-hairline underline-offset-2 hover:text-ink"
          >
            Bank's archive
          </a>{' '}
          directly.
        </p>
      ) : (
        <p className="mt-2.5 text-xs leading-relaxed text-muted">
          Click a month on the chart to read the nearest MPC decision.
        </p>
      )}
    </section>
  )
}
