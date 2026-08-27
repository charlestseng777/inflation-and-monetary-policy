import { Brush, ComposedChart, ResponsiveContainer } from 'recharts'
import { monthShort } from '../lib/format.js'

const PRESETS = [
  { id: 'hiking', label: 'Hiking cycle', from: '2021-01' },
  { id: '5y', label: '5Y', months: 60 },
  { id: '3y', label: '3Y', months: 36 },
  { id: '1y', label: '1Y', months: 12 },
  { id: 'ytd', label: 'YTD', ytd: true },
  { id: 'all', label: 'All', from: null },
]

/**
 * The date-range brush shared by every chart on a tab. Embedded directly
 * inside whichever card holds the tab's main chart rather than living in a
 * box of its own, since a full-width card just for a 64px brush was mostly
 * empty space. No area/line is plotted behind the brush — it's a scrollbar,
 * not a chart, and a second rendering of headline CPI here just duplicated
 * the chart above it.
 */
export default function RangeSlider({ observations, range, onChange }) {
  const last = observations.length - 1

  // YTD's start isn't a fixed literal like the other presets — it's January
  // of whatever year the latest observation falls in.
  function presetStart(preset) {
    if (preset.ytd) {
      const year = observations[last]?.date?.slice(0, 4)
      return year ? `${year}-01` : null
    }
    return preset.from
  }

  function applyPreset(preset) {
    if (preset.months) {
      onChange([Math.max(0, last - preset.months + 1), last])
      return
    }
    const from = presetStart(preset)
    if (from) {
      const start = observations.findIndex((row) => row.date >= from)
      onChange([start < 0 ? 0 : start, last])
      return
    }
    onChange([0, last])
  }

  function isActive(preset) {
    if (range[1] !== last) return false
    if (preset.months) return range[0] === Math.max(0, last - preset.months + 1)
    const from = presetStart(preset)
    if (from) {
      const start = observations.findIndex((row) => row.date >= from)
      return range[0] === (start < 0 ? 0 : start)
    }
    return range[0] === 0
  }

  return (
    <div className="border-b border-hairline px-4 py-3.5 sm:px-5">
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

      <div className="mt-3 h-[26px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={observations} margin={{ top: 0, right: 4, bottom: 0, left: 4 }}>
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
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <p className="mt-2 text-[11px] leading-relaxed text-faint">
        Drag the handles to zoom. Every chart on the page shares this window and a
        synchronised crosshair.
      </p>
    </div>
  )
}
