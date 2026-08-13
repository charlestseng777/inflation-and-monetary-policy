import { useMemo, useState } from 'react'
import { useData } from './lib/useData.js'
import { addMonths, monthLong } from './lib/format.js'
import RangeSelector from './components/RangeSelector.jsx'
import StatCards, { LatestSummary } from './components/StatCards.jsx'
import InsightPanel from './components/InsightPanel.jsx'
import MainChart from './components/MainChart.jsx'
import StackedChart from './components/StackedChart.jsx'
import BoEWatch from './components/BoEWatch.jsx'
import RatesView from './components/RatesView.jsx'
import DrilldownPanel from './components/DrilldownPanel.jsx'

const DEFAULT_START = '2021-01'

const TABS = [
  { id: 'overview', label: 'Inflation & policy' },
  { id: 'rates', label: 'Inflation vs rates' },
]

function Shell({ children }) {
  return (
    <div className="min-h-screen bg-canvas">
      <div className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8">{children}</div>
    </div>
  )
}

export default function App() {
  const state = useData()
  const [tab, setTab] = useState('overview')
  const [enabled, setEnabled] = useState(['core_cpi', 'services_cpi'])
  const [hoveredMonth, setHoveredMonth] = useState(null)
  const [selectedMonth, setSelectedMonth] = useState(null)
  const [range, setRange] = useState(null)

  const observations = state.observations ?? []

  const effectiveRange = useMemo(() => {
    if (range) return range
    if (!observations.length) return [0, 0]
    const start = observations.findIndex((row) => row.date >= DEFAULT_START)
    return [start < 0 ? 0 : start, observations.length - 1]
  }, [range, observations])

  const view = useMemo(
    () => observations.slice(effectiveRange[0], effectiveRange[1] + 1),
    [observations, effectiveRange],
  )

  const latest = observations[observations.length - 1] ?? null

  const focusIndex = useMemo(() => {
    const target = hoveredMonth ?? selectedMonth
    if (target) {
      const found = observations.findIndex((row) => row.date === target)
      if (found >= 0) return found
    }
    return effectiveRange[1]
  }, [hoveredMonth, selectedMonth, observations, effectiveRange])

  const selectedRow = selectedMonth
    ? observations.find((row) => row.date === selectedMonth) ?? null
    : null
  const selectedYearAgo = selectedMonth
    ? observations.find((row) => row.date === addMonths(selectedMonth, -12)) ?? null
    : null

  if (state.status === 'loading') {
    return (
      <Shell>
        <div className="flex h-[60vh] items-center justify-center">
          <div className="text-sm text-muted">Loading ONS and Bank of England data…</div>
        </div>
      </Shell>
    )
  }

  if (state.status === 'error') {
    return (
      <Shell>
        <div className="card card-pad mx-auto mt-16 max-w-lg">
          <h1 className="text-sm font-semibold text-ink">Could not load the data</h1>
          <p className="mt-2 text-xs leading-relaxed text-muted">{state.error}</p>
          <p className="mt-3 text-xs leading-relaxed text-faint">
            Run the fetcher, then restart the dev server:
          </p>
          <pre className="mt-2 overflow-x-auto rounded-md border border-hairline bg-canvas p-3 text-[11px] text-muted">
python fetcher/fetch.py --no-llm{'\n'}npm --prefix web run dev
          </pre>
        </div>
      </Shell>
    )
  }

  function toggleSeries(id) {
    setEnabled((current) => (current.includes(id)
      ? current.filter((entry) => entry !== id)
      : [...current, id]))
  }

  return (
    <Shell>
      <header className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-ink sm:text-xl">
            UK Inflation &amp; Monetary Policy
          </h1>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-muted">
            How inflation evolved and how the Bank of England responded. Start with
            headline CPI against Bank Rate, then click into any month to see what the
            number was actually made of.
          </p>
          <div className="mt-2">
            <LatestSummary row={latest} wage={latest?.wage_growth} realRate={latest?.real_rate} />
          </div>
        </div>

        <div className="flex flex-col items-end gap-2">
          <nav className="flex gap-1.5" aria-label="Views">
            {TABS.map((entry) => (
              <button
                key={entry.id}
                type="button"
                aria-current={tab === entry.id ? 'page' : undefined}
                onClick={() => setTab(entry.id)}
                className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                  tab === entry.id
                    ? 'border-white/25 bg-white/[0.07] text-ink'
                    : 'border-hairline text-muted hover:border-white/20 hover:text-ink'
                }`}
              >
                {entry.label}
              </button>
            ))}
          </nav>
          {state.generatedAt && (
            <span className="text-[10px] text-faint">
              Data refreshed {new Date(state.generatedAt).toISOString().slice(0, 16).replace('T', ' ')} UTC
            </span>
          )}
        </div>
      </header>

      <div className="space-y-4">
        <StatCards row={latest} />

        <RangeSelector
          observations={observations}
          range={effectiveRange}
          onChange={setRange}
        />

        <InsightPanel
          observations={observations}
          focusIndex={focusIndex}
          events={state.events}
          commentary={state.commentary}
          flag={state.meta?.reaction_function_flag}
        />

        {tab === 'overview' ? (
          <>
            <MainChart
              data={view}
              events={state.events}
              enabled={enabled}
              onToggle={toggleSeries}
              onHoverMonth={setHoveredMonth}
              onSelectMonth={setSelectedMonth}
              selectedMonth={selectedMonth}
            />
            <StackedChart data={view} />
            <BoEWatch row={observations[focusIndex] ?? latest} />
          </>
        ) : (
          <RatesView data={view} onHoverMonth={setHoveredMonth} />
        )}

        <footer className="card card-pad text-[11px] leading-relaxed text-faint">
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            <span>
              Sources:{' '}
              <a
                className="text-muted underline decoration-hairline underline-offset-2 hover:text-ink"
                href="https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/consumerpriceindices"
                target="_blank"
                rel="noreferrer"
              >
                ONS MM23
              </a>{' '}
              (CPI) ·{' '}
              <a
                className="text-muted underline decoration-hairline underline-offset-2 hover:text-ink"
                href="https://www.bankofengland.co.uk/boeapps/database/"
                target="_blank"
                rel="noreferrer"
              >
                Bank of England IADB
              </a>{' '}
              (Bank Rate, series IUDBEDR)
            </span>
            {latest && <span>Latest observation: {monthLong(latest.date)}</span>}
          </div>
          <p className="mt-2 max-w-4xl">
            Contributions are basket weight × component rate; the &quot;other&quot; band is the
            residual against published headline CPI. The services weight is implied each
            month from the goods/services split rather than read from a published series —
            see <code>data/meta.json</code> for the full methodology note. Not investment advice.
          </p>
        </footer>
      </div>

      {selectedRow && (
        <DrilldownPanel
          row={selectedRow}
          yearAgo={selectedYearAgo}
          onClose={() => setSelectedMonth(null)}
        />
      )}
    </Shell>
  )
}
