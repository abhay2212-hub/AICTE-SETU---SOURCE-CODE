// Owner: Dev D
// One dashboard per role on the shared /institution and /aicte pages: the page header and the
// order of its sections. Pages render sections in exactly this order; permissions stay in roles.ts.
import type { Role } from './roles'

export type Accent = 'teal' | 'indigo' | 'blue' | 'slate' | 'emerald' | 'amber'

// One colour per role across the app: page headers, landing cards and shared pages.
export const ROLE_ACCENT: Record<Role, Accent> = {
  institution_operator: 'teal',
  institution_admin: 'indigo',
  aicte_admin: 'blue',
  auditor: 'slate',
  student: 'emerald',
  verifier: 'amber',
}

export interface DashboardHeader {
  title: string
  subtitle: string
  accent: Accent
}

export type InstitutionSection =
  | 'upload'
  | 'rows_to_fix'
  | 'batch_history'
  | 'edit_requests'
  | 'ledger_strip'
  | 'intake_alert'
  | 'kpis'
  | 'programmes'
  | 'warnings'
  | 'registry'
  | 'upload_collapsed'

export type AicteSection =
  | 'read_only_banner'
  | 'decisions_waiting'
  | 'exception_queue'
  | 'edit_requests'
  | 'rankings'
  | 'reports'
  | 'audit_chain'
  | 'audit_status'
  | 'decision_log'

export type InstitutionRole = Extract<Role, 'institution_operator' | 'institution_admin'>
export type AicteRole = Extract<Role, 'aicte_admin' | 'auditor'>

export const INSTITUTION_SECTIONS: Record<InstitutionRole, readonly InstitutionSection[]> = {
  institution_operator: ['ledger_strip', 'upload', 'rows_to_fix', 'batch_history', 'edit_requests'],
  institution_admin: [
    'intake_alert',
    'kpis',
    'programmes',
    'warnings',
    'registry',
    'edit_requests',
    'upload_collapsed',
  ],
}

export const AICTE_SECTIONS: Record<AicteRole, readonly AicteSection[]> = {
  aicte_admin: ['decisions_waiting', 'exception_queue', 'edit_requests', 'rankings', 'reports', 'audit_chain'],
  auditor: ['read_only_banner', 'audit_status', 'decision_log', 'reports', 'exception_queue', 'rankings'],
}

export const DASHBOARD_HEADERS: Record<Role, DashboardHeader> = {
  institution_operator: {
    title: 'Data entry workspace',
    subtitle: 'Upload admission batches, fix the rows that failed and track your edit requests.',
    accent: ROLE_ACCENT.institution_operator,
  },
  institution_admin: {
    title: 'Institution oversight',
    subtitle: 'Keep every programme within approved intake and close out open warnings.',
    accent: ROLE_ACCENT.institution_admin,
  },
  aicte_admin: {
    title: 'AICTE command centre',
    subtitle: 'Decide open cases and edit requests, then act on the institutions most at risk.',
    accent: ROLE_ACCENT.aicte_admin,
  },
  auditor: {
    title: 'Audit view · read-only',
    subtitle: 'Check the audit chain and trace every decision back to who made it and why.',
    accent: ROLE_ACCENT.auditor,
  },
  student: {
    title: 'My records',
    subtitle: "See where you're reported, confirm it, and share proof",
    accent: ROLE_ACCENT.student,
  },
  verifier: {
    title: 'Verify a credential',
    subtitle: 'Scan or paste a QR; checked offline against the public key',
    accent: ROLE_ACCENT.verifier,
  },
}

/** Header for a page shared between roles (/blindmatch, /map), tinted with the viewer's accent. */
export function viewerHeader(role: Role, title: string, subtitle: string): DashboardHeader {
  return { title, subtitle, accent: ROLE_ACCENT[role] }
}

/** Sections of /institution for ``role``; anyone else falls back to the operator workspace. */
export function institutionSections(role: Role): readonly InstitutionSection[] {
  return role === 'institution_admin' ? INSTITUTION_SECTIONS.institution_admin : INSTITUTION_SECTIONS.institution_operator
}

/** Sections of /aicte for ``role``; anyone but an AICTE admin gets the read-only audit view. */
export function aicteSections(role: Role): readonly AicteSection[] {
  return role === 'aicte_admin' ? AICTE_SECTIONS.aicte_admin : AICTE_SECTIONS.auditor
}

export function institutionHeader(role: Role): DashboardHeader {
  return DASHBOARD_HEADERS[role === 'institution_admin' ? 'institution_admin' : 'institution_operator']
}

export function aicteHeader(role: Role): DashboardHeader {
  return DASHBOARD_HEADERS[role === 'aicte_admin' ? 'aicte_admin' : 'auditor']
}
