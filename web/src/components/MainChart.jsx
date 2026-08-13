import { useMemo, useState } from 'react'
import {
  CartesianGrid, ComposedChart, Label, LabelList, Line, ReferenceArea,
  ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { CHROME, MAIN_SERIES } from '../lib/series.js'
import { axisTick, monthLong, pct } from '../lib/format.js'
import ChartTooltip from './ChartTooltip.jsx'

const SYNC_ID = 'uk-macro'

const EVENT_TONE = {
  policy: '#d95926',
  shock: '#e66767',
  fiscal: '#c98500',
  political: '#9085e9',
  milestone: '#3987e5',
}

/** Direct end-of-line label, drawn only on the final point of the series. */
function endLabel(color, text, lastIndex) {
  return function EndLabel(props) {
    const { x, y, index } = props
    if (index !== lastIndex || x === undefined || y === undefined) return null
    return (
      <text
        x={x + 8}
        y={y}
        dy={4}
        fill={color}
        fontSize={11}
        fontWeight={600}
        style={{ pointerEvents: 'none' }}
      >
        {text}
      </text>
    )
  }
}

export default function MainChart({
  data, events, enabled, onToggle, onHoverMonth, onSelectMonth, selectedMonth,
}) {
  const [hoveredEvent, setHoveredEvent] = useState(null)

  const visible = useMemo(
    () => MAIN_SERIES.filter((series) => series.locked || enabled.includes(series.id)),
    [enabled],
  )

  const colors = useMemo(
    () => Object.fromEntries(MAIN_SERIES.map((series) => [series.id, series.color])),
    [],
  )

  const from = data[0]?.date
  const to = data[data.length - 1]?.date

  // Point markers, plus any shaded spans whose window overlaps the current view.
  const pointEvents = useMemo(
    () => events.filter((event) => event.date >= from && event.date <= to),
    [events, from, to],
  )
  const spanEvents = useMemo(
    () => events.filter((event) => event.spanLabel && event.date <= to
      && (event.spanEnd === null || event.spanEnd === undefined || event.spanEnd >= from)),
    [events, from, to],
  )

  const lastIndex = data.length - 1
  const showEndLabels = visible.length <= 4

  return (
    <section className="card" aria-label="Inflation and Bank Rate">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-hairline px-4 py-3.5 sm:px-5">
        <div>
          <h2 className="text-sm font-semibold text-ink">Inflation and the policy response</h2>
          <p className="mt-0.5 text-xs text-muted">
            Annual CPI inflation against Bank Rate, percent. Click any point on the
            headline line to decompose that month.
          </p>
        </div>

        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Series shown">
          {MAIN_SERIES.map((series) => {
            const on = series.locked || enabled.includes(series.id)
            return (
              <button
                key={series.id}
                type="button"
                disabled={series.locked}
                aria-pressed={on}
                onClick={() => !series.locked && onToggle(series.id)}
                title={series.locked ? `${series.label} is always shown` : `Toggle ${series.label}`}
                className={`chip ${on ? 'chip-on' : ''} ${series.locked ? 'cursor-default opacity-95' : ''}`}
              >
                <span
                  className="h-2 w-2 rounded-sm"
                  style={{ backgroundColor: on ? series.color : '#3A4150' }}
                  aria-hidden="true"
                />
                {series.short}
                {series.locked && <span className="text-[9px] text-faint">·fixed</span>}
              </button>
            )
          })}
        </div>
      </header>

      <div className="h-[380px] px-1 py-4 sm:h-[440px] sm:px-2">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={data}
            syncId={SYNC_ID}
            margin={{ top: 14, right: showEndLabels ? 78 : 24, bottom: 4, left: 4 }}
            onMouseMove={(state) => onHoverMonth?.(state?.activeLabel ?? null)}
            onMouseLeave={() => onHoverMonth?.(null)}
            onClick={(state) => state?.activeLabel && onSelectMonth?.(state.activeLabel)}
          >
            <CartesianGrid stroke={CHROME.grid} strokeDasharray="0" vertical={false} />

            {spanEvents.map((event) => (
              <ReferenceArea
                key={`span-${event.id}`}
                x1={event.date < from ? from : event.date}
                x2={event.spanEnd && event.spanEnd <= to ? event.spanEnd : to}
                fill={EVENT_TONE[event.category] ?? '#8A93A6'}
                fillOpacity={0.05}
                stroke="none"
                ifOverflow="hidden"
              />
            ))}

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

            {/* The 2% target is the reference everything on this chart is read against. */}
            <ReferenceLine y={2} stroke="#4A5468" strokeDasharray="4 4" strokeWidth={1}>
              <Label value="2% target" position="insideBottomLeft" fill="#6C7689" fontSize={10} />
            </ReferenceLine>
            <ReferenceLine y={0} stroke={CHROME.axis} strokeWidth={1} />

            {selectedMonth && (
              <ReferenceLine
                x={selectedMonth}
                stroke="#E8ECF4"
                strokeOpacity={0.35}
                strokeWidth={1}
                ifOverflow="hidden"
              />
            )}

            {pointEvents.map((event) => (
              <ReferenceLine
                key={event.id}
                x={event.date}
                stroke={EVENT_TONE[event.category] ?? '#8A93A6'}
                strokeOpacity={hoveredEvent?.id === event.id ? 0.85 : 0.28}
                strokeDasharray="3 3"
                ifOverflow="hidden"
                label={({ viewBox }) => (
                  <g
                    transform={`translate(${viewBox.x}, ${viewBox.y - 2})`}
                    style={{ cursor: 'pointer' }}
                    onMouseEnter={() => setHoveredEvent(event)}
                    onMouseLeave={() => setHoveredEvent(null)}
                  >
                    <rect x={-11} y={-11} width={22} height={22} fill="transparent" />
                    <circle
                      r={hoveredEvent?.id === event.id ? 5.5 : 4}
                      fill={hoveredEvent?.id === event.id
                        ? (EVENT_TONE[event.category] ?? '#8A93A6')
                        : CHROME.surface}
                      stroke={EVENT_TONE[event.category] ?? '#8A93A6'}
                      strokeWidth={2}
                    />
                  </g>
                )}
              />
            ))}

            <Tooltip
              cursor={{ stroke: '#4A5468', strokeWidth: 1, strokeDasharray: '3 3' }}
              isAnimationActive={false}
              content={
                <ChartTooltip
                  colors={colors}
                  extras={visible.map((series) => ({ id: series.id, label: series.label }))}
                />
              }
            />

            {visible.map((series) => (
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
              >
                {showEndLabels && (
                  <LabelList content={endLabel(series.color, series.short, lastIndex)} />
                )}
              </Line>
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <footer className="border-t border-hairline px-4 py-3 sm:px-5">
        {hoveredEvent ? (
          <div className="animate-fade-up">
            <div className="flex items-center gap-2">
              <span
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: EVENT_TONE[hoveredEvent.category] ?? '#8A93A6' }}
                aria-hidden="true"
              />
              <span className="text-xs font-semibold text-ink">{hoveredEvent.label}</span>
              <span className="num text-[11px] text-faint">{monthLong(hoveredEvent.date)}</span>
            </div>
            <p className="mt-1.5 max-w-3xl text-xs leading-relaxed text-muted">
              {hoveredEvent.description}
            </p>
          </div>
        ) : (
          <p className="text-xs text-faint">
            Hover a marker on the chart for the macro event behind that month
            {pointEvents.length > 0 && ` — ${pointEvents.length} in this window`}.
          </p>
        )}
      </footer>
    </section>
  )
}
