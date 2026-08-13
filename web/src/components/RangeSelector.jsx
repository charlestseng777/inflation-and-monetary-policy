import { Area, AreaChart, Brush, ResponsiveContainer, YAxis } from 'recharts'
import { PALETTE } from '../lib/series.js'
import { monthShort } from '../lib/format.js'

const PRESETS = [
  { id: 'hiking', label: 'Hiking cycle', from: '2021-01' },
  { id: '5y', label: '5Y', months: 60 },
  { id: '3y', label: '3Y', months: 36 },
  { id: '1y', label: '1Y', months: 12 },
  { id: 'all', label: 'All', from: null },
]

export default function RangeSelector({ observations, range, onChange }) {
  const last = observations.length - 1

  function applyPreset(preset) {
    if (preset.months) {
      onChange([Math.max(0, last - preset.months + 1), last])
      return
    }
    if (preset.from) {
      const start = observations.findIndex((row) => row.date >= preset.from)
      onChange([start < 0 ? 0 : start, last])
      return
    }
    onChange([0, last])
  }

  function isActive(preset) {
    if (range[1] !== last) return false
    if (preset.months) return range[0] === Math.max(0, last - preset.months + 1)
    if (preset.from) {
      const start = observations.findIndex((row) => row.date >= preset.from)
      return range[0] === (start < 0 ? 0 : start)
    }
    return range[0] === 0
  }

  return (
    <div className="card card-pad">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="label-xs">Date range</div>
          <div className="num mt-1 text-sm text-ink">
            {monthShort(observations[range[0]]?.date)}
            <span className="mx-2 text-faint">→</span>
            {monthShort(observations[range[1]]?.date)}
            <span className="ml-2 text-xs text-faint">
              ({range[1] - range[0] + 1} months)
            </span>
          </div>
        </div>

        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Date range presets">
          {PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              onClick={() => applyPreset(preset)}
              aria-pressed={isActive(preset)}
              className={`chip ${isActive(preset) ? 'chip-on' : ''}`}
            >
              {preset.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-3 h-[64px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={observations} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
            <defs>
              <linearGradient id="rangeFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={PALETTE.headline} stopOpacity={0.35} />
                <stop offset="100%" stopColor={PALETTE.headline} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <YAxis hide domain={['dataMin', 'dataMax']} />
            <Area
              type="monotone"
              dataKey="headline_cpi"
              stroke={PALETTE.headline}
              strokeWidth={1.5}
              fill="url(#rangeFill)"
              isAnimationActive={false}
            />
            <Brush
              dataKey="date"
              height={18}
              travellerWidth={8}
              startIndex={range[0]}
              endIndex={range[1]}
              stroke="#2E3545"
              fill="rgba(15,17,22,0.55)"
              tickFormatter={monthShort}
              onChange={(next) => {
                if (
                  typeof next?.startIndex === 'number' &&
                  typeof next?.endIndex === 'number' &&
                  next.endIndex > next.startIndex
                ) {
                  onChange([next.startIndex, next.endIndex])
                }
              }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <p className="mt-2 text-[11px] leading-relaxed text-faint">
        Drag the handles to zoom. Every chart on the page shares this window and a
        synchronised crosshair.
      </p>
    </div>
  )
}
