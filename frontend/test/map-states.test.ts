// Owner: Dev B
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'
import {
  BLUE,
  DEFAULT_METRIC,
  METRICS,
  NEUTRAL,
  NO_DATA,
  RED,
  metricLines,
  platformState,
  riskTier,
  scaleFor,
} from '../src/pages/map/states.ts'

const topology = JSON.parse(
  readFileSync(new URL('../public/geo/india-states.topo.json', import.meta.url), 'utf-8'),
) as { objects: { states: { geometries: { properties: { name: string } }[] } } }
const featureNames = topology.objects.states.geometries.map((g) => platformState(g.properties.name))

// Every state the platform uses: fixtures, datagen/generate.py and the demo database.
const PLATFORM_STATES = [
  'Andhra Pradesh', 'Assam', 'Bihar', 'Chhattisgarh', 'Delhi', 'Gujarat', 'Haryana',
  'Himachal Pradesh', 'Jharkhand', 'Karnataka', 'Kerala', 'Madhya Pradesh', 'Maharashtra',
  'Odisha', 'Punjab', 'Rajasthan', 'Tamil Nadu', 'Telangana', 'Uttar Pradesh', 'Uttarakhand',
  'West Bengal',
]

const metric = (key: string) => METRICS.find((m) => m.key === key)!

describe('state map geometry', () => {
  it('has 36 states and UTs with J&K and Ladakh as separate features', () => {
    assert.equal(featureNames.length, 36)
    assert.equal(new Set(featureNames).size, 36)
    for (const name of ['Jammu & Kashmir', 'Ladakh', 'Arunachal Pradesh', 'Lakshadweep', 'Andaman & Nicobar']) {
      assert.ok(featureNames.includes(name), name)
    }
  })

  it('maps every platform state to exactly one feature', () => {
    for (const state of PLATFORM_STATES) {
      assert.equal(featureNames.filter((n) => n === state).length, 1, state)
    }
    assert.equal(platformState('NCT of Delhi'), 'Delhi')
    assert.equal(platformState('Orissa'), 'Odisha')
  })
})

describe('colour scales', () => {
  it('centres utilisation at 100% with blue under and red over', () => {
    const scale = scaleFor(metric('utilisation'), [0.8, 1.1])
    assert.equal(scale.color(1), NEUTRAL)
    const [r1, , b1] = [1, 3, 5].map((i) => Number.parseInt(scale.color(0.8).slice(i, i + 2), 16))
    const [r2, , b2] = [1, 3, 5].map((i) => Number.parseInt(scale.color(1.2).slice(i, i + 2), 16))
    assert.ok(b1 > r1, 'under capacity is blue')
    assert.ok(r2 > b2, 'over capacity is red')
    assert.equal(scale.color(null), NO_DATA)
  })

  it('makes a lower Integrity Score a darker red', () => {
    const scale = scaleFor(metric('avg_integrity_score'), [38, 93])
    assert.equal(scale.color(38), RED.at(-1))
    assert.equal(scale.color(93), RED[0])
  })

  it('runs admissions light to dark blue from zero', () => {
    const scale = scaleFor(metric('active_admissions'), [100, 400])
    assert.equal(scale.color(0), BLUE[0])
    assert.equal(scale.color(400), BLUE.at(-1))
    assert.equal(scale.stops[0].label, '0')
  })

  it('uses the engine risk tiers', () => {
    assert.deepEqual([85, 70, 45, 38, null].map(riskTier), ['low', 'medium', 'high', 'critical', null])
  })
})

describe('defaults and overrun markers', () => {
  const row = {
    state: 'Uttar Pradesh',
    institutions: 1,
    active_admissions: 71,
    approved_seats: 120,
    utilisation: 0.5917,
    overrun_programmes: 1,
    open_review_cases: 3,
    avg_integrity_score: 47.7,
    institutions_list: [],
  }

  it('opens on Avg Integrity Score', () => {
    assert.equal(DEFAULT_METRIC, 'avg_integrity_score')
  })

  it('adds programmes over intake to the state description only when there are some', () => {
    const lines = metricLines(row)
    assert.equal(lines.at(-1), 'Programmes over intake: 1')
    assert.ok(lines.includes('Avg Integrity Score: 47.7'))
    assert.ok(!metricLines({ ...row, overrun_programmes: 0 }).some((l) => l.startsWith('Programmes over')))
    assert.deepEqual(metricLines(undefined), ['No institutions on the platform'])
  })
})
