// Deterministic "insight engine".
//
// This runs client-side on every hover, so it has to be instant and it has to be
// honest — it only ever restates arithmetic that is already in the data. The
// LLM-written notes in commentary.json are a separate, slower layer that covers
// the latest release; this covers every month in the series.

import { monthLong, pct, pp } from './format.js'

const COMPONENT_LABELS = {
  services: 'services',
  core_goods: 'core goods',
  food: 'food',
  energy: 'energy',
  alcohol_tobacco: 'alcohol and tobacco',
  other: 'other components',
}

function describeMove(value, { rose, fell, flat }) {
  if (value === null || value === undefined) return null
  if (Math.abs(value) < 0.05) return flat
  return value > 0 ? rose : fell
}

/** Largest mover among the contribution components, month on month. */
function primaryDriver(row, previous) {
  if (!previous?.contributions || !row?.contributions) return null
  let best = null
  for (const [key, value] of Object.entries(row.contributions)) {
    const before = previous.contributions[key]
    if (value === null || before === null || value === undefined || before === undefined) continue
    const delta = value - before
    if (!best || Math.abs(delta) > Math.abs(best.delta)) {
      best = { key, delta, value }
    }
  }
  if (!best || Math.abs(best.delta) < 0.05) return null
  return best
}

/** How many consecutive months Bank Rate has been unchanged, ending at index. */
function holdStreak(observations, index) {
  const current = observations[index]?.policy_rate
  if (current === null || current === undefined) return 0
  let streak = 0
  for (let i = index - 1; i >= 0; i -= 1) {
    const prior = observations[i].policy_rate
    if (prior === null || prior === undefined) break
    if (Math.abs(prior - current) > 1e-9) break
    streak += 1
  }
  return streak
}

/**
 * Build an institutional-style paragraph for one observation.
 * Returns { text, stance, driver } — stance drives the badge colour.
 */
export function buildInsight(observations, index, events = []) {
  const row = observations[index]
  if (!row) return null
  const previous = index > 0 ? observations[index - 1] : null

  const parts = []

  // 1. What headline did, and by how much.
  const headlineMove = row.mom?.headline_cpi
  if (previous && headlineMove !== null && headlineMove !== undefined) {
    const verb = describeMove(headlineMove, {
      rose: 'rose', fell: 'declined', flat: 'was broadly unchanged at',
    })
    if (verb === 'was broadly unchanged at') {
      parts.push(`Headline inflation was broadly unchanged at ${pct(row.headline_cpi)}`)
    } else {
      parts.push(
        `Headline inflation ${verb} from ${pct(previous.headline_cpi)} to ${pct(row.headline_cpi)}`,
      )
    }
  } else {
    parts.push(`Headline inflation stood at ${pct(row.headline_cpi)}`)
  }

  // 2. What drove it.
  const driver = primaryDriver(row, previous)
  if (driver) {
    const label = COMPONENT_LABELS[driver.key] ?? driver.key
    const direction = driver.delta > 0 ? 'a larger contribution from' : 'a smaller contribution from'
    parts.push(
      `driven primarily by ${direction} ${label} (${pp(driver.delta)} on the month, ` +
      `to ${pp(driver.value)} of the headline rate)`,
    )
  }

  const opening = `${parts.join(', ')}.`
  const sentences = [opening]

  // 3. The persistence question — services is the MPC's read on domestic inflation.
  if (row.services_cpi !== null && row.services_cpi !== undefined) {
    const servicesMove = row.mom?.services_cpi
    let servicesLine
    if (row.services_cpi >= 4.5) {
      servicesLine = `Services inflation remained elevated at ${pct(row.services_cpi)}`
    } else if (row.services_cpi >= 3) {
      servicesLine = `Services inflation held at ${pct(row.services_cpi)}`
    } else {
      servicesLine = `Services inflation was subdued at ${pct(row.services_cpi)}`
    }
    if (servicesMove !== null && servicesMove !== undefined && Math.abs(servicesMove) >= 0.1) {
      servicesLine += ` (${pp(servicesMove)} on the month)`
    }
    const gap = row.services_cpi - (row.headline_cpi ?? 0)
    if (gap >= 1.5) {
      servicesLine += ', well above the headline rate and pointing to persistent domestic price pressure'
    } else if (gap <= -1.5) {
      servicesLine += ', below the headline rate, consistent with an externally driven episode'
    }
    sentences.push(`${servicesLine}.`)
  }

  // 4. The policy read.
  const rate = row.policy_rate
  const real = row.real_rate
  let stance = 'unclear'
  if (rate !== null && rate !== undefined && real !== null && real !== undefined) {
    const rateMove = row.mom?.policy_rate
    const streak = holdStreak(observations, index)
    let policyLine

    if (rateMove !== null && rateMove !== undefined && Math.abs(rateMove) > 1e-9) {
      const action = rateMove > 0 ? 'raised' : 'lowered'
      policyLine = `The MPC ${action} Bank Rate by ${pp(Math.abs(rateMove))} to ${pct(rate, 2)}`
    } else if (streak >= 2) {
      policyLine = `Bank Rate was held at ${pct(rate, 2)} for a ${ordinal(streak + 1)} consecutive month`
    } else {
      policyLine = `Bank Rate stood at ${pct(rate, 2)}`
    }

    if (real >= 1) {
      stance = 'restrictive'
      policyLine += `, leaving the real policy rate at ${pp(real)} — restrictive territory`
    } else if (real >= 0) {
      stance = 'neutral'
      policyLine += `, with the real policy rate only marginally positive at ${pp(real)}`
    } else {
      stance = 'accommodative'
      policyLine += `, leaving the real policy rate at ${pp(real)} — still below zero in real terms`
    }
    sentences.push(`${policyLine}.`)
  }

  // 5. The tension, when there is one.
  if (row.services_cpi >= 4.5 && row.headline_cpi <= 3 && rate !== null) {
    sentences.push(
      'With headline back near target but services still running hot, the case for holding ' +
      'rests on domestic persistence rather than on the headline print.',
    )
  } else if (row.headline_cpi >= 5 && real !== null && real < 0) {
    sentences.push(
      'Policy remained loose in real terms against a headline rate far above target — the ' +
      'configuration that preceded the sharpest part of the tightening cycle.',
    )
  }

  // 6. Context, if something happened this month.
  const event = events.find((e) => e.date === row.date)
  if (event) {
    sentences.push(`Context: ${event.label}. ${event.description}`)
  }

  return {
    text: sentences.join(' '),
    stance,
    driver: driver ? (COMPONENT_LABELS[driver.key] ?? driver.key) : null,
    month: monthLong(row.date),
  }
}

function ordinal(n) {
  const suffixes = ['th', 'st', 'nd', 'rd']
  const value = n % 100
  return `${n}${suffixes[(value - 20) % 10] ?? suffixes[value] ?? suffixes[0]}`
}

export const STANCE_STYLES = {
  restrictive: { label: 'Restrictive', className: 'border-[#d95926]/40 bg-[#d95926]/10 text-[#f0a07c]' },
  neutral: { label: 'Neutral', className: 'border-[#8A93A6]/40 bg-white/[0.05] text-[#b6bdcc]' },
  accommodative: { label: 'Accommodative', className: 'border-[#3987e5]/40 bg-[#3987e5]/10 text-[#8fbdf2]' },
  unclear: { label: 'Unclear', className: 'border-hairline bg-white/[0.03] text-muted' },
}
