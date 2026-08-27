// Palette and series registry.
//
// Colours come from the validated dark categorical ramp. The SLOT ORDER below is
// load-bearing, not cosmetic: legends, toggle rows and stack order all render in
// this sequence so that every adjacent pair is one the validator cleared.
//
//   validate_palette.py "#3987e5,#d95926,#199e70,#c98500,#d55181,#008300,#9085e9,#e66767" \
//       --mode dark --surface "#161A23" --pairs adjacent   ->  ALL CHECKS PASS
//
// Re-run that check before reordering or adding a hue. Aqua next to magenta, or
// violet next to blue, both fail hard under deuteranopia/protanopia.

export const PALETTE = {
  headline: '#3987e5', // slot 1  blue
  policy: '#d95926',   // slot 2  orange
  services: '#199e70', // slot 3  aqua
  goods: '#c98500',    // slot 4  yellow   (goods aggregate and core goods)
  food: '#d55181',     // slot 5  magenta
  energy: '#008300',   // slot 6  green
  core: '#9085e9',     // slot 7  violet
  alcohol: '#e66767',  // slot 8  red
  other: '#5A6273',    // neutral residual, deliberately not a hue slot
}

export const CHROME = {
  surface: '#161A23',
  grid: '#232733',
  axis: '#2E3545',
  muted: '#8A93A6',
  faint: '#5A6273',
}

// Everything plotted on the main chart, in validated slot order.
// `locked` series cannot be switched off.
export const MAIN_SERIES = [
  { id: 'headline_cpi', label: 'Headline CPI', short: 'Headline', color: PALETTE.headline, width: 2.5, locked: true },
  { id: 'policy_rate', label: 'Bank Rate', short: 'Bank Rate', color: PALETTE.policy, width: 2, locked: true, step: true },
  { id: 'services_cpi', label: 'Services CPI', short: 'Services', color: PALETTE.services, width: 2 },
  { id: 'goods_cpi', label: 'Goods inflation', short: 'Goods', color: PALETTE.goods, width: 2 },
  { id: 'food_cpi', label: 'Food inflation', short: 'Food', color: PALETTE.food, width: 2 },
  { id: 'energy_cpi', label: 'Energy inflation', short: 'Energy', color: PALETTE.energy, width: 2 },
  { id: 'core_cpi', label: 'Core CPI', short: 'Core', color: PALETTE.core, width: 2 },
]

// Bottom-to-top stack order for the decomposition chart. Core components first,
// then non-core — so the chart reads the same way as the hierarchy tree.
export const STACK_SERIES = [
  { id: 'services', label: 'Services', color: PALETTE.services, rate: 'services_cpi', index: 'services' },
  { id: 'core_goods', label: 'Core goods', color: PALETTE.goods, rate: 'core_goods_cpi', index: 'core_goods' },
  { id: 'food', label: 'Food', color: PALETTE.food, rate: 'food_cpi', index: 'food' },
  { id: 'energy', label: 'Energy', color: PALETTE.energy, rate: 'energy_cpi', index: 'energy' },
  { id: 'alcohol_tobacco', label: 'Alcohol & tobacco', color: PALETTE.alcohol, rate: 'alcohol_tobacco_cpi', index: 'alcohol_tobacco' },
  { id: 'other', label: 'Other / rounding', color: PALETTE.other, rate: null, index: null },
]

// Series always shown on the "Inflation vs rates" tab. Rates only,
// deliberately — the inflation lines belong on the overview tab and are not
// repeated here. Both colours are the validated blue/orange pair already used
// together as slots 1-2 elsewhere in the app (see the header note above).
export const RATES_SERIES = [
  { id: 'policy_rate', label: 'Bank Rate (decided)', color: PALETTE.policy, width: 2.5, step: true },
  { id: 'expected_rate', label: 'Synthetic MPC OIS Curve', color: PALETTE.headline, width: 1.75, dashed: true },
]

export const SYNTHETIC_CURVE_DESCRIPTION =
  'Market-implied Bank Rate adjustment for the upcoming MPC meeting, derived ' +
  'from SONIA OIS forward pricing between consecutive MPC dates.'

// Optional context lines, off by default — toggled on from the legend. Reuse
// the aqua/violet slots (3 and 7), already validated adjacent to the blue/
// orange pair above, since nothing else on this page uses them.
export const RATES_CONTEXT_SERIES = [
  { id: 'ois_3m', label: '3M SONIA OIS', color: PALETTE.services, width: 1.5 },
  { id: 'ois_2y', label: '2Y SONIA OIS', color: PALETTE.core, width: 1.5 },
]

// Tone for an MPC decision, reusing the same semantics as the month-on-month
// arrows elsewhere (amber = up, blue = down) so the vocabulary stays one thing
// across the whole app.
export const MPC_ACTION_TONE = {
  hike: '#E9B872',
  cut: '#7FB9E8',
  hold: CHROME.faint,
  unknown: CHROME.faint,
}

// Hawk/dove tone, reusing the same restrictive/accommodative pair the real
// policy rate bands use (PALETTE.policy orange vs PALETTE.headline blue).
export const VOTE_TONE = {
  hawk: PALETTE.policy,
  dove: PALETTE.headline,
}

// The CPI hierarchy the drilldown panel renders. `weight` and `contribution`
// are read from the observation at runtime.
export const HIERARCHY = {
  id: 'headline',
  label: 'Headline CPI',
  rate: 'headline_cpi',
  color: PALETTE.headline,
  children: [
    {
      id: 'core',
      label: 'Core CPI',
      rate: 'core_cpi',
      color: PALETTE.core,
      note: 'Excludes energy, food, alcohol and tobacco — the part of the basket least driven by global commodity prices.',
      children: [
        {
          id: 'services',
          label: 'Services',
          rate: 'services_cpi',
          color: PALETTE.services,
          note: 'Roughly 45% of the basket and the closest read on domestically generated inflation.',
        },
        {
          id: 'core_goods',
          label: 'Core goods',
          rate: 'core_goods_cpi',
          color: PALETTE.goods,
          note: 'Non-energy industrial goods. Sensitive to sterling, freight costs and global goods demand.',
        },
      ],
    },
    {
      id: 'non_core',
      label: 'Non-core',
      rate: null,
      color: PALETTE.other,
      note: 'Volatile components the MPC will look through unless they start feeding into wages and services prices.',
      children: [
        {
          id: 'energy',
          label: 'Energy',
          rate: 'energy_cpi',
          color: PALETTE.energy,
          note: 'Electricity, gas and motor fuels. Moves with wholesale markets and the Ofgem cap, with a lag.',
        },
        {
          id: 'food',
          label: 'Food',
          rate: 'food_cpi',
          color: PALETTE.food,
          note: 'Food and non-alcoholic beverages. Globally traded and highly visible to households.',
        },
        {
          id: 'alcohol_tobacco',
          label: 'Alcohol & tobacco',
          rate: 'alcohol_tobacco_cpi',
          color: PALETTE.alcohol,
          note: 'Small weight, but duty changes at fiscal events can move it sharply.',
        },
      ],
    },
  ],
}

// What the Bank of England actually watches, ranked. Used by the BoE view.
export const BOE_INDICATORS = [
  {
    id: 'services_cpi',
    label: 'Services inflation',
    stars: 5,
    color: PALETTE.services,
    why: 'The single best available proxy for domestically generated inflation. Services prices are dominated by labour costs, so they move with wage growth rather than with global commodity prices.',
    domestic: 'Yes — largely set by UK labour costs',
    volatile: 'Low, though indexation and administered prices make April prints jumpy',
    policySensitive: 'High — this is the part of the basket policy can actually reach',
  },
  {
    id: 'wage_growth',
    label: 'Wage growth',
    stars: 5,
    color: PALETTE.core,
    why: 'Pay growth running well above productivity growth is inconsistent with 2% inflation over time. The MPC treats it as the key test of whether an inflation shock has become self-sustaining.',
    domestic: 'Yes — the primary domestic cost channel',
    volatile: 'Moderate; bonus effects and data quality issues add noise',
    policySensitive: 'High, but with long lags through the labour market',
  },
  {
    id: 'core_cpi',
    label: 'Core CPI',
    stars: 4,
    color: PALETTE.core,
    why: 'Strips out the components most exposed to global shocks, giving a cleaner read on the underlying trend than headline. Still contains core goods, which are import-sensitive.',
    domestic: 'Partly — services are, core goods are not',
    volatile: 'Low',
    policySensitive: 'Moderate to high',
  },
  {
    id: 'headline_cpi',
    label: 'Headline CPI',
    stars: 3,
    color: PALETTE.headline,
    why: 'The target variable and the anchor for inflation expectations and wage bargaining — but it is dominated by energy and food, which policy cannot influence. The MPC targets it without reacting mechanically to it.',
    domestic: 'No — heavily influenced by imported energy and food',
    volatile: 'High',
    policySensitive: 'Low in the short run',
  },
  {
    id: 'goods_cpi',
    label: 'Goods inflation',
    stars: 2,
    color: PALETTE.goods,
    why: 'Mostly reflects global supply conditions, freight costs and the exchange rate. Useful for reading how much of an inflation episode is imported, but a weak guide to the policy stance.',
    domestic: 'No — largely imported',
    volatile: 'High',
    policySensitive: 'Low, other than through the exchange rate',
  },
]
