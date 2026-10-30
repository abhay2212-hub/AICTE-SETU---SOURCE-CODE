// Owner: Dev D
// Demo identity kept in localStorage and sent as X-Demo-Role / X-Demo-Institution in mock mode.
import { useSyncExternalStore } from 'react'

export const ROLES = [
  'institution_admin',
  'institution_operator',
  'aicte_admin',
  'student',
  'verifier',
  'auditor',
] as const

export type Role = (typeof ROLES)[number]

export interface DemoIdentity {
  role: Role
  institutionId: string
}

// Shadow Institute of Technology in the backend mock fixtures.
export const DEFAULT_INSTITUTION_ID = '10000000-0000-4000-8000-000000000003'
const STORAGE_KEY = 'apaar-demo-identity'
const DEFAULT_IDENTITY: DemoIdentity = { role: 'aicte_admin', institutionId: DEFAULT_INSTITUTION_ID }

function read(): DemoIdentity {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_IDENTITY
    const parsed = JSON.parse(raw) as Partial<DemoIdentity>
    const role = ROLES.includes(parsed.role as Role) ? (parsed.role as Role) : DEFAULT_IDENTITY.role
    return { role, institutionId: parsed.institutionId || DEFAULT_INSTITUTION_ID }
  } catch {
    return DEFAULT_IDENTITY
  }
}

let current = read()
const listeners = new Set<() => void>()

export function getIdentity(): DemoIdentity {
  return current
}

export function setIdentity(next: Partial<DemoIdentity>): void {
  current = { ...current, ...next }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(current))
  } catch {
    // Storage unavailable (private mode, blocked): keep the in-memory value.
  }
  listeners.forEach((listener) => listener())
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useIdentity(): DemoIdentity {
  return useSyncExternalStore(subscribe, getIdentity)
}

// ------------------------------------------------------------------ routes per role
export interface RouteAccess {
  path: string
  label: string
  roles: readonly Role[]
  /** Who the view is for, as in "This view is for …". */
  audience: string
}

// Same allow list as the header nav. The first role is the one offered by "Switch to …".
export const ROUTES: readonly RouteAccess[] = [
  { path: '/', label: 'Home', roles: ROLES, audience: 'everyone' },
  {
    path: '/institution',
    label: 'Institution',
    roles: ['institution_admin', 'institution_operator'],
    audience: 'institution staff',
  },
  { path: '/aicte', label: 'AICTE', roles: ['aicte_admin', 'auditor'], audience: 'AICTE administrators' },
  {
    path: '/blindmatch',
    label: 'Blind Match',
    roles: ['aicte_admin', 'auditor'],
    audience: 'AICTE administrators',
  },
  {
    path: '/map',
    label: 'State map',
    roles: ['aicte_admin', 'auditor'],
    audience: 'AICTE administrators',
  },
  { path: '/student', label: 'Student', roles: ['student'], audience: 'students' },
  // Public: checked offline against the public key, so it works for every role and without login.
  { path: '/verifier', label: 'Verifier', roles: ROLES, audience: 'everyone' },
]

export const ROLE_HOME: Record<Role, string> = {
  institution_admin: '/institution',
  institution_operator: '/institution',
  aicte_admin: '/aicte',
  auditor: '/aicte',
  student: '/student',
  verifier: '/verifier',
}

/** The guarded route a pathname falls under, or undefined for unknown paths (e.g. 404). */
export function routeFor(pathname: string): RouteAccess | undefined {
  if (pathname === '/' || pathname === '') return ROUTES[0]
  return ROUTES.find(
    (route) => route.path !== '/' && (pathname === route.path || pathname.startsWith(`${route.path}/`)),
  )
}

export function canAccess(role: Role, pathname: string): boolean {
  const route = routeFor(pathname)
  return route === undefined || route.roles.includes(role)
}

/** Where to go after switching to ``role``: stay when allowed, else the role's home route. */
export function routeAfterRoleChange(role: Role, pathname: string): string {
  return canAccess(role, pathname) ? pathname : ROLE_HOME[role]
}

// ------------------------------------------------------------------ actions per role
export const ROLE_LABELS: Record<Role, string> = {
  institution_admin: 'Institution admin',
  institution_operator: 'Institution operator',
  aicte_admin: 'AICTE admin',
  auditor: 'Auditor',
  student: 'Student',
  verifier: 'Verifier',
}

export interface ActionAccess {
  endpoint: string
  /** Same roles as the backend guard on ``endpoint``. The first one is named in the hint. */
  roles: readonly Role[]
}

// Actions behind a role guard, with the roles the backend allows. Keep in step with the
// backend routers; test/roles.test.ts compares each entry with its guard.
export const ACTIONS = {
  // ---- institution staff
  upload_batch: { endpoint: 'POST /batches', roles: ['institution_admin', 'institution_operator'] },
  map_batch: {
    endpoint: 'POST /batches/{batch_id}/mapping',
    roles: ['institution_admin', 'institution_operator'],
  },
  commit_batch: {
    endpoint: 'POST /batches/{batch_id}/commit',
    roles: ['institution_admin', 'institution_operator'],
  },
  upload_corrections: {
    endpoint: 'POST /batches/{batch_id}/corrections',
    roles: ['institution_admin', 'institution_operator'],
  },
  request_edit: {
    endpoint: 'POST /admissions/{admission_id}/edit-requests',
    roles: ['institution_admin', 'institution_operator'],
  },
  withdraw_admission: {
    endpoint: 'POST /admissions/{admission_id}/withdraw',
    roles: ['institution_admin'],
  },
  // Warnings and info. Errors are fixed by a correction upload, never resolved by hand.
  resolve_issue: {
    endpoint: 'POST /validation-issues/{issue_id}/resolve',
    roles: ['institution_admin', 'aicte_admin'],
  },
  // Same endpoint; the service only lets an AICTE admin resolve review findings.
  resolve_review_issue: {
    endpoint: 'POST /validation-issues/{issue_id}/resolve',
    roles: ['aicte_admin'],
  },
  manage_api_keys: {
    endpoint: 'POST /institutions/{institution_id}/api-keys',
    roles: ['institution_admin', 'aicte_admin'],
  },
  set_webhook: {
    endpoint: 'PUT /institutions/{institution_id}/webhook',
    roles: ['institution_admin', 'aicte_admin'],
  },
  // SIMULATED APAAR lookup.
  verify_apaar: {
    endpoint: 'POST /integrations/apaar/verify',
    roles: ['institution_admin', 'institution_operator', 'aicte_admin'],
  },
  // ---- AICTE. An auditor sees everything and changes nothing.
  resolve_review_case: { endpoint: 'POST /review-cases/{case_id}/resolve', roles: ['aicte_admin'] },
  decide_edit_request: {
    endpoint: 'POST /edit-requests/{edit_request_id}/decision',
    roles: ['aicte_admin'],
  },
  mark_no_response: { endpoint: 'POST /admin/admissions/mark-no-response', roles: ['aicte_admin'] },
  create_submission_window: { endpoint: 'POST /submission-windows', roles: ['aicte_admin'] },
  lock_submission_window: {
    endpoint: 'POST /submission-windows/{window_id}/lock',
    roles: ['aicte_admin'],
  },
  scan_blind_match: { endpoint: 'POST /admin/blind-match/scan', roles: ['aicte_admin'] },
  encode_blind_match: { endpoint: 'POST /blind-match/encode', roles: ['aicte_admin'] },
  run_engine: { endpoint: 'POST /engine/*', roles: ['aicte_admin'] },
  // Read-only actions an auditor keeps.
  verify_audit_chain: { endpoint: 'GET /audit/verify', roles: ['aicte_admin', 'auditor'] },
  download_enrolment_report: { endpoint: 'GET /reports/enrolment', roles: ['aicte_admin', 'auditor'] },
  load_accreditation_report: {
    endpoint: 'GET /reports/accreditation/{institution_id}',
    roles: ['aicte_admin', 'auditor', 'institution_admin'],
  },
} as const satisfies Record<string, ActionAccess>

export type Action = keyof typeof ACTIONS

export function canPerform(role: Role, action: Action): boolean {
  return (ACTIONS[action].roles as readonly Role[]).includes(role)
}

export const READ_ONLY_HINT = 'Auditors have read-only access'

/** "Needs institution admin" when ``role`` may not perform ``action``, else undefined. */
export function actionHint(role: Role, action: Action): string | undefined {
  if (canPerform(role, action)) return undefined
  if (role === 'auditor') return READ_ONLY_HINT
  const label = ROLE_LABELS[ACTIONS[action].roles[0]]
  return `Needs ${label.replace(/^[A-Z][a-z]/, (start) => start.toLowerCase())}`
}

export function useActionHint(action: Action): string | undefined {
  return actionHint(useIdentity().role, action)
}

/** Text of the "Signed in as …" badge. */
export function roleBadge(role: Role): string {
  return role === 'auditor' ? `${ROLE_LABELS.auditor} · read-only` : ROLE_LABELS[role]
}
