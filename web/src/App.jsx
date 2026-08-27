import { useMemo, useState } from 'react'
import { useData } from './lib/useData.js'
import { addMonths, monthLong } from './lib/format.js'
import StatCards, { LatestSummary } from './components/StatCards.jsx'
import { InsightEngineCard } from './components/InsightPanel.jsx'
import MainChart from './components/MainChart.jsx'
import StackedChart from './components/StackedChart.jsx'
import GrowthChart from './components/GrowthChart.jsx'
import BoEWatch from './components/BoEWatch.jsx'
import { MarketPricingChart, RealRateChart } from './components/RatesView.jsx'
import { VoteBreakdownCard, MonetaryPolicySummaryCard } from './components/MpcInsightPanel.jsx'
import SyntheticCurveTable from './components/SyntheticCurveTable.jsx'
import DrilldownPanel from './components/DrilldownPanel.jsx'
import UpcomingReleasesCard from './components/UpcomingReleases.jsx'
import LatestNewsCard from './components/MpcNews.jsx'
import { nearestDecision } from './lib/mpcInsight.js'

const DEFAULT_START = '2021-01'

const TABS = [
  { id: 'overview', label: 'Macro Data' },
  { id: 'rates', label: 'Rates and Monetary Policy' },
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
  // The month the insight/summary cards are focused on — set only by
  // clicking a chart, never by hovering, so the cards stay put while you
  // explore the chart's own tooltips and only move on the next click.
  const [clickedMonth, setClickedMonth] = useState(null)
  // The month the CPI breakdown drilldown is open for — set only by
  // clicking the decomposition chart, independent of the focus above.
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

  // The panel can now carry trailing months with Bank Rate/OIS data but no
  // CPI print yet (the gap between the latest MPC meeting and the next ONS
  // release) — see build_panel in fetcher/fetch.py. Everything on the
  // inflation-focused overview tab is fundamentally about the latest CPI
  // print, so it anchors to the latest row that actually has one rather than
  // the newest row full stop, which the rates tab still uses directly.
  const latest = useMemo(() => {
    for (let i = observations.length - 1; i >= 0; i -= 1) {
      if (observations[i].headline_cpi !== null && observations[i].headline_cpi !== undefined) {
        return observations[i]
      }
    }
    return observations[observations.length - 1] ?? null
  }, [observations])

  const focusIndex = useMemo(() => {
    if (clickedMonth) {
      const found = observations.findIndex((row) => row.date === clickedMonth)
      if (found >= 0) return found
    }
    return effectiveRange[1]
  }, [clickedMonth, observations, effectiveRange])

  function focusOnMonth(month) {
    if (month) setClickedMonth(month)
  }

  // Same idea as `latest`, but tracking the hover/selection instead of
  // defaulting to the end of the range — walks back to the nearest earlier
  // month with a CPI print, so hovering into the CPI-less tail on the
  // overview tab doesn't blank out the insight panel or BoE watch cards.
  const cpiFocusIndex = useMemo(() => {
    for (let i = focusIndex; i >= 0; i -= 1) {
      if (observations[i]?.headline_cpi !== null && observations[i]?.headline_cpi !== undefined) {
        return i
      }
    }
    return focusIndex
  }, [observations, focusIndex])

  const selectedRow = selectedMonth
    ? observations.find((row) => row.date === selectedMonth) ?? null
    : null
  const selectedYearAgo = selectedMonth
    ? observations.find((row) => row.date === addMonths(selectedMonth, -12)) ?? null
    : null

  const focusMonth = observations[focusIndex]?.date ?? null
  const focusDecision = useMemo(
    () => nearestDecision(state.mpcDecisions ?? [], focusMonth),
    [state.mpcDecisions, focusMonth],
  )
  const focusSummary = focusDecision ? state.mpcSummaries?.[focusDecision.month] ?? null : null

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
            How inflation evolved and how the Bank of England responded. Click any
            month on a chart to focus the panel on it, or click the decomposition
            chart below to see what that month's number was actually made of.
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

        {tab === 'overview' ? (
          <>
            <div className="grid gap-3 lg:grid-cols-4">
              <div className="lg:col-span-3">
                <MainChart
                  data={view}
                  events={state.events}
                  enabled={enabled}
                  onToggle={toggleSeries}
                  onSelectMonth={focusOnMonth}
                  selectedMonth={selectedMonth}
                  observations={observations}
                  range={effectiveRange}
                  onRangeChange={setRange}
                />
              </div>
              {/* Two boxes need to split the chart's height exactly at desktop
                  widths, but CSS can't size an auto grid row from one column
                  while letting a taller-content sibling compress to fit it —
                  an auto row always grows to the tallest natural content.
                  Taking this column out of flow at lg+ (absolute, inset-0
                  inside a relatively positioned cell with no content of its
                  own) means it contributes nothing to the row's height, so
                  the row is sized by the chart alone and this column just
                  fills whatever that turns out to be. Below lg the grid drops
                  to one column per row, so this stays in normal flow and each
                  card just takes its natural height stacked under the chart. */}
              <div className="lg:relative lg:col-span-1">
                <div className="flex min-h-0 flex-col gap-3 lg:absolute lg:inset-0">
                  <InsightEngineCard
                    observations={observations}
                    focusIndex={cpiFocusIndex}
                    events={state.events}
                    className="flex-1 min-h-0"
                  />
                  <UpcomingReleasesCard releases={state.upcomingReleases} className="flex-1 min-h-0" />
                </div>
              </div>
            </div>
            <StackedChart
              data={view}
              onSelectMonth={(month) => {
                focusOnMonth(month)
                // Months with Bank Rate data but no CPI yet have nothing for
                // the drilldown to show — ignore clicks there rather than
                // open an empty panel.
                const row = observations.find((entry) => entry.date === month)
                if (row?.headline_cpi !== null && row?.headline_cpi !== undefined) {
                  setSelectedMonth(month)
                }
              }}
            />
            <GrowthChart data={view} />
            <BoEWatch row={observations[cpiFocusIndex] ?? latest} />
          </>
        ) : (
          <>
            <div className="grid gap-3 lg:grid-cols-4">
              <div className="lg:col-span-3">
                <MarketPricingChart
                  data={view}
                  decisions={state.mpcDecisions}
                  focusMonth={focusMonth}
                  onSelectMonth={focusOnMonth}
                  observations={observations}
                  range={effectiveRange}
                  onRangeChange={setRange}
                />
              </div>
              <div className="lg:relative lg:col-span-1">
                <div className="flex min-h-0 flex-col gap-3 lg:absolute lg:inset-0">
                  <VoteBreakdownCard decision={focusDecision} className="flex-1 min-h-0" />
                  <LatestNewsCard news={state.mpcNews} className="flex-1 min-h-0" />
                </div>
              </div>
            </div>
            <MonetaryPolicySummaryCard decision={focusDecision} summary={focusSummary} />
            <RealRateChart data={view} />
            <SyntheticCurveTable curve={state.syntheticCurve} />
          </>
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
