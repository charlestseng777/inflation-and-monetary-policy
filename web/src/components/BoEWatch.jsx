import { BOE_INDICATORS } from '../lib/series.js'
import { deltaArrow, deltaTone, pct, pp } from '../lib/format.js'

function Stars({ count }) {
  return (
    <span
      className="text-xs tracking-[0.15em]"
      aria-label={`Importance ${count} out of 5`}
      title={`Importance ${count} of 5`}
    >
      <span className="text-[#E9B872]">{'★'.repeat(count)}</span>
      <span className="text-faint">{'☆'.repeat(5 - count)}</span>
    </span>
  )
}

function Attribute({ label, value }) {
  return (
    <div className="flex gap-2 text-[11px] leading-relaxed">
      <span className="w-[104px] shrink-0 text-faint">{label}</span>
      <span className="flex-1 text-muted">{value}</span>
    </div>
  )
}

export default function BoEWatch({ row }) {
  return (
    <section className="card" aria-label="What the Bank of England watches">
      <header className="border-b border-hairline px-4 py-3.5 sm:px-5">
        <h2 className="text-sm font-semibold text-ink">What the Bank of England watches</h2>
        <p className="mt-0.5 max-w-3xl text-xs leading-relaxed text-muted">
          The MPC targets headline CPI, but it does not react to headline CPI. Ranked
          by how much weight each indicator actually carries in the decision — the
          test throughout is whether a move reflects domestic, persistent pressure or
          an imported shock that will drop out of the annual comparison on its own.
        </p>
      </header>

      <div className="grid gap-3 p-4 sm:p-5 lg:grid-cols-2 xl:grid-cols-3">
        {BOE_INDICATORS.map((indicator) => {
          const value = row?.[indicator.id]
          const change = row?.mom?.[indicator.id]
          return (
            <article
              key={indicator.id}
              className="rounded-lg border border-hairline bg-raised/60 p-4 transition-colors hover:border-white/15"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span
                    className="h-2.5 w-2.5 rounded-sm"
                    style={{ backgroundColor: indicator.color }}
                    aria-hidden="true"
                  />
                  <h3 className="text-sm font-semibold text-ink">{indicator.label}</h3>
                </div>
                <Stars count={indicator.stars} />
              </div>

              <div className="mt-3 flex items-baseline gap-2">
                <span className="num text-2xl font-semibold leading-none text-ink">
                  {value === null || value === undefined ? '—' : value.toFixed(1)}
                </span>
                <span className="text-sm text-faint">%</span>
                <span className={`num ml-1 text-[11px] ${deltaTone(change)}`}>
                  {deltaArrow(change)} {pp(change)}
                </span>
              </div>

              <p className="mt-3 text-[11px] leading-relaxed text-muted">{indicator.why}</p>

              <div className="mt-3 space-y-1.5 border-t border-hairline pt-3">
                <Attribute label="Domestic?" value={indicator.domestic} />
                <Attribute label="Volatility" value={indicator.volatile} />
                <Attribute label="Policy-sensitive?" value={indicator.policySensitive} />
              </div>
            </article>
          )
        })}
      </div>

      {row && (
        <footer className="border-t border-hairline px-4 py-3 text-[11px] leading-relaxed text-faint sm:px-5">
          Read together for the latest month: headline at{' '}
          <span className="num text-muted">{pct(row.headline_cpi)}</span> tells you what
          households are paying; services at{' '}
          <span className="num text-muted">{pct(row.services_cpi)}</span>
          {row.wage_growth !== null && row.wage_growth !== undefined && (
            <> and pay growth at <span className="num text-muted">{pct(row.wage_growth)}</span></>
          )}{' '}
          tell you whether the Bank has finished its job.
        </footer>
      )}
    </section>
  )
}
