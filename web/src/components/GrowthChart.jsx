import {
  Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import { CHROME, PALETTE } from '../lib/series.js'
import { axisTick, monthLong, pct } from '../lib/format.js'

const WAGE_COLOR = PALETTE.core     // matches wage_growth's colour in BOE_INDICATORS
const GDP_COLOR = PALETTE.goods
const SERVICES_COLOR = PALETTE.services

const SERIES = [
  { id: 'wage_growth', label: 'Wage growth (AWE, 3m YoY)', color: WAGE_COLOR, kind: 'bar' },
  { id: 'gdp_growth', label: 'GDP growth (monthly GVA, YoY)', color: GDP_COLOR, kind: 'bar' },
  { id: 'services_cpi', label: 'Services CPI (YoY)', color: SERVICES_COLOR, kind: 'line' },
]

function GrowthTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const row = payload[0]?.payload
  if (!row) return null

  return (
    <div className="pointer-events-none w-[240px] rounded-lg border border-hairline bg-[#10131A]/95 p-3 shadow-2xl backdrop-blur">
      <div className="num text-xs font-semibold text-ink">{monthLong(label)}</div>
      <div className="mt-2 space-y-1.5">
        {SERIES.map((series) => {
          const value = row[series.id]
          if (value === null || value === undefined) return null
          return (
            <div key={series.id} className="flex items-center gap-2 text-xs">
              <span
                className={series.kind === 'bar' ? 'h-2 w-2 shrink-0 rounded-sm' : 'h-0.5 w-3 shrink-0'}
                style={{ backgroundColor: series.color }}
                aria-hidden="true"
              />
              <span className="flex-1 truncate text-muted">{series.label}</span>
              <span className="num font-medium text-ink">{pct(value)}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/**
 * Wage growth and GDP growth as monthly bars, with services CPI overlaid as
 * a line — three annualised growth rates read together: pay growth and
 * output growth are the two real-economy inputs the MPC weighs against
 * services inflation, the closest read on domestically generated price
 * pressure. All three are year-on-year percentages, so they share one axis.
 */
export default function GrowthChart({ data }) {
  return (
    <section className="card" aria-label="Wage growth, GDP growth and services inflation">
      <header className="border-b border-hairline px-4 py-3.5 sm:px-5">
        <h2 className="text-sm font-semibold text-ink">Pay, output and services inflation</h2>
        <p className="mt-0.5 max-w-3xl text-xs leading-relaxed text-muted">
          Wage growth and GDP growth, annual rate, each month — the two real-economy
          inputs to the MPC's reaction function — against services CPI, the closest
          read on whether domestic price pressure is keeping pace with them.
        </p>
      </header>

      <div className="h-[320px] px-1 py-4 sm:px-2">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} syncId="uk-macro" margin={{ top: 10, right: 24, bottom: 4, left: 4 }}>
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
            <ReferenceLine y={0} stroke={CHROME.axis} strokeWidth={1} />

            <Tooltip
              cursor={{ fill: 'rgba(255,255,255,0.03)' }}
              isAnimationActive={false}
              content={<GrowthTooltip />}
            />

            <Bar
              dataKey="wage_growth"
              name="Wage growth (AWE, 3m YoY)"
              fill={WAGE_COLOR}
              fillOpacity={0.85}
              radius={[2, 2, 0, 0]}
              isAnimationActive={false}
            />
            <Bar
              dataKey="gdp_growth"
              name="GDP growth (monthly GVA, YoY)"
              fill={GDP_COLOR}
              fillOpacity={0.85}
              radius={[2, 2, 0, 0]}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="services_cpi"
              name="Services CPI (YoY)"
              stroke={SERVICES_COLOR}
              strokeWidth={2.25}
              dot={false}
              activeDot={{ r: 4.5, strokeWidth: 2, stroke: CHROME.surface }}
              connectNulls
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <footer className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-hairline px-4 py-3 sm:px-5">
        {SERIES.map((series) => (
          <span key={series.id} className="flex items-center gap-1.5 text-[11px] text-muted">
            <span
              className={series.kind === 'bar' ? 'h-2 w-2 rounded-sm' : 'h-0.5 w-4 rounded'}
              style={{ backgroundColor: series.color }}
              aria-hidden="true"
            />
            {series.label}
          </span>
        ))}
        <span className="ml-auto text-[11px] text-faint">
          GDP is the ONS monthly estimate (output-side GVA); wage growth is Average Weekly
          Earnings, both released with a longer lag than CPI.
        </span>
      </footer>
    </section>
  )
}
