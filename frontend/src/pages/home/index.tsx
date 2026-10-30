// Owner: Dev D
import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../lib/api'
import type { components } from '../../lib/api-types'
import { ROLE_ACCENT } from '../../lib/dashboards'
import { setIdentity, type Role } from '../../lib/roles'
import { accentTints } from '../../components/accents'
import BlindMatchStrip from './BlindMatchStrip'
import HashChain from './HashChain'
import SeatLedgerCard from './SeatLedgerCard'
import './home.css'
import {
  ArrowIcon,
  BuildingIcon,
  CapIcon,
  ChartIcon,
  LinkLockIcon,
  MaskIcon,
  QrCheckIcon,
  ShieldIcon,
} from './icons'
import { useCountUp, useInView } from './motion'

type Health = components['schemas']['Health']
type PublicStats = components['schemas']['PublicStats']

const panel = 'rounded-2xl border border-slate-200 bg-white p-6 shadow-sm'
const sectionTitle = 'text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl'

// Each card takes its role's accent from lib/dashboards.ts, the same colour as that role's header.
const ROLE_CARDS: {
  role: Role
  to: string
  title: string
  line: string
  icon: ReactNode
}[] = [
  {
    role: 'institution_admin',
    to: '/institution',
    title: 'Institution',
    line: 'Upload a batch, fix flagged rows and watch the Seat Ledger update live.',
    icon: <BuildingIcon />,
  },
  {
    role: 'aicte_admin',
    to: '/aicte',
    title: 'AICTE',
    line: 'Integrity scores, open review cases, Blind Match results and reports.',
    icon: <ChartIcon />,
  },
  {
    role: 'student',
    to: '/student',
    title: 'Student',
    line: 'Confirm or dispute your admission and collect a signed credential.',
    icon: <CapIcon />,
  },
  {
    role: 'verifier',
    to: '/verifier',
    title: 'Verifier',
    line: 'Scan a credential QR and check its signature and revocation status.',
    icon: <QrCheckIcon />,
  },
]

const STEPS = [
  { title: 'Upload', line: 'Institutions upload admission batches as CSV or through the API.' },
  {
    title: 'Validate & Seat Ledger',
    line: 'Every row is checked and counted against approved intake, pool by pool.',
  },
  {
    title: 'Integrity Score & Blind Match',
    line: 'Anomaly signals score each institution; duplicates surface across institutions.',
  },
  {
    title: 'Student-verified credential',
    line: 'Students confirm their record and receive a signed, verifiable credential.',
  },
]

const PRIVACY = [
  {
    icon: <MaskIcon />,
    title: 'APAAR masked everywhere',
    line: 'IDs appear only as XXXX-XXXX-1234, in every screen, export and API response.',
  },
  {
    icon: <ShieldIcon />,
    title: 'Opting out never blocks',
    line: 'A student who opts out of APAAR gets a provisional ID and is admitted as normal.',
  },
  {
    icon: <LinkLockIcon />,
    title: 'Encodings, not names',
    line:
      'Blind Match compares keyed, one-way encodings of identity fields, so no raw identity leaves an institution.',
  },
]

function healthState(health: UseQueryResult<Health>) {
  if (health.isPending) return { dot: 'bg-slate-400', ping: false, label: 'Checking systems…' }
  if (health.isError || health.data.status !== 'ok') {
    return { dot: 'bg-red-500', ping: false, label: 'API unreachable' }
  }
  if (!health.data.engine_import_ok || health.data.db === 'error') {
    return { dot: 'bg-amber-400', ping: false, label: 'Some systems degraded' }
  }
  return { dot: 'bg-emerald-400', ping: true, label: 'All systems live' }
}

function Stat({
  label,
  stats,
  target,
  children,
}: {
  label: string
  stats: UseQueryResult<PublicStats>
  target: number | undefined
  children?: ReactNode
}) {
  const value = useCountUp(stats.isSuccess ? target : undefined)
  return (
    <div className={panel}>
      <p className="text-sm font-medium text-slate-500">{label}</p>
      {stats.isPending ? (
        <div className="mt-3 h-10 w-24 animate-pulse rounded-lg bg-slate-200" />
      ) : stats.isError ? (
        <p className="mt-3 text-4xl font-semibold text-slate-400">—</p>
      ) : (
        children ?? (
          <p className="mt-3 text-4xl font-semibold tracking-tight text-slate-950 tabular-nums">
            {value.toLocaleString('en-IN')}
          </p>
        )
      )}
    </div>
  )
}

function AuditValue({ stats }: { stats: PublicStats }) {
  const events = useCountUp(stats.audit_events)
  if (!stats.audit_chain_ok) {
    return <p className="mt-3 text-4xl font-semibold tracking-tight text-red-600">Broken</p>
  }
  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
      <p className="text-4xl font-semibold tracking-tight text-emerald-600">Verified</p>
      <HashChain />
      <p className="w-full text-xs text-slate-500 tabular-nums">
        {events.toLocaleString('en-IN')} events hash-linked
      </p>
    </div>
  )
}

function Stepper() {
  const [ref, seen] = useInView<HTMLOListElement>()
  return (
    <ol ref={ref} className="relative grid grid-cols-1 gap-8 sm:grid-cols-4 sm:gap-6">
      {/* Connector: one segment per step under 640px, a single horizontal line above. */}
      <span
        aria-hidden="true"
        className={`absolute top-5 left-[12.5%] right-[12.5%] hidden h-0.5 origin-left bg-indigo-500 transition-transform duration-[1200ms] ease-out motion-reduce:transition-none sm:block ${seen ? 'scale-x-100' : 'scale-x-0'}`}
      />
      {STEPS.map((step, index) => (
        <li
          key={step.title}
          className="relative flex gap-4 sm:flex-col sm:items-center sm:text-center"
        >
          {index < STEPS.length - 1 && (
            <span
              aria-hidden="true"
              className={`absolute top-10 left-5 h-[calc(100%-0.5rem)] w-0.5 origin-top bg-indigo-500 transition-transform duration-300 ease-out motion-reduce:transition-none sm:hidden ${seen ? 'scale-y-100' : 'scale-y-0'}`}
              style={{ transitionDelay: seen ? `${index * 300}ms` : '0ms' }}
            />
          )}
          <span
            className={`relative z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-semibold ring-4 ring-slate-50 transition-colors duration-500 motion-reduce:transition-none ${seen ? 'bg-indigo-600 text-white' : 'bg-white text-indigo-600 border border-indigo-200'}`}
            style={{ transitionDelay: seen ? `${index * 250}ms` : '0ms' }}
          >
            {index + 1}
          </span>
          <div>
            <p className="font-semibold text-slate-950">{step.title}</p>
            <p className="mt-1 text-sm text-slate-600">{step.line}</p>
          </div>
        </li>
      ))}
    </ol>
  )
}

export default function HomePage() {
  const navigate = useNavigate()
  const health = useQuery({ queryKey: ['health'], queryFn: () => api<Health>('/health') })
  // Unauthenticated aggregates, so the tiles work for every demo role.
  const stats = useQuery({
    queryKey: ['public-stats'],
    queryFn: () => api<PublicStats>('/public/stats'),
    retry: false,
  })
  const status = healthState(health)

  function openAs(role: Role, to: string) {
    setIdentity({ role })
    navigate(to)
  }

  return (
    <div className="space-y-16 pb-8 sm:space-y-24">
      {/* The hero bleeds past the layout's max width; clip the scrollbar-width overhang. */}
      <style>{'html { overflow-x: clip; }'}</style>
      {/* Layout.tsx keeps the header dark while this hero is under it. */}
      <section
        id="home-hero"
        className="home-hero-pattern relative left-1/2 -mt-6 w-screen -translate-x-1/2 text-white"
      >
        <div className="mx-auto grid max-w-6xl grid-cols-1 items-center gap-12 px-4 py-16 sm:py-24 lg:grid-cols-[1.1fr_1fr]">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-indigo-300">
              APAAR Integrity Platform
            </p>
            <h1 className="mt-4 text-4xl font-semibold leading-tight tracking-tight sm:text-6xl">
              Every admission, accounted for.
            </h1>
            <p className="mt-6 max-w-xl text-lg text-indigo-100">
              Verifiable, consent-first student records for AICTE: catch intake overruns, ghost
              and duplicate enrolments, and backdated admissions, without sharing raw identity.
            </p>
            <p className="mt-6 flex items-center gap-3 text-sm text-indigo-100">
              <span className="relative flex h-2.5 w-2.5" aria-hidden="true">
                {status.ping && (
                  <span
                    className={`absolute inset-0 rounded-full ${status.dot} opacity-75 motion-safe:animate-ping`}
                  />
                )}
                <span className={`relative h-2.5 w-2.5 rounded-full ${status.dot}`} />
              </span>
              {status.label}
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <button
                type="button"
                onClick={() => openAs('aicte_admin', '/aicte')}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-white px-5 py-3 text-sm font-semibold text-indigo-950 shadow-lg transition hover:bg-indigo-50 focus:outline-none focus-visible:ring-4 focus-visible:ring-indigo-300"
              >
                See the AICTE view <ArrowIcon />
              </button>
              <button
                type="button"
                onClick={() => openAs('institution_admin', '/institution')}
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/30 px-5 py-3 text-sm font-semibold text-white transition hover:bg-white/10 focus:outline-none focus-visible:ring-4 focus-visible:ring-indigo-300"
              >
                Watch an upload
              </button>
            </div>
          </div>
          <SeatLedgerCard />
        </div>
      </section>

      <section className="space-y-8">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className={sectionTitle}>Live numbers</h2>
          {stats.isSuccess && (
            <p className="text-sm text-slate-500">Academic year {stats.data.academic_year}</p>
          )}
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Institutions" stats={stats} target={stats.data?.institutions} />
          <Stat
            label="Active admissions"
            stats={stats}
            target={stats.data?.active_admissions}
          />
          <Stat
            label="Open review cases"
            stats={stats}
            target={stats.data?.open_review_cases}
          />
          <Stat label="Audit chain" stats={stats} target={undefined}>
            {stats.data && <AuditValue stats={stats.data} />}
          </Stat>
        </div>
      </section>

      <BlindMatchStrip />

      <section className="space-y-8">
        <h2 className={sectionTitle}>Try it as</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {ROLE_CARDS.map((card) => {
            const tint = accentTints[ROLE_ACCENT[card.role]]
            return (
              <button
                key={card.role}
                type="button"
                data-accent={ROLE_ACCENT[card.role]}
                onClick={() => openAs(card.role, card.to)}
                className={`${panel} flex flex-col text-left transition duration-200 hover:-translate-y-1 hover:shadow-lg focus:outline-none focus-visible:ring-4 focus-visible:ring-indigo-200 motion-reduce:transition-none motion-reduce:hover:translate-y-0 ${tint.border}`}
              >
                <span
                  className={`flex h-12 w-12 items-center justify-center rounded-xl ${tint.badge}`}
                >
                  {card.icon}
                </span>
                <span className="mt-4 text-lg font-semibold text-slate-950">{card.title}</span>
                <span className="mt-1 flex-1 text-sm text-slate-600">{card.line}</span>
                <span
                  className={`mt-4 inline-flex items-center gap-1 text-sm font-medium ${tint.text}`}
                >
                  Open as {card.role.replace('_', ' ')} <ArrowIcon />
                </span>
              </button>
            )
          })}
        </div>
      </section>

      <section className="space-y-10">
        <h2 className={sectionTitle}>How it works</h2>
        <Stepper />
      </section>

      <section className="space-y-8">
        <h2 className={sectionTitle}>Privacy by design</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {PRIVACY.map((point) => (
            <div key={point.title} className={panel}>
              <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-slate-900 text-white">
                {point.icon}
              </span>
              <p className="mt-4 text-lg font-semibold text-slate-950">{point.title}</p>
              <p className="mt-1 text-sm text-slate-600">{point.line}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="space-y-4 border-t border-slate-200 pt-8 text-sm text-slate-500">
        <p>SIH 2026 · PS 26263 (AICTE) · synthetic demonstration data</p>
        <details>
          <summary className="cursor-pointer select-none hover:text-slate-700">
            System status details
          </summary>
          {health.isSuccess ? (
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-6 gap-y-1">
              <dt>API</dt>
              <dd>
                {health.data.status} (v{health.data.version})
              </dd>
              <dt>Engine</dt>
              <dd>
                {health.data.engine_import_ok
                  ? `loaded${health.data.engine_version ? ` (v${health.data.engine_version})` : ''}`
                  : 'not loaded'}
              </dd>
              <dt>Database</dt>
              <dd>{health.data.db ?? 'unconfigured'}</dd>
              <dt>Login</dt>
              <dd>{health.data.mock_mode ? 'Demo roles (no sign-in)' : 'Supabase sign-in'}</dd>
              <dt>Live domains</dt>
              <dd className="break-words">
                {health.data.real_domains?.length
                  ? health.data.real_domains.join(', ')
                  : 'none (all synthetic fixtures)'}
              </dd>
            </dl>
          ) : (
            <p className="mt-3">{health.isPending ? 'Checking…' : 'Cannot reach the API.'}</p>
          )}
        </details>
      </footer>
    </div>
  )
}
