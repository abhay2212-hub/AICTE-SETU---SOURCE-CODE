// Owner: Dev D
import { useQueryClient } from '@tanstack/react-query'
import { useSyncExternalStore } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  ROLES,
  ROUTES,
  canAccess,
  routeAfterRoleChange,
  routeFor,
  setIdentity,
  useIdentity,
  type Role,
} from '../lib/roles'

// The home page marks its dark hero with this id; the header goes dark while it is under it.
const HOME_HERO_ID = 'home-hero'
const HEADER_HEIGHT = 64
// Query keys whose responses are the same for every demo role (pages/home).
const ROLE_INDEPENDENT_QUERIES = new Set(['health', 'public-stats'])

function LogoMark() {
  return (
    <svg viewBox="0 0 32 32" className="h-8 w-8 shrink-0" aria-hidden="true">
      <defs>
        <linearGradient id="logo-gradient" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#6366f1" />
          <stop offset="1" stopColor="#1e1b6b" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#logo-gradient)" />
      <rect x="7" y="9" width="18" height="3" rx="1.5" fill="#fff" opacity="0.45" />
      <rect x="7" y="15" width="12" height="3" rx="1.5" fill="#fff" opacity="0.7" />
      <path
        d="M15.5 22.5l2.5 2.5 5.5-6"
        fill="none"
        stroke="#34d399"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function subscribeToViewport(onChange: () => void): () => void {
  window.addEventListener('scroll', onChange, { passive: true })
  window.addEventListener('resize', onChange)
  return () => {
    window.removeEventListener('scroll', onChange)
    window.removeEventListener('resize', onChange)
  }
}

/** Whether the hero's bottom edge is still below the header. Measured on every render and
 * scroll, so a remount or role change never leaves a stale value; dark until the hero exists. */
function heroUnderHeader(): boolean {
  const hero = document.getElementById(HOME_HERO_ID)
  if (!hero) return true
  const header = document.querySelector('header')?.getBoundingClientRect().height ?? HEADER_HEIGHT
  return hero.getBoundingClientRect().bottom > header
}

/** True while the home hero is still under the sticky header. */
function useOnHomeHero(pathname: string): boolean {
  const onHero = useSyncExternalStore(subscribeToViewport, heroUnderHeader, () => true)
  return pathname === '/' && onHero
}

function AccessPanel({ pathname, role, onSwitch }: {
  pathname: string
  role: Role
  onSwitch: (role: Role) => void
}) {
  const route = routeFor(pathname)
  if (!route) return null
  const suggested = route.roles[0]
  return (
    <div className="mx-auto mt-10 max-w-lg rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.75}
          strokeLinecap="round"
          strokeLinejoin="round"
          className="h-6 w-6"
          aria-hidden="true"
        >
          <rect x="5" y="11" width="14" height="9" rx="2" />
          <path d="M8 11V8a4 4 0 0 1 8 0v3" />
        </svg>
      </div>
      <h1 className="mt-4 text-xl font-semibold text-slate-950">
        This view is for {route.audience}
      </h1>
      <p className="mt-2 text-sm text-slate-600">
        You are using the demo as <span className="font-medium">{role}</span>. {route.label} is
        available to {route.roles.join(' and ')}.
      </p>
      <button
        type="button"
        onClick={() => onSwitch(suggested)}
        className="mt-6 inline-flex items-center justify-center rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 focus:outline-none focus-visible:ring-4 focus-visible:ring-indigo-200"
      >
        Switch to {suggested}
      </button>
    </div>
  )
}

export default function Layout() {
  const { role } = useIdentity()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const dark = useOnHomeHero(pathname)

  function switchRole(next: Role, follow: boolean) {
    // Drop cached responses fetched as the previous role before the page remounts; keep the
    // role-independent ones the home page shows.
    queryClient.removeQueries({
      predicate: (query) => !ROLE_INDEPENDENT_QUERIES.has(String(query.queryKey[0])),
    })
    setIdentity({ role: next })
    const target = routeAfterRoleChange(next, pathname)
    if (follow && target !== pathname) navigate(target)
  }

  const pill = (active: boolean) =>
    `whitespace-nowrap rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
      active
        ? dark
          ? 'bg-white text-indigo-950'
          : 'bg-indigo-600 text-white shadow-sm'
        : dark
          ? 'text-indigo-100 hover:bg-white/10 hover:text-white'
          : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
    }`

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header
        className={`sticky top-0 z-40 border-b backdrop-blur-md transition-colors duration-300 motion-reduce:transition-none ${
          dark
            ? 'border-white/10 bg-[#0b1437]/90 text-white'
            : 'border-slate-200/80 bg-white/90 text-slate-900'
        }`}
      >
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
          <Link to="/" className="flex items-center gap-2.5 rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400">
            <LogoMark />
            <span className="text-base font-semibold tracking-tight sm:text-lg">
              APAAR Integrity
              <span className="hidden sm:inline"> Platform</span>
            </span>
          </Link>
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-medium ring-1 ${
              dark
                ? 'bg-amber-300/15 text-amber-200 ring-amber-300/30'
                : 'bg-amber-50 text-amber-800 ring-amber-200'
            }`}
            title="Demo roles instead of sign-in; every record is synthetic"
          >
            Demo login · synthetic data
          </span>
          <nav
            aria-label="Main"
            className="order-last -mx-1 flex w-full gap-1 overflow-x-auto px-1 pb-0.5 lg:order-none lg:mx-0 lg:w-auto lg:px-0 lg:pb-0"
          >
            {ROUTES.filter((route) => route.roles.includes(role)).map((route) => (
              <NavLink
                key={route.path}
                to={route.path}
                end={route.path === '/'}
                className={({ isActive }) => pill(isActive)}
              >
                {route.label}
              </NavLink>
            ))}
          </nav>
          <label className="ml-auto flex items-center gap-2 text-sm">
            <span className={dark ? 'text-indigo-200' : 'text-slate-500'}>Demo role</span>
            <select
              className={`rounded-lg border px-2.5 py-1.5 text-sm font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-indigo-400 ${
                dark
                  ? 'border-white/20 bg-white/10 text-white'
                  : 'border-slate-300 bg-white text-slate-900'
              }`}
              value={role}
              onChange={(event) => switchRole(event.target.value as Role, true)}
            >
              {ROLES.map((r) => (
                <option key={r} value={r} className="bg-white text-slate-900">
                  {r}
                </option>
              ))}
            </select>
          </label>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        {canAccess(role, pathname) ? (
          // Keyed by role so role-scoped pages remount and refetch when the demo role changes.
          // Home only reads /public/stats, so it keeps its key and its hero stays mounted.
          <Outlet key={pathname === '/' ? 'home' : role} />
        ) : (
          <AccessPanel
            pathname={pathname}
            role={role}
            onSwitch={(next) => switchRole(next, false)}
          />
        )}
      </main>
    </div>
  )
}
