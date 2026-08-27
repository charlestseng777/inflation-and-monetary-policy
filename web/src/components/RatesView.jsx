import { useMemo, useState } from 'react'
import {
  Area, AreaChart, CartesianGrid, ComposedChart, Line, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import {
  CHROME, MPC_ACTION_TONE, PALETTE, RATES_CONTEXT_SERIES, RATES_SERIES,
  SYNTHETIC_CURVE_DESCRIPTION,
} from '../lib/series.js'
import { MPC_ACTION_LABEL } from '../lib/mpcInsight.js'
import { axisTick, monthLong, pct, pp } from '../lib/format.js'
import RangeSlider from './RangeSlider.jsx'

const NEGATIVE = '#3987e5' // real rate below zero — policy loose in real terms
const POSITIVE = '#d95926' // real rate above zero — policy restrictive

/** Small hover-triggered explainer, used next to the synthetic curve's name. */
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

function RatesTooltip({ active, payload, label, extras = [] }) {
  if (!active || !payload?.length) return null
  const row = payload[0]?.payload
  if (!row) return null

  const series = [...RATES_SERIES, ...extras]

  return (
    <div className="pointer-events-none w-[240px] rounded-lg border border-hairline bg-[#10131A]/95 p-3 shadow-2xl backdrop-blur">
      <div className="num text-xs font-semibold text-ink">{monthLong(label)}</div>
      <div className="mt-0.5 text-[10px] uppercase tracking-[0.12em] text-faint">
        Percent · change on previous month
      </div>

      <div className="mt-2.5 space-y-1.5">
        {series.map((item) => {
          const value = row[item.id]
          if (value === null || value === undefined) return null
          const change = row.mom?.[item.id]
          return (
            <div key={item.id} className="flex items-center gap-2 text-xs">
              <span
                className="h-2 w-2 shrink-0 rounded-sm"
                style={{ backgroundColor: item.color }}
                aria-hidden="true"
              />
              <span className="flex-1 truncate text-muted">{item.label}</span>
              <span className="num w-12 text-right font-medium text-ink">{pct(value, 2)}</span>
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

export function MarketPricingChart({
  data, decisions, focusMonth, onSelectMonth, observations, range, onRangeChange,
}) {
  const [enabled, setEnabled] = useState([])

  function toggleContext(id) {
    setEnabled((current) => (current.includes(id)
      ? current.filter((entry) => entry !== id)
      : [...current, id]))
  }

  const visibleContext = useMemo(
    () => RATES_CONTEXT_SERIES.filter((series) => enabled.includes(series.id)),
    [enabled],
  )

  const from = data[0]?.date
  const to = data[data.length - 1]?.date
  const meetings = useMemo(
    () => (decisions ?? []).filter((entry) => entry.month >= from && entry.month <= to),
    [decisions, from, to],
  )

  const priced = data.filter((row) => row.expected_rate !== null && row.expected_rate !== undefined).length
  const avgAbsGap = useMemo(() => {
    const gaps = data.map((row) => row.expected_gap).filter((v) => v !== null && v !== undefined)
    if (!gaps.length) return null
    return gaps.reduce((sum, v) => sum + Math.abs(v), 0) / gaps.length
  }, [data])

  return (
    <section className="card" aria-label="Market pricing versus Bank Rate decisions">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-hairline px-4 py-3.5 sm:px-5">
        <div>
          <h2 className="text-sm font-semibold text-ink">Market pricing versus Bank Rate decisions</h2>
          <p className="mt-0.5 max-w-3xl text-xs leading-relaxed text-muted">
            Bank Rate as actually decided against the Synthetic MPC OIS Curve — the
            market's live forecast of the Committee's near-term path. Markers mark
            each MPC meeting; click the chart for the vote and the pricing surprise
            below.
          </p>
        </div>

        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Context series">
          {RATES_CONTEXT_SERIES.map((series) => {
            const on = enabled.includes(series.id)
            return (
              <button
                key={series.id}
                type="button"
                aria-pressed={on}
                onClick={() => toggleContext(series.id)}
                title={`Toggle ${series.label}`}
                className={`chip ${on ? 'chip-on' : ''}`}
              >
                <span
                  className="h-2 w-2 rounded-sm"
                  style={{ backgroundColor: on ? series.color : '#3A4150' }}
                  aria-hidden="true"
                />
                {series.label}
              </button>
            )
          })}
        </div>
      </header>

      <RangeSlider observations={observations} range={range} onChange={onRangeChange} />

      <div className="h-[400px] px-1 py-4 sm:px-2">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={data}
            syncId="uk-macro"
            margin={{ top: 22, right: 24, bottom: 4, left: 4 }}
            onClick={(state) => state?.activeLabel && onSelectMonth?.(state.activeLabel)}
          >
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
              domain={['auto', 'auto']}
            />
            <ReferenceLine y={0} stroke={CHROME.axis} />

            {meetings.map((meeting) => {
              const active = meeting.month === focusMonth
              const tone = MPC_ACTION_TONE[meeting.action] ?? CHROME.faint
              return (
                <ReferenceLine
                  key={meeting.date}
                  x={meeting.month}
                  stroke={tone}
                  strokeOpacity={active ? 0.85 : 0.25}
                  strokeDasharray="3 3"
                  ifOverflow="hidden"
                  label={({ viewBox }) => (
                    <g transform={`translate(${viewBox.x}, ${viewBox.y - 6})`}>
                      <circle
                        r={active ? 5 : 3.5}
                        fill={active ? tone : CHROME.surface}
                        stroke={tone}
                        strokeWidth={1.75}
                      />
                    </g>
                  )}
                />
              )
            })}

            <Tooltip
              cursor={{ stroke: '#4A5468', strokeWidth: 1, strokeDasharray: '3 3' }}
              isAnimationActive={false}
              content={<RatesTooltip extras={visibleContext} />}
            />

            {[...RATES_SERIES, ...visibleContext].map((series) => (
              <Line
                key={series.id}
                type={series.step ? 'stepAfter' : 'monotone'}
                dataKey={series.id}
                name={series.label}
                stroke={series.color}
                strokeWidth={series.width}
                strokeDasharray={series.dashed ? '5 3' : undefined}
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
            <span
              className="h-0.5 w-4 rounded"
              style={{
                backgroundColor: series.color,
                backgroundImage: series.dashed
                  ? `repeating-linear-gradient(90deg, ${series.color} 0 4px, transparent 4px 7px)`
                  : undefined,
              }}
              aria-hidden="true"
            />
            {series.label}
            {series.id === 'expected_rate' && <InfoIcon text={SYNTHETIC_CURVE_DESCRIPTION} />}
          </span>
        ))}
        {visibleContext.map((series) => (
          <span key={series.id} className="flex items-center gap-1.5 text-[11px] text-muted">
            <span className="h-0.5 w-4 rounded" style={{ backgroundColor: series.color }} aria-hidden="true" />
            {series.label}
          </span>
        ))}
        <span className="flex items-center gap-1.5 text-[11px] text-muted">
          <span className="h-2 w-2 rounded-full border-2" style={{ borderColor: MPC_ACTION_TONE.hike }} aria-hidden="true" />
          {MPC_ACTION_LABEL.hike} <span className="h-2 w-2 rounded-full border-2 ml-2" style={{ borderColor: MPC_ACTION_TONE.cut }} aria-hidden="true" />
          {MPC_ACTION_LABEL.cut} <span className="h-2 w-2 rounded-full border-2 ml-2" style={{ borderColor: MPC_ACTION_TONE.hold }} aria-hidden="true" />
          {MPC_ACTION_LABEL.hold}
        </span>
        <span className="ml-auto text-[11px] text-faint">
          <span className="num text-muted">{priced}</span> months priced ·{' '}
          avg gap <span className="num text-muted">{avgAbsGap === null ? '—' : `${avgAbsGap.toFixed(2)}pp`}</span>
        </span>
      </footer>
    </section>
  )
}

export function RealRateChart({ data }) {
  return (
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
  )
}
