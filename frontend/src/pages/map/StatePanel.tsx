// Owner: Dev B
// Institutions of the selected state: side panel on wide screens, bottom sheet on phones.
import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import type { components } from '../../lib/api-types'
import { METRICS, TIER_STYLE, riskTier } from './states'

type StateRow = components['schemas']['StateRow']

interface Props {
  row: StateRow
  onClose: () => void
}

export default function StatePanel({ row, onClose }: Props) {
  const closeButton = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    closeButton.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [row.state, onClose])

  return (
    <aside
      aria-label={`Institutions in ${row.state}`}
      className="fixed inset-x-0 bottom-0 z-30 max-h-[70vh] overflow-y-auto rounded-t-3xl border-t border-slate-200 bg-white p-6 shadow-2xl lg:static lg:z-auto lg:max-h-none lg:rounded-2xl lg:border lg:shadow-sm"
    >
      <div className="mx-auto mb-4 h-1.5 w-12 rounded-full bg-slate-200 lg:hidden" aria-hidden="true" />
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-indigo-600">Selected state</p>
          <h2 className="mt-1 text-2xl font-semibold tracking-tight text-slate-950">{row.state}</h2>
        </div>
        <button
          ref={closeButton}
          type="button"
          onClick={onClose}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
        >
          Close<span className="sr-only"> {row.state} panel</span>
        </button>
      </div>

      <dl className="mt-5 grid grid-cols-2 gap-3">
        {METRICS.map((m) => {
          const value = row[m.key]
          return (
            <div key={m.key} className="rounded-xl bg-slate-50 p-3">
              <dt className="text-xs text-slate-500">{m.label}</dt>
              <dd className="mt-1 text-lg font-semibold tabular-nums text-slate-950">
                {value === null || value === undefined ? '—' : m.format(value)}
              </dd>
            </div>
          )
        })}
      </dl>

      <h3 className="mt-6 text-sm font-semibold text-slate-900">
        {row.institutions} {row.institutions === 1 ? 'institution' : 'institutions'}, lowest Integrity
        Score first
      </h3>
      <ul className="mt-3 space-y-2">
        {row.institutions_list.map((institution) => {
          const tier = riskTier(institution.integrity_score)
          return (
            <li key={institution.institution_id}>
              <Link
                to="/aicte"
                className="block rounded-xl border border-slate-200 p-3 transition hover:border-indigo-300 hover:bg-indigo-50/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-medium text-slate-950">{institution.name}</p>
                    <p className="text-xs text-slate-500">AICTE {institution.aicte_code}</p>
                  </div>
                  <span
                    className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold tabular-nums ring-1 ${
                      tier ? TIER_STYLE[tier].className : 'bg-slate-100 text-slate-600 ring-slate-300'
                    }`}
                  >
                    {institution.integrity_score === null || institution.integrity_score === undefined
                      ? 'Not scored'
                      : `${institution.integrity_score.toFixed(1)} · ${TIER_STYLE[tier!].label}`}
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                  <span className="text-slate-600">
                    {institution.open_review_cases} open {institution.open_review_cases === 1 ? 'case' : 'cases'}
                  </span>
                  {institution.overrun && (
                    <span className="rounded-full bg-red-50 px-2 py-0.5 font-semibold text-red-700 ring-1 ring-red-200">
                      Overrun
                    </span>
                  )}
                </div>
              </Link>
            </li>
          )
        })}
      </ul>
      <p className="mt-4 text-xs text-slate-500">Rows open the AICTE dashboard.</p>
    </aside>
  )
}
