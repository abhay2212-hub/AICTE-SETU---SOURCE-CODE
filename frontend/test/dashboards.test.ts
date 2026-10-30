// Owner: Dev D
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'
import {
  DASHBOARD_HEADERS,
  ROLE_ACCENT,
  aicteHeader,
  aicteSections,
  institutionHeader,
  institutionSections,
  viewerHeader,
} from '../src/lib/dashboards.ts'
import { ROLES, canAccess, canPerform } from '../src/lib/roles.ts'

describe('role dashboards', () => {
  it('gives the institution operator a data entry workspace, seats then upload', () => {
    assert.deepEqual(institutionSections('institution_operator'), [
      'ledger_strip',
      'upload',
      'rows_to_fix',
      'batch_history',
      'edit_requests',
    ])
    assert.equal(institutionHeader('institution_operator').title, 'Data entry workspace')
    assert.equal(institutionHeader('institution_operator').accent, 'teal')
  })

  it('gives the institution admin oversight, intake alert first and upload last', () => {
    assert.deepEqual(institutionSections('institution_admin'), [
      'intake_alert',
      'kpis',
      'programmes',
      'warnings',
      'registry',
      'edit_requests',
      'upload_collapsed',
    ])
    assert.equal(institutionHeader('institution_admin').title, 'Institution oversight')
    assert.equal(institutionHeader('institution_admin').accent, 'indigo')
  })

  it('gives the AICTE admin a command centre, decisions first', () => {
    assert.deepEqual(aicteSections('aicte_admin'), [
      'decisions_waiting',
      'exception_queue',
      'edit_requests',
      'rankings',
      'reports',
      'audit_chain',
    ])
    assert.equal(aicteHeader('aicte_admin').title, 'AICTE command centre')
    assert.equal(aicteHeader('aicte_admin').accent, 'blue')
  })

  it('gives the auditor a read-only audit view, chain status and decision log first', () => {
    assert.deepEqual(aicteSections('auditor'), [
      'read_only_banner',
      'audit_status',
      'decision_log',
      'reports',
      'exception_queue',
      'rankings',
    ])
    assert.equal(aicteHeader('auditor').title, 'Audit view · read-only')
    assert.equal(aicteHeader('auditor').accent, 'slate')
  })

  it('makes every dashboard distinguishable by title and accent', () => {
    const headers = Object.values(DASHBOARD_HEADERS)
    assert.equal(new Set(headers.map((header) => header.title)).size, headers.length)
    assert.equal(new Set(headers.map((header) => header.accent)).size, headers.length)
    for (const header of headers) assert.ok(header.subtitle.length > 0, header.title)
  })

  it('keeps one accent per role across the app', () => {
    assert.equal(ROLE_ACCENT.student, 'emerald')
    assert.equal(ROLE_ACCENT.verifier, 'amber')
    assert.equal(new Set(Object.values(ROLE_ACCENT)).size, ROLES.length)
    for (const role of ROLES) assert.equal(DASHBOARD_HEADERS[role].accent, ROLE_ACCENT[role], role)
    assert.equal(DASHBOARD_HEADERS.student.title, 'My records')
    assert.equal(DASHBOARD_HEADERS.verifier.title, 'Verify a credential')
    for (const role of ROLES) assert.ok(canAccess(role, '/verifier'), role)
    // Shared pages take the viewer's accent.
    assert.equal(viewerHeader('aicte_admin', 'Blind Match', 'x').accent, 'blue')
    assert.equal(viewerHeader('auditor', 'Blind Match', 'x').accent, 'slate')
  })

  it('colours the landing role cards from the role accents', () => {
    const home = readFileSync(new URL('../src/pages/home/index.tsx', import.meta.url), 'utf8')
    assert.match(home, /accentTints\[ROLE_ACCENT\[card\.role\]\]/)
  })

  it('only shows a role sections it may use', () => {
    // Withdraw and Resolve live in the admin's registry and warnings sections.
    assert.ok(!institutionSections('institution_operator').includes('registry'))
    assert.ok(!institutionSections('institution_operator').includes('warnings'))
    assert.ok(canPerform('institution_admin', 'withdraw_admission'))
    assert.ok(canPerform('institution_admin', 'resolve_issue'))
    assert.ok(canPerform('institution_operator', 'upload_corrections'))
    // Pending edit requests to decide are an admin section; the auditor reads decided ones.
    assert.ok(!aicteSections('auditor').includes('edit_requests'))
    assert.ok(!aicteSections('auditor').includes('decisions_waiting'))
    assert.ok(canPerform('auditor', 'verify_audit_chain'))
    for (const role of ['institution_admin', 'institution_operator'] as const) assert.ok(canAccess(role, '/institution'))
    for (const role of ['aicte_admin', 'auditor'] as const) assert.ok(canAccess(role, '/aicte'))
  })

  it('renders each page from its section list', () => {
    const institution = readFileSync(new URL('../src/pages/institution/index.tsx', import.meta.url), 'utf8')
    const aicte = readFileSync(new URL('../src/pages/aicte/index.tsx', import.meta.url), 'utf8')
    assert.match(institution, /const sections = institutionSections\(role\)/)
    assert.match(institution, /Record<InstitutionSection, ReactNode>/)
    assert.match(aicte, /const sections = aicteSections\(role\)/)
    assert.match(aicte, /Record<AicteSection, ReactNode>/)
  })
})
