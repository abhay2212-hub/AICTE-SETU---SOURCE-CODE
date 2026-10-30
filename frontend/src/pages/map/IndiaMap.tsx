// Owner: Dev B
// SVG choropleth of India's states and UTs (d3-geo, Mercator fitted to the viewBox).
import { geoMercator, geoPath } from 'd3-geo'
import type { Feature, FeatureCollection, Geometry } from 'geojson'
import { useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react'
import type { components } from '../../lib/api-types'
import { METRICS, metricLines, overrunLine, platformState, type Metric, type Scale } from './states'

type StateRow = components['schemas']['StateRow']
export type StateFeature = Feature<Geometry, { name: string }>

const WIDTH = 800
const HEIGHT = 900
// Features smaller than this on screen (px²) also get a dot so they stay visible and clickable.
const TINY_AREA = 40

interface Props {
  geometry: FeatureCollection<Geometry, { name: string }>
  rows: Map<string, StateRow>
  metric: Metric
  scale: Scale
  selected: string | null
  onSelect: (state: string) => void
}

export default function IndiaMap({ geometry, rows, metric, scale, selected, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<{ state: string; x: number; y: number } | null>(null)

  const shapes = useMemo(() => {
    const projection = geoMercator().fitSize([WIDTH, HEIGHT], geometry)
    const path = geoPath(projection)
    return geometry.features.map((feature: StateFeature) => {
      const name = platformState(feature.properties.name)
      return {
        name,
        d: path(feature) ?? '',
        tiny: path.area(feature) < TINY_AREA,
        centroid: path.centroid(feature),
      }
    })
  }, [geometry])

  function place(event: MouseEvent, state: string) {
    const box = container.current?.getBoundingClientRect()
    if (!box) return
    // Keep the 240px tooltip inside the map.
    const x = Math.min(event.clientX - box.left + 16, box.width - 248)
    setHover({ state, x: Math.max(x, 0), y: event.clientY - box.top + 16 })
  }

  function onKey(event: KeyboardEvent, state: string) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      onSelect(state)
    }
  }

  const hovered = hover ? rows.get(hover.state) : undefined
  const outline = shapes.map((s) => s.d).join(' ')

  return (
    <div ref={container} className="relative" onMouseLeave={() => setHover(null)}>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="mx-auto h-auto max-h-[72vh] w-full"
        role="group"
        aria-label={`Map of India coloured by ${metric.label.toLowerCase()}`}
      >
        <defs>
          <pattern id="no-data" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="8" height="8" fill="#f1f5f9" />
            <line x1="0" y1="0" x2="0" y2="8" stroke="#cbd5e1" strokeWidth="2" />
          </pattern>
        </defs>
        {/* Country outline under the fills, so pale states keep a visible edge. */}
        <path d={outline} fill="none" stroke="#94a3b8" strokeWidth={2} aria-hidden="true" />
        {shapes.map((shape, index) => {
          const row = rows.get(shape.name)
          const value = row?.[metric.key]
          const fill = row ? scale.color(value) : 'url(#no-data)'
          const active = selected === shape.name || hover?.state === shape.name
          const title = `${shape.name}. ${metricLines(row).join('. ')}`
          return (
            <g key={shape.name} className="map-state" style={{ animationDelay: `${index * 18}ms` }}>
              <path
                d={shape.d}
                fill={fill}
                stroke={selected === shape.name ? '#4338ca' : active ? '#0f172a' : '#ffffff'}
                strokeWidth={selected === shape.name ? 2.5 : active ? 1.75 : 0.75}
                strokeLinejoin="round"
                className={`map-fill outline-none ${row ? 'cursor-pointer' : 'opacity-80'}`}
                tabIndex={row ? 0 : -1}
                role={row ? 'button' : undefined}
                aria-pressed={row ? selected === shape.name : undefined}
                aria-label={title}
                onMouseEnter={(e) => place(e, shape.name)}
                onMouseMove={(e) => place(e, shape.name)}
                onFocus={() => setHover(null)}
                onClick={() => row && onSelect(shape.name)}
                onKeyDown={(e) => row && onKey(e, shape.name)}
              >
                <title>{title}</title>
              </path>
              {shape.tiny && (
                <circle
                  cx={shape.centroid[0]}
                  cy={shape.centroid[1]}
                  r={5}
                  fill={fill}
                  stroke="#64748b"
                  strokeWidth={1}
                  className={row ? 'cursor-pointer' : undefined}
                  onMouseEnter={(e) => place(e, shape.name)}
                  onClick={() => row && onSelect(shape.name)}
                  aria-hidden="true"
                />
              )}
            </g>
          )
        })}
        {/* Programmes over intake: a red dot at the state's centroid, on every metric. */}
        <g aria-hidden="true" className="pointer-events-none">
          {shapes.map((shape) => {
            const row = rows.get(shape.name)
            if (!row || row.overrun_programmes <= 0) return null
            const [cx, cy] = shape.centroid
            return (
              <g key={shape.name} data-overrun={shape.name}>
                <circle cx={cx} cy={cy} r={7} fill="#dc2626" className="overrun-pulse" />
                <circle cx={cx} cy={cy} r={6} fill="#dc2626" stroke="#ffffff" strokeWidth={2} />
              </g>
            )
          })}
        </g>
      </svg>
      {hover && (
        <div
          role="tooltip"
          className="pointer-events-none absolute z-10 w-60 rounded-xl border border-slate-200 bg-white/95 p-3 text-sm shadow-lg backdrop-blur"
          style={{ left: hover.x, top: hover.y }}
        >
          <p className="font-semibold text-slate-950">{hover.state}</p>
          {hovered ? (
            <dl className="mt-2 space-y-1">
              {METRICS.map((m) => {
                const value = hovered[m.key]
                return (
                  <div key={m.key} className="flex justify-between gap-3">
                    <dt className={m.key === metric.key ? 'font-medium text-slate-900' : 'text-slate-500'}>
                      {m.label}
                    </dt>
                    <dd className="font-medium tabular-nums text-slate-900">
                      {value === null || value === undefined ? '—' : m.format(value)}
                    </dd>
                  </div>
                )
              })}
              {hovered.overrun_programmes > 0 && (
                <div className="flex items-center gap-2 border-t border-slate-100 pt-1 font-medium text-red-700">
                  <span className="h-2 w-2 rounded-full bg-red-600" aria-hidden="true" />
                  {overrunLine(hovered)}
                </div>
              )}
            </dl>
          ) : (
            <p className="mt-1 text-slate-500">No institutions on the platform</p>
          )}
        </div>
      )}
    </div>
  )
}
