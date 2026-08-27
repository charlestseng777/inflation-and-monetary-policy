import { MPC_ACTION_LABEL } from '../lib/mpcInsight.js'
import { SYNTHETIC_CURVE_DESCRIPTION } from '../lib/series.js'
import { dayLong, num, pct } from '../lib/format.js'

/** Small hover-triggered explainer — duplicated from RatesView.jsx deliberately;
 *  see the note there on why it isn't shared for one extra usage. */
function InfoIcon({ text }) {
  return (
    <span className="group relative inline-flex">
      <svg
        className="h-3.5 w-3.5 shrink-0 cursor-help text-faint transition-colors group-hover:text-muted"
        viewBox="0 0 16 16"
        fill="none"
        aria-hidden="true"
      >
        <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.3" />
        <path d="M8 7.2v4.3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
        <circle cx="8" cy="4.7" r="0.9" fill="currentColor" />
      </svg>
      <span
        role="tooltip"
        className="pointer-events-none absolute left-1/2 top-full z-10 mt-2 w-64 -translate-x-1/2 rounded-lg
                   border border-hairline bg-[#10131A]/95 p-2.5 text-[11px] leading-relaxed text-muted opacity-0
                   shadow-2xl backdrop-blur transition-opacity duration-150 group-hover:opacity-100"
      >
        {text}
      </span>
    </span>
  )
}

function pricingCell(meeting) {
  const { pricing_bp: bp, direction, probability_next_step_pct: prob, full_steps_priced: steps } = meeting
  if (bp === null || bp === undefined) return { text: '—', tone: 'text-faint' }
  if (direction === 'none' || Math.abs(bp) < 1) {
    return { text: 'No move priced', tone: 'text-faint' }
  }
  const verb = direction === 'hike' ? 'hike' : 'cut'
  const magnitude = `${num(Math.abs(bp), 1)}bp ${verb}`
  const probability = steps >= 1
    ? `${prob}% further`
    : `${prob}% prob.`
  return {
    text: `${magnitude} priced (${probability} 25bp)`,
    tone: direction === 'hike' ? 'text-[#E9B872]' : 'text-[#7FB9E8]',
  }
}

/**
 * The "output table" view of the synthetic curve: the next few MPC meetings
 * as of the latest data date, with the curve read, the bootstrapped forward,
 * the Bank-Rate-scale expectation, and the bp/probability priced for each.
 */
export default function SyntheticCurveTable({ curve }) {
  const meetings = curve?.meetings ?? []
  if (!meetings.length) return null

  return (
    <section className="card" aria-label="Synthetic MPC OIS curve">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-hairline px-4 py-3.5 sm:px-5">
        <div className="flex items-center gap-1.5">
          <h2 className="text-sm font-semibold text-ink">Synthetic MPC OIS Curve</h2>
          <InfoIcon text={SYNTHETIC_CURVE_DESCRIPTION} />
        </div>
        <span className="text-[11px] text-faint">
          As of <span className="num text-muted">{dayLong(curve.as_of)}</span> ·{' '}
          spread assumption <span className="num text-muted">{curve.spread_bps}bp</span>
        </span>
      </header>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-hairline text-[10px] uppercase tracking-[0.08em] text-faint">
              <th className="px-4 py-2.5 font-medium sm:px-5">MPC meeting</th>
              <th className="px-3 py-2.5 font-medium">Synthetic OIS</th>
              <th className="px-3 py-2.5 font-medium">Implied SONIA</th>
              <th className="px-3 py-2.5 font-medium">Implied Bank Rate</th>
              <th className="px-3 py-2.5 font-medium sm:pr-5">Market pricing</th>
            </tr>
          </thead>
          <tbody>
            {meetings.map((meeting) => {
              const pricing = pricingCell(meeting)
              return (
                <tr key={meeting.meeting} className="border-b border-hairline last:border-0">
                  <td className="px-4 py-2.5 text-ink sm:px-5">
                    {dayLong(meeting.meeting)}
                    <span className="ml-1.5 text-[10px] text-faint">
                      (T+{meeting.tenor_days}d)
                    </span>
                  </td>
                  <td className="num px-3 py-2.5 text-muted">{pct(meeting.synthetic_ois, 2)}</td>
                  <td className="num px-3 py-2.5 text-muted">{pct(meeting.implied_sonia, 2)}</td>
                  <td className="num px-3 py-2.5 font-medium text-ink">{pct(meeting.implied_rate, 2)}</td>
                  <td className={`px-3 py-2.5 sm:pr-5 ${pricing.tone}`}>{pricing.text}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <footer className="space-y-1.5 border-t border-hairline px-4 py-3 text-[10px] leading-relaxed text-faint sm:px-5">
        <p>
          <span className="text-muted">Synthetic OIS</span> is the curve-read OIS rate from
          today to that meeting's own date.{' '}
          <span className="text-muted">Implied SONIA</span> is a different window — the
          forward rate for the period starting right after that meeting's decision and
          running to the meeting after it, i.e. the average rate the market expects that
          meeting to actually set. The two are never the same number: nothing can move
          Bank Rate before a meeting happens, so the first window is close to today's rate
          almost by definition, and tells you very little about the decision itself.
          {meetings.some((m) => m.source === 'boe_ois_curve+sonia_floor') && (
            <> One or more legs used today's SONIA fixing as a floor — the meeting falls
            inside the Bank's shortest published tenor (1 month).</>
          )}
        </p>
        <p>
          <span className="text-muted">Spread</span> ({curve.spread_bps}bp, converting the
          SONIA-space forward to a Bank Rate expectation) is not a fixed assumption — it's
          the realised Bank Rate-minus-SONIA gap run through Holt's linear trend smoothing,
          re-estimated from every day back to 2015. A flat multi-year average was tested and
          rejected: the true spread has moved through very different regimes (~4bp through
          2015-2020, 5-7bp through the 2021-2023 hiking/QT cycle, under 2bp now), and a flat
          average lags a real trend like that rather than tracking it. Full derivation:{' '}
          <span className="text-muted">docs/synthetic-mpc-ois-methodology.md</span>.
        </p>
      </footer>
    </section>
  )
}
