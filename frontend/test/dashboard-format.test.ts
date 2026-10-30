// Owner: Dev D
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  actorLabel,
  apiErrorMessage,
  evidenceSentences,
  maskApaar,
  shortInstitutionName,
  type InstitutionRef,
} from '../src/components/format.ts'

const institutions: InstitutionRef[] = [
  { id: 'i-2', name: 'Narmada Valley College of Technology', aicte_code: '1-9999002' },
  { id: 'i-3', name: 'Shadow Institute of Technology', aicte_code: '1-9999003' },
]
const lookup = (key: string) => institutions.find((i) => i.id === key || i.aicte_code === key)

describe('apiErrorMessage', () => {
  it('shows the server code and message', () => {
    const error = {
      status: 422,
      body: { detail: { code: 'INVALID_EDIT_VALUE', field: 'dob', message: 'dob is in the future.' } },
    }
    assert.equal(apiErrorMessage(error), 'INVALID_EDIT_VALUE: dob is in the future.')
  })

  it('formats FastAPI validation errors and plain details', () => {
    const validation = { status: 422, body: { detail: [{ loc: ['body', 'reason'], msg: 'Field required' }] } }
    assert.equal(apiErrorMessage(validation), 'VALIDATION_ERROR: reason: Field required')
    assert.equal(apiErrorMessage({ status: 403, body: { detail: 'Forbidden' } }), 'HTTP 403: Forbidden')
    assert.equal(apiErrorMessage(new TypeError('Failed to fetch')), 'NETWORK_ERROR: could not reach the API.')
  })
})

describe('actorLabel', () => {
  it('turns demo actors into readable roles', () => {
    assert.equal(actorLabel('demo-aicte_admin'), 'AICTE admin (demo)')
    assert.equal(actorLabel('demo-institution_operator'), 'Institution operator (demo)')
    assert.equal(actorLabel('9f1c2d3e-0000-4000-8000-000000000001'), 'User 9f1c2d3e')
    assert.equal(actorLabel(null), '—')
  })
})

describe('evidenceSentences', () => {
  it('describes a cross-institution APAAR duplicate with the masked ID', () => {
    const sentences = evidenceSentences(
      'signal',
      {
        rule_code: 'DUP_CROSS_INSTITUTION',
        batch_id: 'b-1',
        row_number: 32,
        apaar_id_masked: 'XXXX-XXXX-0188',
        other_institution_code: '1-9999002',
      },
      lookup,
    )
    assert.deepEqual(sentences, [
      'Row 32: APAAR XXXX-XXXX-0188 is also enrolled at Narmada Valley College of Technology (1-9999002)',
    ])
  })

  it('describes an intake overrun and a blind match', () => {
    assert.deepEqual(
      evidenceSentences('intake_overrun', { programme_code: 'UG-CSE', approved_total: 60, admitted_total: 71, overrun: 11 }, lookup),
      ['UG-CSE: 71 admitted against 60 approved seats (11 over)'],
    )
    const match = evidenceSentences('blind_match', { dice: 0.93, other_institution_id: 'i-2' }, lookup, 'i-3')
    assert.equal(match[0], 'Possibly the same student at Shadow Institute of Technology and Narmada Valley College of Technology')
    assert.match(match[1], /Dice similarity 0\.93/)
    assert.equal(shortInstitutionName('i-3', lookup), 'Shadow')
  })

  it('never shows a raw APAAR ID', () => {
    assert.equal(maskApaar('id 123456780188'), 'id XXXX-XXXX-0188')
    const sentences = evidenceSentences('signal', { note: 'APAAR 1234-5678-0188' }, lookup)
    assert.deepEqual(sentences, ['Note: APAAR XXXX-XXXX-0188'])
  })
})
