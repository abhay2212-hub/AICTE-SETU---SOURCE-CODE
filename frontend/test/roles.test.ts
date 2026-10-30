// Owner: Dev D
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'
import {
  ACTIONS,
  ROLES,
  ROLE_HOME,
  ROLE_LABELS,
  actionHint,
  canAccess,
  canPerform,
  routeAfterRoleChange,
  roleBadge,
  routeFor,
  type Action,
} from '../src/lib/roles.ts'

describe('role routing', () => {
  it('sends each role to its home route', () => {
    assert.deepEqual(ROLE_HOME, {
      institution_admin: '/institution',
      institution_operator: '/institution',
      aicte_admin: '/aicte',
      auditor: '/aicte',
      student: '/student',
      verifier: '/verifier',
    })
    for (const role of ROLES) assert.ok(canAccess(role, ROLE_HOME[role]), role)
  })

  it('stays on an allowed route and leaves a forbidden one', () => {
    assert.equal(routeAfterRoleChange('student', '/institution'), '/student')
    assert.equal(routeAfterRoleChange('verifier', '/student'), '/verifier')
    assert.equal(routeAfterRoleChange('aicte_admin', '/blindmatch'), '/blindmatch')
    assert.equal(routeAfterRoleChange('aicte_admin', '/verifier'), '/verifier')
    assert.equal(routeAfterRoleChange('auditor', '/aicte/reports'), '/aicte/reports')
    assert.equal(routeAfterRoleChange('student', '/blindmatch'), '/student')
  })

  it('lets every role use home and unknown paths', () => {
    for (const role of ROLES) {
      assert.ok(canAccess(role, '/'), role)
      assert.ok(canAccess(role, '/no-such-page'), role)
    }
  })

  it('matches nested paths but not prefixes of other words', () => {
    assert.equal(routeFor('/aicte/reports')?.path, '/aicte')
    assert.equal(routeFor('/aicteish'), undefined)
    assert.deepEqual(routeFor('/institution')?.roles, ['institution_admin', 'institution_operator'])
  })
})

// Router file and the guard behind each action in ACTIONS: a guard constant (UPPER_CASE),
// or for an inline Depends(require_roles(...)) the route path or prefix that precedes it.
const GUARDS: Record<Exclude<Action, 'resolve_review_issue'>, [string, string]> = {
  upload_batch: ['batches.py', 'INTEGRATORS'],
  map_batch: ['batches.py', 'UPLOADERS'],
  commit_batch: ['batches.py', 'INTEGRATORS'],
  upload_corrections: ['batches.py', 'INTEGRATORS'],
  request_edit: ['admissions.py', 'EDITORS'],
  withdraw_admission: ['admissions.py', 'WITHDRAWERS'],
  resolve_issue: ['validation_issues.py', 'RESOLVERS'],
  manage_api_keys: ['institutions.py', 'KEY_ADMINS'],
  set_webhook: ['institutions.py', 'KEY_ADMINS'],
  verify_apaar: ['integrations.py', '"/apaar/verify"'],
  resolve_review_case: ['review_cases.py', 'RESOLVERS'],
  decide_edit_request: ['admissions.py', 'DECIDERS'],
  mark_no_response: ['admissions.py', 'DECIDERS'],
  create_submission_window: ['submission_windows.py', 'SETTERS'],
  lock_submission_window: ['submission_windows.py', 'SETTERS'],
  scan_blind_match: ['blind_match_scan.py', '"/scan"'],
  encode_blind_match: ['blind_match.py', '"/encode"'],
  run_engine: ['engine.py', 'prefix="/engine"'],
  verify_audit_chain: ['audit.py', '"/verify"'],
  download_enrolment_report: ['reports.py', 'ENROLMENT_READERS'],
  load_accreditation_report: ['reports.py', 'ACCREDITATION_READERS'],
}

const routers = new URL('../../backend/app/routers/', import.meta.url)

function backendRoles(file: string, guard: string): string[] {
  const source = readFileSync(new URL(file, routers), 'utf8')
  let args: string | undefined
  if (/^[A-Z_]+$/.test(guard)) {
    const pattern = new RegExp(`^${guard} = (?:require_roles|api_key_or_roles)\\(([^)]*)\\)`, 'm')
    args = pattern.exec(source)?.[1]
  } else {
    const at = source.indexOf(guard)
    if (at >= 0) args = /require_roles\(([^)]*)\)/.exec(source.slice(at))?.[1]
  }
  assert.ok(args, `${guard} in ${file}`)
  return [...args.matchAll(/"([a-z_]+)"/g)].map((found) => found[1]).sort()
}

describe('action roles', () => {
  it('match the backend guard on each endpoint', () => {
    for (const [action, [file, guard]] of Object.entries(GUARDS)) {
      assert.deepEqual([...ACTIONS[action as Action].roles].sort(), backendRoles(file, guard), action)
    }
    assert.deepEqual(Object.keys(ACTIONS).sort(), [...Object.keys(GUARDS), 'resolve_review_issue'].sort())
  })

  it('leaves review findings to the AICTE admin, as the batch service does', () => {
    const service = readFileSync(new URL('../services/batches.py', routers), 'utf8')
    assert.match(service, /severity == "review" and user\.role != "aicte_admin"/)
    assert.deepEqual(ACTIONS.resolve_review_issue.roles, ['aicte_admin'])
  })

  it('separates institution operator from institution admin', () => {
    assert.ok(canPerform('institution_operator', 'commit_batch'))
    assert.ok(canPerform('institution_admin', 'withdraw_admission'))
    assert.ok(!canPerform('institution_operator', 'withdraw_admission'))
    assert.ok(!canPerform('institution_operator', 'resolve_issue'))
    assert.ok(!canPerform('institution_operator', 'manage_api_keys'))
  })

  it('names the role the action needs', () => {
    assert.equal(actionHint('institution_operator', 'withdraw_admission'), 'Needs institution admin')
    assert.equal(actionHint('institution_admin', 'resolve_review_issue'), 'Needs AICTE admin')
    assert.equal(actionHint('institution_admin', 'withdraw_admission'), undefined)
    assert.equal(ROLE_LABELS.institution_operator, 'Institution operator')
  })

  it('keeps the auditor read-only', () => {
    const allowed = (Object.keys(ACTIONS) as Action[]).filter((action) => canPerform('auditor', action))
    assert.deepEqual(allowed.sort(), [
      'download_enrolment_report',
      'load_accreditation_report',
      'verify_audit_chain',
    ])
    for (const action of ['resolve_review_case', 'decide_edit_request', 'scan_blind_match'] as const) {
      assert.ok(canPerform('aicte_admin', action), action)
      assert.equal(actionHint('auditor', action), 'Auditors have read-only access')
    }
    assert.equal(roleBadge('auditor'), 'Auditor · read-only')
    assert.equal(roleBadge('aicte_admin'), 'AICTE admin')
  })
})
