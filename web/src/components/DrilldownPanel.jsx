import { useEffect, useState } from 'react'
import { HIERARCHY } from '../lib/series.js'
import { deltaArrow, deltaTone, monthLong, pct, pp, weightPct } from '../lib/format.js'

const LEAVES = ['services', 'core_goods', 'food', 'energy', 'alcohol_tobacco']

const AGGREGATES = {
  core: ['services', 'core_goods'],
  non_core: ['food', 'energy', 'alcohol_tobacco', 'other'],
}

function sumOf(source, keys) {
  let total = 0
  let seen = false
  for (const key of keys) {
    const value = source?.[key]
    if (value === null || value === undefined) continue
    total += value
    seen = true
  }
  return seen ? total : null
}

/** Contribution to the headline rate, in percentage points. */
function contributionFor(node, row) {
  if (node.id === 'headline') return row.headline_cpi
  if (LEAVES.includes(node.id)) return row.contributions?.[node.id] ?? null
  if (AGGREGATES[node.id]) return sumOf(row.contributions, AGGREGATES[node.id])
  return null
}

/** Share of the CPI basket, stored per 1000. */
function weightFor(node, row) {
  if (node.id === 'headline') return 1000
  if (LEAVES.includes(node.id)) return row.weights?.[node.id] ?? null
  if (AGGREGATES[node.id]) {
    return sumOf(row.weights, AGGREGATES[node.id].filter((key) => key !== 'other'))
  }
  return null
}

function Metric({ label, value, tone }) {
  return (
    <div className="min-w-[64px]">
      <div className="text-[9px] uppercase tracking-[0.1em] text-faint">{label}</div>
      <div className={`num mt-0.5 text-xs font-medium ${tone ?? 'text-ink'}`}>{value}</div>
    </div>
  )
}

function TreeNode({ node, row, yearAgo, depth, openIds, onToggle }) {
  const hasChildren = Boolean(node.children?.length)
  const open = openIds.includes(node.id)

  const rate = node.rate ? row[node.rate] ?? null : null
  const contribution = contributionFor(node, row)
  const weight = weightFor(node, row)
  const monthly = node.rate ? row.mom?.[node.rate] ?? null : null
  const annual = node.rate && yearAgo && rate !== null && yearAgo[node.rate] !== null
    && yearAgo[node.rate] !== undefined
    ? rate - yearAgo[node.rate]
    : null

  return (
    <li>
      <div
        className="rounded-lg border border-hairline bg-raised/60 p-3 transition-colors hover:border-white/15"
        style={{ marginLeft: depth * 14 }}
      >
        <div className="flex items-start gap-2.5">
          <span
            className="mt-1 h-3 w-1 shrink-0 rounded-full"
            style={{ backgroundColor: node.color }}
            aria-hidden="true"
          />

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              {hasChildren ? (
                <button
                  type="button"
                  onClick={() => onToggle(node.id)}
                  aria-expanded={open}
                  className="flex items-center gap-1.5 text-sm font-semibold text-ink hover:text-white"
                >
                  <span
                    className="text-[10px] text-faint transition-transform"
                    style={{ transform: open ? 'rotate(90deg)' : 'none' }}
                    aria-hidden="true"
                  >
                    ▶
                  </span>
                  {node.label}
                </button>
              ) : (
                <span className="pl-[18px] text-sm font-semibold text-ink">{node.label}</span>
              )}

              <span className="num ml-auto text-base font-semibold text-ink">
                {rate === null ? '—' : pct(rate)}
              </span>
            </div>

            {node.note && (
              <p className="mt-1 pl-[18px] text-[11px] leading-relaxed text-faint">{node.note}</p>
            )}

            <div className="mt-2.5 flex flex-wrap gap-x-5 gap-y-2 pl-[18px]">
              <Metric label="Contribution" value={contribution === null ? '—' : pp(contribution)} />
              <Metric label="Basket weight" value={weightPct(weight)} />
              <Metric
                label="1m change"
                value={`${deltaArrow(monthly)} ${pp(monthly)}`}
                tone={deltaTone(monthly)}
              />
              <Metric
                label="12m change"
                value={`${deltaArrow(annual)} ${pp(annual)}`}
                tone={deltaTone(annual)}
              />
            </div>
          </div>
        </div>
      </div>

      {hasChildren && open && (
        <ul className="mt-2 space-y-2">
          {node.children.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              row={row}
              yearAgo={yearAgo}
              depth={depth + 1}
              openIds={openIds}
              onToggle={onToggle}
            />
          ))}
        </ul>
      )}
    </li>
  )
}

export default function DrilldownPanel({ row, yearAgo, onClose }) {
  const [openIds, setOpenIds] = useState(['headline', 'core', 'non_core'])

  useEffect(() => {
    function onKey(event) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  if (!row) return null

  function toggle(id) {
    setOpenIds((current) => (current.includes(id)
      ? current.filter((entry) => entry !== id)
      : [...current, id]))
  }

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/55 backdrop-blur-[2px]"
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Headline CPI breakdown"
        className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[520px] animate-slide-in flex-col border-l border-hairline bg-panel shadow-2xl"
      >
        <header className="flex items-start justify-between gap-3 border-b border-hairline px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-ink">Headline CPI breakdown</h2>
            <p className="num mt-0.5 text-xs text-muted">{monthLong(row.date)}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-hairline px-2.5 py-1 text-xs text-muted transition-colors hover:border-white/25 hover:text-ink"
          >
            Close
          </button>
        </header>

        <div className="scroll-thin flex-1 overflow-y-auto px-5 py-4">
          <p className="mb-4 text-xs leading-relaxed text-muted">
            Headline CPI is the weighted sum of everything below. Contributions add
            up to the headline rate; the components&apos; own rates do not. Core is
            the part the Bank can influence; non-core is mostly imported.
          </p>

          <ul className="space-y-2">
            <TreeNode
              node={HIERARCHY}
              row={row}
              yearAgo={yearAgo}
              depth={0}
              openIds={openIds}
              onToggle={toggle}
            />
          </ul>

          <div className="mt-5 rounded-lg border border-hairline bg-raised/50 p-3">
            <div className="label-xs">Residual</div>
            <p className="mt-1.5 text-[11px] leading-relaxed text-faint">
              A small &quot;other&quot; residual of{' '}
              <span className="num text-muted">{pp(row.contributions?.other)}</span>{' '}
              reconciles the modelled components to published headline CPI. It absorbs
              rounding, unallocated basket items, and the approximation in the implied
              services weight.
            </p>
          </div>
        </div>
      </aside>
    </>
  )
}
