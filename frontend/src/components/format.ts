// Owner: Dev D
// Plain-text formatting shared by the institution and AICTE dashboards: API errors, actor
// labels and review evidence as sentences. No imports, so node --test can load it directly.

/** Institution name and AICTE code, looked up by id or code. */
export interface InstitutionRef {
  id: string
  name: string
  aicte_code: string
}

export type InstitutionLookup = (idOrCode: string) => InstitutionRef | undefined

const ROLE_LABELS: Record<string, string> = {
  aicte_admin: 'AICTE admin',
  auditor: 'Auditor',
  institution_admin: 'Institution admin',
  institution_operator: 'Institution operator',
  student: 'Student',
  verifier: 'Verifier',
  system: 'System',
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Server error as "CODE: message" when the API sent a code, else its message or status. */
export function apiErrorMessage(error: unknown): string {
  if (isRecord(error) && typeof error.status === 'number' && 'body' in error) {
    const { status, body } = error
    const detail = isRecord(body) && 'detail' in body ? body.detail : body
    if (isRecord(detail)) {
      const message = typeof detail.message === 'string' ? detail.message : ''
      const code = typeof detail.code === 'string' ? detail.code : ''
      if (code || message) return [code, message].filter(Boolean).join(': ')
    }
    if (Array.isArray(detail) && detail.length) {
      // FastAPI request validation: [{loc: [...], msg}].
      const parts = detail.map((item) => {
        if (!isRecord(item)) return String(item)
        const loc = Array.isArray(item.loc) ? item.loc.filter((p) => p !== 'body').join('.') : ''
        return loc ? `${loc}: ${String(item.msg)}` : String(item.msg)
      })
      return `VALIDATION_ERROR: ${parts.join('; ')}`
    }
    if (typeof detail === 'string' && detail.trim()) return `HTTP ${status}: ${detail.trim()}`
    return `HTTP ${status}: the server returned no error details.`
  }
  if (error instanceof TypeError) return 'NETWORK_ERROR: could not reach the API.'
  if (error instanceof Error && error.message) return error.message
  return 'An unexpected error occurred.'
}

/** "demo-aicte_admin" -> "AICTE admin (demo)"; a user UUID -> "User 1a2b3c4d". */
export function actorLabel(actor: string | null | undefined): string {
  if (!actor) return '—'
  const demo = actor.startsWith('demo-')
  const key = demo ? actor.slice('demo-'.length) : actor
  const role = ROLE_LABELS[key]
  if (role) return demo ? `${role} (demo)` : role
  if (demo) return `${key.replaceAll('_', ' ')} (demo)`
  if (/^[0-9a-f]{8}-[0-9a-f]{4}-/i.test(actor)) return `User ${actor.slice(0, 8)}`
  return actor
}

/** Masks anything that looks like a raw 12-digit APAAR ID; masked values pass through. */
export function maskApaar(text: string): string {
  return text.replace(/\b(\d{4})[- ]?(\d{4})[- ]?(\d{4})\b/g, 'XXXX-XXXX-$3')
}

export function institutionLabel(
  idOrCode: unknown,
  lookup: InstitutionLookup,
  withCode = true,
): string {
  if (typeof idOrCode !== 'string' || !idOrCode) return 'another institution'
  const found = lookup(idOrCode)
  if (!found) return /^[0-9a-f]{8}-/i.test(idOrCode) ? `institution ${idOrCode.slice(0, 8)}` : idOrCode
  return withCode ? `${found.name} (${found.aicte_code})` : found.name
}

/** First word of an institution name ("Shadow Institute of Technology" -> "Shadow"). */
export function shortInstitutionName(idOrCode: unknown, lookup: InstitutionLookup): string {
  const full = institutionLabel(idOrCode, lookup, false)
  return lookup(String(idOrCode)) ? full.split(' ')[0] : full
}

function humanKey(key: string): string {
  const text = key.replaceAll('_', ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

function plain(value: unknown): string {
  if (value == null) return 'not recorded'
  if (Array.isArray(value)) return value.map(plain).join(', ')
  if (isRecord(value)) {
    return Object.entries(value)
      .map(([k, v]) => `${humanKey(k).toLowerCase()} ${plain(v)}`)
      .join(', ')
  }
  return maskApaar(String(value))
}

function rowPrefix(evidence: Record<string, unknown>): string {
  const rows = evidence.row_numbers ?? evidence.row_number ?? evidence.rows_affected
  if (Array.isArray(rows) && rows.length) {
    return `${rows.length === 1 ? 'Row' : 'Rows'} ${rows.join(', ')}: `
  }
  if (typeof rows === 'number') return `Row ${rows}: `
  return ''
}

function dice(value: unknown): string {
  return typeof value === 'number' ? value.toFixed(2) : String(value)
}

// Keys that are internal references, already used in a sentence, or would only repeat one.
const SKIP_KEYS = new Set([
  'rule_code',
  'code',
  'batch_id',
  'programme_id',
  'pair_key',
  'student_a_id',
  'student_b_id',
  'student_id',
  'admission_id',
  'blind_match_case_id',
  'row_number',
  'row_numbers',
  'rows_affected',
  'reason',
])

/**
 * Review-case or signal evidence as readable sentences. `code` is the signal code or the
 * review-case kind; `institutionId` is the institution the evidence belongs to.
 */
export function evidenceSentences(
  code: string,
  evidence: Record<string, unknown> | null | undefined,
  lookup: InstitutionLookup,
  institutionId?: string,
): string[] {
  const ev = evidence ?? {}
  const rows = rowPrefix(ev)
  const n = (key: string) => (typeof ev[key] === 'number' ? (ev[key] as number) : undefined)
  const kind = String(ev.rule_code ?? code).toUpperCase()
  const sentences: string[] = []

  if (kind === 'DUP_CROSS_INSTITUTION') {
    const other = ev.other_institution_code ?? ev.other_institution_id
    sentences.push(
      `${rows}APAAR ${plain(ev.apaar_id_masked ?? 'ID')} is also enrolled at ${institutionLabel(other, lookup)}`,
    )
  } else if (kind === 'INTAKE_OVERRUN') {
    const programme = ev.programme ?? ev.programme_code ?? 'A programme'
    const pool = ev.pool ? ` ${plain(ev.pool)} pool` : ''
    const admitted = n('used') ?? n('admitted_total')
    const approved = n('approved') ?? n('approved_total')
    const over = n('overrun_by') ?? n('overrun') ?? (admitted != null && approved != null ? admitted - approved : undefined)
    const year = ev.academic_year ? ` in ${plain(ev.academic_year)}` : ''
    sentences.push(
      admitted != null && approved != null
        ? `${rows}${plain(programme)}${pool}: ${admitted} admitted against ${approved} approved seats${over ? ` (${over} over)` : ''}${year}`
        : `${rows}${plain(programme)}${pool} admitted more students than its approved seats${year}`,
    )
  } else if (kind === 'BLIND_MATCH' || kind === 'FUZZY_MATCH_CANDIDATE') {
    const a = ev.institution_a_id ?? institutionId
    const b = ev.institution_b_id ?? ev.other_institution_id
    if (a && b) {
      sentences.push(
        `${rows}Possibly the same student at ${institutionLabel(a, lookup, false)} and ${institutionLabel(b, lookup, false)}`,
      )
    } else {
      sentences.push(`${rows}Possibly the same student enrolled at another institution`)
    }
    if (ev.dice != null || ev.similarity_score != null) {
      sentences.push(`Blind Match Dice similarity ${dice(ev.dice ?? ev.similarity_score)} on encrypted identity fields`)
    }
    if (Array.isArray(ev.matched_on) && ev.matched_on.length) {
      sentences.push(`Matched on ${plain(ev.matched_on)}`)
    }
    if (ev.programme_a || ev.programme_b) {
      sentences.push(
        `Programmes: ${plain(ev.programme_a ?? '?')} (${plain(ev.academic_year_a ?? '?')}) and ${plain(ev.programme_b ?? '?')} (${plain(ev.academic_year_b ?? '?')})`,
      )
    }
  } else if (kind === 'SHARED_CONTACT_CLUSTER') {
    const size = n('cluster_size') ?? n('size') ?? (Array.isArray(ev.row_numbers) ? ev.row_numbers.length : undefined)
    sentences.push(
      size != null
        ? `${size} students share one phone number or email address`
        : `${rows}Several students share one phone number or email address`,
    )
  } else if (kind === 'BACKDATED_ENTRY') {
    if (typeof ev.reason === 'string') sentences.push(`${rows}${maskApaar(ev.reason)}`)
    else if (n('rows') != null) sentences.push(`${n('rows')} admissions were entered well after their admission date`)
    else sentences.push(`${rows}Admission entered well after its admission date`)
  } else if (kind === 'DISPUTE') {
    const channel = ev.channel ? ` via ${plain(ev.channel)}` : ''
    sentences.push(
      ev.statement ? `Student disputes this admission${channel}: "${plain(ev.statement)}"` : `Student disputes this admission${channel}`,
    )
  } else if (typeof ev.reason === 'string') {
    sentences.push(`${rows}${maskApaar(ev.reason)}`)
  }

  const handled: Record<string, string[]> = {
    DUP_CROSS_INSTITUTION: ['apaar_id_masked', 'other_institution_code', 'other_institution_id'],
    INTAKE_OVERRUN: ['programme', 'programme_code', 'pool', 'used', 'admitted_total', 'approved', 'approved_total', 'overrun_by', 'overrun', 'academic_year'],
    BLIND_MATCH: ['institution_a_id', 'institution_b_id', 'other_institution_id', 'dice', 'similarity_score', 'matched_on', 'programme_a', 'programme_b', 'academic_year_a', 'academic_year_b'],
    SHARED_CONTACT_CLUSTER: ['cluster_size', 'size'],
    BACKDATED_ENTRY: ['rows', 'delay', 'admission_date'],
    DISPUTE: ['statement', 'channel'],
  }
  handled.FUZZY_MATCH_CANDIDATE = handled.BLIND_MATCH
  const used = new Set([...SKIP_KEYS, ...(handled[kind] ?? [])])

  const rest = Object.entries(ev).filter(([key, value]) => !used.has(key) && value != null && value !== '')
  if (sentences.length === 0 && rows) sentences.push(`${rows}flagged as ${kind.replaceAll('_', ' ').toLowerCase()}`)
  for (const [key, value] of rest) {
    const label = humanKey(key)
    sentences.push(
      /institution/.test(key) && typeof value === 'string'
        ? `${label}: ${institutionLabel(value, lookup)}`
        : `${label}: ${plain(value)}`,
    )
  }
  if (sentences.length === 0) sentences.push('No further evidence was recorded.')
  return sentences
}
