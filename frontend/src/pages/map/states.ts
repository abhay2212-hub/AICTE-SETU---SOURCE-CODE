// Owner: Dev B
// Pure helpers for the state map: geometry-to-platform names, metrics, colour scales, tiers.
import type { components } from '../../lib/api-types'

type StateRow = components['schemas']['StateRow']

/** Geometry names (DataMeet States layer) whose platform spelling differs. Every other
 *  geometry name is used as is: the platform's institutions.state values match exactly. */
export const NAME_ALIASES: Record<string, string> = {
  'NCT of Delhi': 'Delhi',
  'Orissa': 'Odisha',
  'Uttaranchal': 'Uttarakhand',
  'Pondicherry': 'Puducherry',
  'Jammu and Kashmir': 'Jammu & Kashmir',
  'Andaman and Nicobar Islands': 'Andaman & Nicobar',
}

export function platformState(geometryName: string): string {
  return NAME_ALIASES[geometryName] ?? geometryName
}

export type MetricKey = 'active_admissions' | 'utilisation' | 'open_review_cases' | 'avg_integrity_score'

export interface Metric {
  key: MetricKey
  label: string
  short: string
  unit: string
  format: (value: number) => string
}

const indian = (value: number) => Math.round(value).toLocaleString('en-IN')

export const METRICS: Metric[] = [
  { key: 'active_admissions', label: 'Active admissions', short: 'Admissions', unit: 'admissions', format: indian },
  {
    key: 'utilisation',
    label: 'Seat utilisation',
    short: 'Utilisation',
    unit: '% of approved seats',
    format: (v) => `${Math.round(v * 100)}%`,
  },
  { key: 'open_review_cases', label: 'Open review cases', short: 'Open cases', unit: 'cases', format: indian },
  {
    key: 'avg_integrity_score',
    label: 'Avg Integrity Score',
    short: 'Integrity',
    unit: 'out of 100',
    format: (v) => v.toFixed(1),
  },
]

// Integrity first, so the riskiest state is the darkest red on first load.
export const DEFAULT_METRIC: MetricKey = 'avg_integrity_score'

export function overrunLine(row: StateRow): string {
  return `Programmes over intake: ${row.overrun_programmes}`
}

/** All four metrics (plus programmes over intake) as text, for the <title> of each state. */
export function metricLines(row: StateRow | undefined): string[] {
  if (!row) return ['No institutions on the platform']
  const lines = METRICS.map((m) => {
    const value = row[m.key]
    return `${m.label}: ${value === null || value === undefined ? 'not available' : m.format(value)}`
  })
  return row.overrun_programmes > 0 ? [...lines, overrunLine(row)] : lines
}

// Ramps (light -> dark). Blue is the default sequential hue, orange the second one; the
// diverging scale runs blue (under capacity) through a neutral grey to red (over capacity).
// Each ramp starts at a step that clears 2:1 on the page, so the lowest state never reads as
// the no-data grey, and adjacent steps stay visibly apart (dataviz validator, --ordinal).
export const BLUE = ['#86b6ef', '#5598e7', '#2a78d6', '#1c5cab', '#0d366b']
export const ORANGE = ['#f4a179', '#eb6834', '#c9501f', '#9c3c14', '#6f2a0d']
export const RED = ['#ef9090', '#e34948', '#c13332', '#952524', '#6a1817']
export const NEUTRAL = '#f0efec'
export const NO_DATA = '#e2e8f0'
/** Utilisation colour arms: 75% and 125% get the full blue and red. */
export const UTILISATION_SPREAD = 0.25

function hexToRgb(hex: string): [number, number, number] {
  const n = Number.parseInt(hex.slice(1), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

function mix(a: string, b: string, t: number): string {
  const [ar, ag, ab] = hexToRgb(a)
  const [br, bg, bb] = hexToRgb(b)
  const channel = (x: number, y: number) => Math.round(x + (y - x) * t).toString(16).padStart(2, '0')
  return `#${channel(ar, br)}${channel(ag, bg)}${channel(ab, bb)}`
}

/** Colour at position t (0..1) along a ramp, interpolating between its steps. */
export function rampAt(ramp: string[], t: number): string {
  const clamped = Math.min(Math.max(t, 0), 1) * (ramp.length - 1)
  const i = Math.min(Math.floor(clamped), ramp.length - 2)
  return mix(ramp[i], ramp[i + 1], clamped - i)
}

export interface Scale {
  color: (value: number | null | undefined) => string
  /** Legend stops left to right, with their labels. */
  stops: { color: string; label: string }[]
  /** CSS gradient for the legend bar. */
  gradient: string
  caption: string
}

function gradientOf(colors: string[]): string {
  return `linear-gradient(to right, ${colors.join(', ')})`
}

/** Colour scale for one metric over the values present on the map. */
export function scaleFor(metric: Metric, values: number[]): Scale {
  const finite = values.filter((v) => Number.isFinite(v))
  const min = finite.length ? Math.min(...finite) : 0
  const max = finite.length ? Math.max(...finite) : 0
  const none = (value: number | null | undefined) =>
    value === null || value === undefined || !Number.isFinite(value)

  if (metric.key === 'utilisation') {
    // Diverging, centred at 100% with fixed arms of ±25 points: most states sit within a few
    // points of capacity, so a data-driven range would let one outlier wash out the rest.
    // Values beyond the arms take the end colour; the legend says so.
    const spread = UTILISATION_SPREAD
    const color = (value: number | null | undefined) => {
      if (none(value)) return NO_DATA
      const v = value as number
      if (v === 1) return NEUTRAL
      return v < 1
        ? mix(NEUTRAL, BLUE[3], Math.min((1 - v) / spread, 1))
        : mix(NEUTRAL, RED[2], Math.min((v - 1) / spread, 1))
    }
    return {
      color,
      stops: [
        { color: color(1 - spread), label: `≤${metric.format(1 - spread)}` },
        { color: NEUTRAL, label: '100%' },
        { color: color(1 + spread), label: `≥${metric.format(1 + spread)}` },
      ],
      gradient: gradientOf([
        color(1 - spread),
        mix(NEUTRAL, BLUE[3], 0.5),
        NEUTRAL,
        mix(NEUTRAL, RED[2], 0.5),
        color(1 + spread),
      ]),
      caption: 'Under capacity ← 100% of approved seats → over capacity',
    }
  }

  const span = max - min || 1
  if (metric.key === 'avg_integrity_score') {
    // Lower score = higher risk = darker red.
    const color = (value: number | null | undefined) =>
      none(value) ? NO_DATA : rampAt(RED, finite.length < 2 ? 0.6 : (max - (value as number)) / span)
    return {
      color,
      stops: [
        { color: color(max), label: metric.format(max) },
        { color: color(min), label: metric.format(min) },
      ],
      gradient: gradientOf([color(max), rampAt(RED, 0.5), color(min)]),
      caption: 'Higher score (lower risk) → lower score (higher risk)',
    }
  }

  const ramp = metric.key === 'open_review_cases' ? ORANGE : BLUE
  const floor = Math.min(min, 0)
  const range = max - floor || 1
  const color = (value: number | null | undefined) =>
    none(value) ? NO_DATA : rampAt(ramp, ((value as number) - floor) / range)
  return {
    color,
    stops: [
      { color: color(floor), label: metric.format(floor) },
      { color: color(max), label: metric.format(max) },
    ],
    gradient: gradientOf([color(floor), rampAt(ramp, 0.5), color(max)]),
    caption: `Fewer → more ${metric.unit}`,
  }
}

export type Tier = 'low' | 'medium' | 'high' | 'critical'

/** Risk tier from an Integrity Score, as in engine/scoring (80 / 60 / 40). */
export function riskTier(score: number | null | undefined): Tier | null {
  if (score === null || score === undefined) return null
  if (score >= 80) return 'low'
  if (score >= 60) return 'medium'
  if (score >= 40) return 'high'
  return 'critical'
}

export const TIER_STYLE: Record<Tier, { label: string; className: string }> = {
  low: { label: 'Low risk', className: 'bg-green-50 text-green-800 ring-green-600/30' },
  medium: { label: 'Medium risk', className: 'bg-amber-50 text-amber-800 ring-amber-500/40' },
  high: { label: 'High risk', className: 'bg-orange-50 text-orange-800 ring-orange-500/40' },
  critical: { label: 'Critical risk', className: 'bg-red-50 text-red-800 ring-red-600/30' },
}
