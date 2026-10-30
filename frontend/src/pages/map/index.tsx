// Owner: Dev B
// F27: AICTE state map. Choropleth of India by state from GET /reports/states.
import { useQuery } from '@tanstack/react-query'
import type { FeatureCollection, Geometry } from 'geojson'
import { useCallback, useMemo, useState } from 'react'
import { feature } from 'topojson-client'
import type { Topology } from 'topojson-specification'
import { API_URL, ApiError } from '../../lib/api'
import type { components } from '../../lib/api-types'
import { viewerHeader } from '../../lib/dashboards'
import { getIdentity, useIdentity } from '../../lib/roles'
import DashboardHeader, { ReadOnlyBanner } from '../../components/DashboardHeader'
import IndiaMap from './IndiaMap'
import './map.css'
import StatePanel from './StatePanel'
import { DEFAULT_METRIC, METRICS, scaleFor, type MetricKey } from './states'

type StateReport = components['schemas']['StateReport']
type StateRow = components['schemas']['StateRow']
type Geo = FeatureCollection<Geometry, { name: string }>

const panel = 'rounded-2xl border border-slate-200 bg-white p-6 shadow-sm'

/** Fetches the report and whether this response came from fixtures (X-Mock: true). */
async function fetchStates(): Promise<{ report: StateReport; mock: boolean }> {
  const { role, institutionId } = getIdentity()
  const headers = new Headers({ 'X-Demo-Role': role })
  if (institutionId) headers.set('X-Demo-Institution', institutionId)
  const response = await fetch(`${API_URL}/reports/states`, { headers })
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(response.status, body)
  return { report: body as StateReport, mock: response.headers.get('X-Mock') === 'true' }
}

async function fetchGeometry(): Promise<Geo> {
  const response = await fetch('/geo/india-states.topo.json')
  if (!response.ok) throw new Error(`Map geometry failed to load (${response.status})`)
  const topology = (await response.json()) as Topology
  return feature(topology, topology.objects.states) as unknown as Geo
}

function SummaryTile({ label, value }: { label: string; value: string }) {
  return (
    <div className={panel}>
      <p className="text-sm font-medium text-slate-500">{label}</p>
      <p className="mt-2 text-3xl font-semibold tracking-tight tabular-nums text-slate-950">{value}</p>
    </div>
  )
}

function Skeleton() {
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_360px]" aria-busy="true" aria-label="Loading the map">
      <div className="aspect-[8/9] animate-pulse rounded-2xl bg-slate-200" />
      <div className="space-y-4">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-24 animate-pulse rounded-2xl bg-slate-200" />
        ))}
      </div>
    </div>
  )
}

export default function MapPage() {
  const { role } = useIdentity()
  const [metricKey, setMetricKey] = useState<MetricKey>(DEFAULT_METRIC)
  const [selected, setSelected] = useState<string | null>(null)
  const states = useQuery({ queryKey: ['state-report'], queryFn: fetchStates, retry: false })
  const geometry = useQuery({
    queryKey: ['india-geometry'],
    queryFn: fetchGeometry,
    staleTime: Infinity,
    retry: 1,
  })

  const metric = METRICS.find((m) => m.key === metricKey) ?? METRICS[0]
  const rows = useMemo(
    () => new Map<string, StateRow>((states.data?.report.rows ?? []).map((r) => [r.state, r])),
    [states.data],
  )
  const scale = useMemo(
    () =>
      scaleFor(
        metric,
        [...rows.values()]
          .map((r) => r[metric.key])
          .filter((v): v is number => v !== null && v !== undefined),
      ),
    [metric, rows],
  )
  const highestRisk = useMemo(() => {
    const scored = [...rows.values()].filter((r) => r.avg_integrity_score !== null && r.avg_integrity_score !== undefined)
    return scored.sort((a, b) => (a.avg_integrity_score as number) - (b.avg_integrity_score as number))[0]
  }, [rows])
  const close = useCallback(() => setSelected(null), [])

  const report = states.data?.report
  const selectedRow = selected ? rows.get(selected) : undefined
  const loading = states.isPending || geometry.isPending
  const failed = states.isError || geometry.isError

  return (
    <div className="space-y-8 pb-8">
      {role === 'auditor' && (
        <ReadOnlyBanner>
          You can view, verify and download. Decisions and edits are made by AICTE admins.
        </ReadOnlyBanner>
      )}
      <DashboardHeader
        header={viewerHeader(role, 'Admissions across India', `Academic year ${report?.academic_year ?? '2026-27'}`)}
        eyebrow="State map"
        simulated={Boolean(states.data?.mock)}
      />
      <div className="flex flex-wrap items-end justify-end gap-6">
        <div
          role="radiogroup"
          aria-label="Colour the map by"
          className="flex w-full flex-wrap gap-1 rounded-2xl bg-slate-100 p-1 sm:w-auto"
        >
          {METRICS.map((m) => (
            <button
              key={m.key}
              type="button"
              role="radio"
              aria-checked={m.key === metricKey}
              onClick={() => setMetricKey(m.key)}
              className={`flex-1 whitespace-nowrap rounded-xl px-3 py-2 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 sm:flex-none ${
                m.key === metricKey ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      {loading && <Skeleton />}

      {!loading && failed && (
        <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-6">
          <p className="text-sm text-red-800">
            {states.error instanceof ApiError
              ? `The state report could not be loaded (${states.error.status}).`
              : geometry.isError
                ? 'The map outline could not be loaded.'
                : 'We could not reach the service. Check that the backend is running.'}
          </p>
          <button
            type="button"
            onClick={() => {
              void states.refetch()
              void geometry.refetch()
            }}
            className="mt-4 rounded-lg bg-red-700 px-4 py-2 text-sm font-semibold text-white hover:bg-red-800"
          >
            Retry
          </button>
        </div>
      )}

      {!loading && !failed && report && geometry.data && report.rows.length === 0 && (
        <div className={`${panel} text-center text-slate-600`}>
          No institutions have admissions data for {report.academic_year} yet.
        </div>
      )}

      {!loading && !failed && report && geometry.data && report.rows.length > 0 && (
        <>
          <section aria-label="Totals" className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            <SummaryTile label="Institutions" value={report.totals.institutions.toLocaleString('en-IN')} />
            <SummaryTile
              label="Active admissions"
              value={report.totals.active_admissions.toLocaleString('en-IN')}
            />
            <SummaryTile label="States covered" value={String(report.totals.states)} />
            <SummaryTile
              label="Programmes over intake"
              value={report.totals.overrun_programmes.toLocaleString('en-IN')}
            />
            {highestRisk && (
              <button
                type="button"
                onClick={() => setSelected(highestRisk.state)}
                className="col-span-2 rounded-2xl border border-red-200 bg-red-50 p-6 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md focus:outline-none focus-visible:ring-4 focus-visible:ring-red-200 motion-reduce:transition-none motion-reduce:hover:translate-y-0 lg:col-span-1"
              >
                <p className="text-sm font-medium text-red-700">Highest risk state</p>
                <p className="mt-2 text-xl font-semibold tracking-tight text-red-950">{highestRisk.state}</p>
                <p className="mt-1 text-sm tabular-nums text-red-800">
                  Avg Integrity Score {highestRisk.avg_integrity_score?.toFixed(1)} · View →
                </p>
              </button>
            )}
          </section>

          <div className={`grid gap-6 ${selectedRow ? 'lg:grid-cols-[1fr_360px]' : ''}`}>
            <section className={`${panel} p-4 sm:p-6`} aria-label="State map">
              <IndiaMap
                geometry={geometry.data}
                rows={rows}
                metric={metric}
                scale={scale}
                selected={selected}
                onSelect={(state) => setSelected((current) => (current === state ? null : state))}
              />
              <div className="mt-4 flex flex-col gap-4 border-t border-slate-100 pt-4 sm:flex-row sm:items-end sm:justify-between">
                <div className="w-full max-w-sm">
                  <p className="text-sm font-medium text-slate-900">
                    {metric.label} <span className="font-normal text-slate-500">({metric.unit})</span>
                  </p>
                  <div className="mt-2 h-3 rounded-full" style={{ background: scale.gradient }} aria-hidden="true" />
                  <div className="mt-1 flex justify-between text-xs tabular-nums text-slate-600">
                    {scale.stops.map((stop) => (
                      <span key={stop.label}>{stop.label}</span>
                    ))}
                  </div>
                  <p className="mt-1 text-xs text-slate-500">{scale.caption}</p>
                </div>
                <div className="flex flex-col gap-2 text-xs text-slate-600">
                  <p className="flex items-center gap-2">
                    <span
                      className="inline-block h-3 w-3 rounded-full border-2 border-white bg-red-600 shadow-[0_0_0_1px_#dc2626]"
                      aria-hidden="true"
                    />
                    Programme over intake
                  </p>
                  <p className="flex items-center gap-2">
                    <span
                      className="inline-block h-3 w-5 rounded-sm border border-slate-300"
                      style={{
                        background: `repeating-linear-gradient(45deg, #f1f5f9 0 3px, #cbd5e1 3px 5px)`,
                      }}
                      aria-hidden="true"
                    />
                    No institutions on the platform
                  </p>
                </div>
              </div>
            </section>
            {selectedRow && <StatePanel row={selectedRow} onClose={close} />}
          </div>
        </>
      )}

      <p className="text-xs text-slate-500">
        India state boundaries:{' '}
        <a className="underline hover:text-slate-700" href="https://github.com/datameet/maps" target="_blank" rel="noreferrer">
          DataMeet India Community Maps Project
        </a>{' '}
        (
        <a className="underline hover:text-slate-700" href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">
          CC BY 4.0
        </a>
        ), simplified. Aggregates only; no student-level data is shown.
      </p>
    </div>
  )
}
