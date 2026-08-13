import { useMemo, useState } from 'react'
import {
  Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import { CHROME, PALETTE, STACK_SERIES } from '../lib/series.js'
import { axisTick, monthLong, num, pct, pp } from '../lib/format.js'

const MODES = [
  {
    id: 'contribution',
    label: 'Contribution to inflation',
    unit: 'pp',
    blurb: 'Each band is that component\'s share of the headline annual rate — weight in the basket multiplied by its own inflation rate. The bands sum to headline CPI.',
  },
  {
    id: 'rate',
    label: 'Annual inflation rate',
    unit: '%',
    blurb: 'Each component\'s own annual rate. These are shown as lines, not a stack: component rates do not sum to headline — only weighted contributions do.',
  },
  {
    id: 'index',
    label: 'Index level',
    unit: '2015=100',
    blurb: 'Price level of each component, rebased to 2015 = 100. This is the cumulative story: where the price level ended up, not how fast it was moving.',
  },
]

function ComponentTooltip({ active, payload, label, mode }) {
  if (!active || !payload?.length) return null
  const total = payload.reduce((sum, entry) => sum + (entry.value ?? 0), 0)

  return (
    <div className="pointer-events-none w-[260px] rounded-lg border border-hairline bg-[#10131A]/95 p-3 shadow-2xl backdrop-blur">
      <div className="num text-xs font-semibold text-ink">{monthLong(label)}</div>
      <div className="mt-2 space-y-1.5">
        {[...payload].reverse().map((entry) => (
          <div key={entry.dataKey} className="flex items-center gap-2 text-xs">
            <span
              className="h-2 w-2 shrink-0 rounded-sm"
              style={{ backgroundColor: entry.color }}
              aria-hidden="true"
            />
            <span className="flex-1 truncate text-muted">{entry.name}</span>
            <span className="num font-medium text-ink">
              {mode === 'contribution' ? pp(entry.value) : mode === 'rate' ? pct(entry.value) : num(entry.value)}
            </span>
          </div>
        ))}
      </div>
      {mode === 'contribution' && (
        <div className="mt-2 flex items-center justify-between border-t border-hairline pt-2 text-[11px]">
          <span className="text-faint">Sum = headline CPI</span>
          <span className="num text-ink">{pct(total)}</span>
        </div>
      )}
    </div>
  )
}

export default function StackedChart({ data }) {
  const [mode, setMode] = useState('contribution')
  const active = MODES.find((entry) => entry.id === mode)

  const chartData = useMemo(() => data.map((row) => {
    const point = { date: row.date, headline_cpi: row.headline_cpi }
    for (const series of STACK_SERIES) {
      if (mode === 'contribution') {
        point[series.id] = row.contributions?.[series.id] ?? null
      } else if (mode === 'rate') {
        point[series.id] = series.rate ? row[series.rate] ?? null : null
      } else {
        point[series.id] = series.index ? row.index?.[series.index] ?? null : null
      }
    }
    return point
  }), [data, mode])

  // "Other" is a residual, and residual rates / index levels do not exist.
  const plotted = mode === 'contribution'
    ? STACK_SERIES
    : STACK_SERIES.filter((series) => series.id !== 'other')

  return (
    <section className="card" aria-label="CPI decomposition over time">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-hairline px-4 py-3.5 sm:px-5">
        <div className="max-w-xl">
          <h2 className="text-sm font-semibold text-ink">Where the inflation came from</h2>
          <p className="mt-0.5 text-xs leading-relaxed text-muted">{active.blurb}</p>
        </div>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Decomposition mode">
          {MODES.map((entry) => (
            <button
              key={entry.id}
              type="button"
              aria-pressed={mode === entry.id}
              onClick={() => setMode(entry.id)}
              className={`chip ${mode === entry.id ? 'chip-on' : ''}`}
            >
              {entry.label}
            </button>
          ))}
        </div>
      </header>

      <div className="h-[300px] px-1 py-4 sm:h-[340px] sm:px-2">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} syncId="uk-macro" margin={{ top: 8, right: 24, bottom: 4, left: 4 }}>
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
              tickFormatter={(value) => (mode === 'index' ? value : `${value}${active.unit === 'pp' ? '' : '%'}`)}
              tickLine={false}
              axisLine={false}
              width={46}
            />
            <ReferenceLine y={mode === 'index' ? 100 : 0} stroke={CHROME.axis} strokeWidth={1} />

            <Tooltip
              cursor={{ stroke: '#4A5468', strokeWidth: 1, strokeDasharray: '3 3' }}
              isAnimationActive={false}
              content={<ComponentTooltip mode={mode} />}
            />

            {mode === 'contribution'
              ? plotted.map((series) => (
                <Area
                  key={series.id}
                  type="monotone"
                  dataKey={series.id}
                  name={series.label}
                  stackId="cpi"
                  fill={series.color}
                  fillOpacity={0.92}
                  // Surface-coloured hairline keeps a visible gap between bands.
                  stroke={CHROME.surface}
                  strokeWidth={1.5}
                  isAnimationActive={false}
                />
              ))
              : plotted.map((series) => (
                <Line
                  key={series.id}
                  type="monotone"
                  dataKey={series.id}
                  name={series.label}
                  stroke={series.color}
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                />
              ))}

            {mode === 'contribution' && (
              <Line
                type="monotone"
                dataKey="headline_cpi"
                name="Headline CPI"
                stroke={PALETTE.headline}
                strokeWidth={2}
                strokeDasharray="5 3"
                dot={false}
                isAnimationActive={false}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <footer className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-hairline px-4 py-3 sm:px-5">
        {plotted.map((series) => (
          <span key={series.id} className="flex items-center gap-1.5 text-[11px] text-muted">
            <span
              className="h-2 w-2 rounded-sm"
              style={{ backgroundColor: series.color }}
              aria-hidden="true"
            />
            {series.label}
          </span>
        ))}
        {mode === 'contribution' && (
          <span className="flex items-center gap-1.5 text-[11px] text-muted">
            <span className="h-0.5 w-4" style={{ backgroundColor: PALETTE.headline }} aria-hidden="true" />
            Headline CPI
          </span>
        )}
      </footer>
    </section>
  )
}
