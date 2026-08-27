/** Latest decision at or before `month` ('YYYY-MM'), falling back to the earliest. */
export function nearestDecision(decisions, month) {
  if (!decisions?.length || !month) return null
  const inMonth = decisions.filter((entry) => entry.month === month)
  if (inMonth.length) return inMonth[inMonth.length - 1]
  const before = decisions.filter((entry) => entry.month < month)
  return before.length ? before[before.length - 1] : decisions[0]
}

export const MPC_ACTION_LABEL = {
  hike: 'Rate rise',
  cut: 'Rate cut',
  hold: 'Held',
  unknown: 'Decision',
}
