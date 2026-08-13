import { useMemo } from 'react'
import {
  Area, AreaChart, CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { CHROME, PALETTE, RATES_SERIES } from '../lib/series.js'
import { axisTick, monthLong, pct, pp } from '../lib/format.js'
import ChartTooltip from './ChartTooltip.jsx'

const NEGATIVE = '#3987e5' // real rate below zero — policy loose in real terms
const POSITIVE = '#d95926' // real rate above zero — policy restrictive

/** Collapse the month-by-month sign of the real rate into contiguous bands. */
function realRateBands(data) {
  const bands = []
  let current = null

  for (const row of data) {
    if (row.real_rate === null || row.real_rate === undefined) {
      current = null
      continue
    }
    const sign = row.real_rate >= 0 ? 'positive' : 'negative'
    if (!current || current.sign !== sign) {
      current = { sign, from: row.date, to: row.date }
      bands.push(current)
    } else {
      current.to = row.date
    }
  }
  return bands
}

function RealRateTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const value = payload[0]?.value
  return (
    <div className="pointer-events-none rounded-lg border border-hairline bg-[#10131A]/95 px-3 py-2 text-xs shadow-2xl backdrop-blur">
      <div className="num font-semibold text-ink">{monthLong(label)}</div>
      <div className="mt-1 flex items-center gap-2">
        <span className="text-muted">Real policy rate</span>
        <span className="num text-ink">{pp(value)}</span>
      </div>
      <div className="mt-0.5 text-[11px] text-faint">
        {value >= 0 ? 'Bank Rate above inflation' : 'Bank Rate below inflation'}
      </div>
    </div>
  )
}

export default function RatesView({ data, onHoverMonth }) {
  const bands = useMemo(() => realRateBands(data), [data])
  const colors = useMemo(
    () => Object.fromEntries(RATES_SERIES.map((series) => [series.id, series.color])),
    [],
  )

  const negativeMonths = data.filter((row) => row.real_rate !== null && row.real_rate < 0).length
  const positiveMonths = data.filter((row) => row.real_rate !== null && row.real_rate >= 0).length

  return (
    <div className="space-y-4">
      <section className="card" aria-label="Inflation versus Bank Rate">
        <header className="border-b border-hairline px-4 py-3.5 sm:px-5">
          <h2 className="text-sm font-semibold text-ink">Inflation versus Bank Rate</h2>
          <p className="mt-0.5 max-w-3xl text-xs leading-relaxed text-muted">
            All four series are annual percentages on one axis, so the vertical gap
            between Bank Rate and inflation is the real policy rate. Shaded blue where
            inflation ran above Bank Rate (negative real rates, policy loose in real
            terms); shaded orange where Bank Rate ran above inflation (positive real
            rates, policy restrictive).
          </p>
        </header>

        <div className="h-[400px] px-1 py-4 sm:px-2">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={data}
              syncId="uk-macro"
              margin={{ top: 10, right: 24, bottom: 4, left: 4 }}
              onMouseMove={(state) => onHoverMonth?.(state?.activeLabel ?? null)}
              onMouseLeave={() => onHoverMonth?.(null)}
            >
              {bands.map((band) => (
                <ReferenceArea
                  key={`${band.sign}-${band.from}`}
                  x1={band.from}
                  x2={band.to}
                  fill={band.sign === 'positive' ? POSITIVE : NEGATIVE}
                  fillOpacity={0.07}
                  stroke="none"
                  ifOverflow="hidden"
                />
              ))}

              <CartesianGrid stroke={CHROME.grid} vertical={false} />
              <XAxis
                dataKey="date"
                tickFormatter={axisTick}
                tickLine={false}
                axisLine={{ stroke: CHROME.axis }}
                minTickGap={28}
                interval="preserveStartEnd"
              />
              <YAxis
                tickFormatter={(value) => `${value}%`}
                tickLine={false}
                axisLine={false}
                width={46}
              />
              <ReferenceLine y={2} stroke="#4A5468" strokeDasharray="4 4" />
              <ReferenceLine y={0} stroke={CHROME.axis} />

              <Tooltip
                cursor={{ stroke: '#4A5468', strokeWidth: 1, strokeDasharray: '3 3' }}
                isAnimationActive={false}
                content={<ChartTooltip colors={colors} />}
              />

              {RATES_SERIES.map((series) => (
                <Line
                  key={series.id}
                  type={series.step ? 'stepAfter' : 'monotone'}
                  dataKey={series.id}
                  name={series.label}
                  stroke={series.color}
                  strokeWidth={series.width}
                  dot={false}
                  activeDot={{ r: 4.5, strokeWidth: 2, stroke: CHROME.surface }}
                  connectNulls
                  isAnimationActive={false}
                />
              ))}
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <footer className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-hairline px-4 py-3 sm:px-5">
          {RATES_SERIES.map((series) => (
            <span key={series.id} className="flex items-center gap-1.5 text-[11px] text-muted">
              <span className="h-0.5 w-4 rounded" style={{ backgroundColor: series.color }} aria-hidden="true" />
              {series.label}
            </span>
          ))}
          <span className="ml-auto text-[11px] text-faint">
            <span className="num text-muted">{negativeMonths}</span> months negative real ·{' '}
            <span className="num text-muted">{positiveMonths}</span> months positive real
          </span>
        </footer>
      </section>

      <section className="card" aria-label="Real policy rate">
        <header className="border-b border-hairline px-4 py-3.5 sm:px-5">
          <h2 className="text-sm font-semibold text-ink">Real policy rate</h2>
          <p className="mt-0.5 text-xs text-muted">
            Bank Rate minus headline CPI. A crude measure — the MPC sets policy against
            expected, not realised, inflation — but it is the cleanest single read on
            whether the stance was loose or tight at the time.
          </p>
        </header>

        <div className="h-[180px] px-1 py-4 sm:px-2">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} syncId="uk-macro" margin={{ top: 6, right: 24, bottom: 4, left: 4 }}>
              <defs>
                <linearGradient id="realRateFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={POSITIVE} stopOpacity={0.5} />
                  <stop offset="50%" stopColor={POSITIVE} stopOpacity={0.05} />
                  <stop offset="50%" stopColor={NEGATIVE} stopOpacity={0.05} />
                  <stop offset="100%" stopColor={NEGATIVE} stopOpacity={0.5} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={CHROME.grid} vertical={false} />
              <XAxis
                dataKey="date"
                tickFormatter={axisTick}
                tickLine={false}
                axisLine={{ stroke: CHROME.axis }}
                minTickGap={28}
                interval="preserveStartEnd"
              />
              <YAxis tickFormatter={(value) => `${value}`} tickLine={false} axisLine={false} width={46} />
              <ReferenceLine y={0} stroke="#4A5468" strokeWidth={1.5} />
              <Tooltip
                cursor={{ stroke: '#4A5468', strokeWidth: 1, strokeDasharray: '3 3' }}
                isAnimationActive={false}
                content={<RealRateTooltip />}
              />
              <Area
                type="monotone"
                dataKey="real_rate"
                name="Real policy rate"
                stroke={PALETTE.policy}
                strokeWidth={2}
                fill="url(#realRateFill)"
                connectNulls
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
  )
}
