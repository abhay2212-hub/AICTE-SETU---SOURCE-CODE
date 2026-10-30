// Owner: Dev X
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import nacl from 'tweetnacl'
import testVectors from '../../shared/test-vectors.json' with { type: 'json' }
import {
  canonicalBytes,
  verifyCredential,
  verifyCredentialWithTimestamp,
} from '../src/lib/credential-verify.ts'
import {
  decodeCredentialEnvelope,
  extractCredentialId,
  getStatusDetails,
  resolveCredentialStatus,
  verifyCredentialWorkflow,
  type CredentialStatus,
} from '../src/pages/verifier/verify-stub.ts'

const credentialsVectors = testVectors.credentials
const TEST_SEED_HEX = credentialsVectors.test_seed_hex
const PUBLIC_KEY_B64 = credentialsVectors.public_key_b64

function getTestKeyPair() {
  const seedBytes = new Uint8Array(
    TEST_SEED_HEX.match(/.{1,2}/g)!.map((byte) => parseInt(byte, 16))
  )
  return nacl.sign.keyPair.fromSeed(seedBytes)
}

function createSignedCredential(
  payloadOverrides: Record<string, unknown> = {},
  keyPair = getTestKeyPair()
): string {
  const now = Math.floor(Date.now() / 1000)
  const basePayload: Record<string, unknown> = {
    v: 1,
    id: '92000000-0000-4000-8000-000000000088',
    iss: 'apaar-integrity-platform',
    sub: 'c15bf3f2cddbcb7b3472a0fa60b361d30193b088abf112d2136f4987ce76a55a',
    aud: 'Acme Infotech',
    claims: {
      academic_year: '2026-27',
      enrolment_status: 'student_confirmed',
      institution: 'Meghdoot Institute of Engineering',
      programme: 'B.Tech Computer Science and Engineering',
    },
    iat: now,
    exp: now + 86400,
    nonce: '00000000000000000000000000000088',
  }

  const payload = { ...basePayload, ...payloadOverrides }
  const canonical = canonicalBytes(payload)
  const sig = nacl.sign.detached(canonical, keyPair.secretKey)
  const envelope = {
    payload,
    sig: Buffer.from(sig).toString('base64'),
  }
  return Buffer.from(JSON.stringify(envelope)).toString('base64url')
}

describe('Verifier UI & Offline Verification Flow', () => {
  describe('1. Valid credential verification', () => {
    it('verifies a valid credential offline and populates claims', async () => {
      const qrText = createSignedCredential()
      let revocationChecked = false

      const outcome = await verifyCredentialWorkflow(qrText, {
        getPublicKey: async () => PUBLIC_KEY_B64,
        checkRevocation: async () => {
          revocationChecked = true
          return false
        },
      })

      assert.strictEqual(outcome.status, 'valid')
      assert.strictEqual(outcome.revoked, false)
      assert.strictEqual(outcome.result.valid, true)
      assert.strictEqual(outcome.result.offline, true)
      assert.strictEqual(revocationChecked, true)

      assert.deepStrictEqual(outcome.result.claims, {
        academic_year: '2026-27',
        enrolment_status: 'student_confirmed',
        institution: 'Meghdoot Institute of Engineering',
        programme: 'B.Tech Computer Science and Engineering',
      })

      const details = getStatusDetails(outcome.status)
      assert.strictEqual(details.title, 'Verified')
      assert.ok(details.titleClass.includes('bg-emerald-100'))
    })

    it('verifies canonical test-vector valid case with timestamp', async () => {
      const validCase = credentialsVectors.cases.find((c) => c.name === 'valid')!
      let revocationChecked = false

      const outcome = await verifyCredentialWorkflow(validCase.qr_text, {
        getPublicKey: async () => PUBLIC_KEY_B64,
        verifyOffline: (qr, pk) =>
          verifyCredentialWithTimestamp(qr, pk, validCase.verify_at),
        checkRevocation: async (id) => {
          revocationChecked = true
          return validCase.revoked_ids.includes(id)
        },
      })

      assert.strictEqual(outcome.status, 'valid')
      assert.strictEqual(outcome.revoked, false)
      assert.strictEqual(outcome.result.valid, true)
      assert.strictEqual(revocationChecked, true)
    })
  })

  describe('2. Expired credential verification', () => {
    it('identifies expired credential and NEVER performs online revocation check', async () => {
      const expiredCase = credentialsVectors.cases.find((c) => c.name === 'expired')!
      let revocationChecked = false

      const outcome = await verifyCredentialWorkflow(expiredCase.qr_text, {
        getPublicKey: async () => PUBLIC_KEY_B64,
        verifyOffline: (qr, pk) =>
          verifyCredentialWithTimestamp(qr, pk, expiredCase.verify_at),
        checkRevocation: async () => {
          revocationChecked = true
          return false
        },
      })

      assert.strictEqual(outcome.status, 'expired')
      assert.strictEqual(outcome.result.valid, false)
      assert.strictEqual(outcome.result.reason, 'expired')
      assert.strictEqual(revocationChecked, false, 'Revocation must NOT be queried when expired')

      const details = getStatusDetails(outcome.status)
      assert.strictEqual(details.title, 'Expired')
      assert.ok(details.titleClass.includes('bg-amber-100'))
    })
  })

  describe('3. Bad signature verification', () => {
    it('identifies tampered credential and NEVER performs online revocation check', async () => {
      const tamperedCase = credentialsVectors.cases.find((c) => c.name === 'tampered')!
      let revocationChecked = false

      const outcome = await verifyCredentialWorkflow(tamperedCase.qr_text, {
        getPublicKey: async () => PUBLIC_KEY_B64,
        verifyOffline: (qr, pk) =>
          verifyCredentialWithTimestamp(qr, pk, tamperedCase.verify_at),
        checkRevocation: async () => {
          revocationChecked = true
          return false
        },
      })

      assert.strictEqual(outcome.status, 'bad_signature')
      assert.strictEqual(outcome.result.valid, false)
      assert.strictEqual(outcome.result.reason, 'bad_signature')
      assert.strictEqual(revocationChecked, false, 'Revocation must NOT be queried for bad signature')

      const details = getStatusDetails(outcome.status)
      assert.strictEqual(details.title, 'Invalid signature')
      assert.ok(details.titleClass.includes('bg-red-100'))
    })

    it('fails when signed with a different key', async () => {
      const otherSeed = new Uint8Array(32).fill(7)
      const otherKeyPair = nacl.sign.keyPair.fromSeed(otherSeed)
      const qrText = createSignedCredential({}, otherKeyPair)
      let revocationChecked = false

      const outcome = await verifyCredentialWorkflow(qrText, {
        getPublicKey: async () => PUBLIC_KEY_B64,
        checkRevocation: async () => {
          revocationChecked = true
          return false
        },
      })

      assert.strictEqual(outcome.status, 'bad_signature')
      assert.strictEqual(revocationChecked, false)
    })
  })

  describe('4. Malformed QR', () => {
    const malformedInputs = [
      '',
      '   ',
      'invalid!not-base64',
      Buffer.from('not json content').toString('base64url'),
      Buffer.from(JSON.stringify({ not: 'an envelope' })).toString('base64url'),
      Buffer.from(JSON.stringify({ payload: 'not-object', sig: 'abc' })).toString('base64url'),
    ]

    for (const input of malformedInputs) {
      it(`identifies malformed input: "${input.slice(0, 20)}..."`, async () => {
        let revocationChecked = false

        const outcome = await verifyCredentialWorkflow(input, {
          getPublicKey: async () => PUBLIC_KEY_B64,
          checkRevocation: async () => {
            revocationChecked = true
            return false
          },
        })

        assert.strictEqual(outcome.status, 'malformed')
        assert.strictEqual(outcome.result.valid, false)
        assert.strictEqual(outcome.result.reason, 'malformed')
        assert.strictEqual(revocationChecked, false, 'Revocation must NOT be queried for malformed QR')

        const details = getStatusDetails(outcome.status)
        assert.strictEqual(details.title, 'Malformed')
        assert.ok(details.titleClass.includes('bg-red-100'))
      })
    }
  })

  describe('5. Revoked credential', () => {
    it('marks credential as revoked when payload.id matches revocation list', async () => {
      const revokedCase = credentialsVectors.cases.find((c) => c.name === 'revoked')!
      let revocationLookupId: string | null = null

      const outcome = await verifyCredentialWorkflow(revokedCase.qr_text, {
        getPublicKey: async () => PUBLIC_KEY_B64,
        verifyOffline: (qr, pk) =>
          verifyCredentialWithTimestamp(qr, pk, revokedCase.verify_at),
        checkRevocation: async (id) => {
          revocationLookupId = id
          return revokedCase.revoked_ids.includes(id)
        },
      })

      assert.strictEqual(outcome.status, 'revoked')
      assert.strictEqual(outcome.revoked, true)
      assert.strictEqual(outcome.result.valid, true)
      assert.strictEqual(revocationLookupId, '92000000-0000-4000-8000-000000000003')

      const details = getStatusDetails(outcome.status)
      assert.strictEqual(details.title, 'Revoked')
      assert.ok(details.titleClass.includes('bg-amber-100'))
    })
  })

  describe('6. Online revocation lookup and offline independence', () => {
    it('offline verification never makes network calls', async () => {
      // Mock global fetch to throw if called
      const originalFetch = globalThis.fetch
      globalThis.fetch = () => {
        throw new Error('fetch should NEVER be called by offline verification')
      }

      try {
        const qrText = createSignedCredential()
        const res = await verifyCredential(qrText, PUBLIC_KEY_B64)
        assert.strictEqual(res.valid, true)
        assert.strictEqual(res.offline, true)
      } finally {
        globalThis.fetch = originalFetch
      }
    })

    it('queries online revocation with payload.id ONLY after offline verification succeeds', async () => {
      const calls: string[] = []
      const qrText = createSignedCredential({ id: '92000000-0000-4000-8000-000000000042' })

      const outcome = await verifyCredentialWorkflow(qrText, {
        getPublicKey: async () => {
          calls.push('getPublicKey')
          return PUBLIC_KEY_B64
        },
        checkRevocation: async (id) => {
          calls.push(`checkRevocation:${id}`)
          return false
        },
      })

      assert.deepStrictEqual(calls, [
        'getPublicKey',
        'checkRevocation:92000000-0000-4000-8000-000000000042',
      ])
      assert.strictEqual(outcome.status, 'valid')
    })
  })

  describe('7. payload.id extraction', () => {
    it('extracts payload.id correctly from valid envelope', () => {
      const qrText = createSignedCredential({ id: '92000000-0000-4000-8000-000000000077' })
      const envelope = decodeCredentialEnvelope(qrText)
      assert.ok(envelope?.payload)
      assert.strictEqual(envelope.payload.id, '92000000-0000-4000-8000-000000000077')
      const id = extractCredentialId(qrText)
      assert.strictEqual(id, '92000000-0000-4000-8000-000000000077')
    })

    it('rejects obsolete prototype assumptions about payload.cid', () => {
      // Envelope with legacy cid instead of id
      const legacyPayload = {
        v: 1,
        cid: 'legacy-cid-value',
        iss: 'apaar-integrity-platform',
      }
      const envelope = {
        payload: legacyPayload,
        sig: Buffer.from(new Uint8Array(64)).toString('base64'),
      }
      const qrText = Buffer.from(JSON.stringify(envelope)).toString('base64url')

      const id = extractCredentialId(qrText)
      assert.strictEqual(id, null, 'Must extract payload.id, never assume payload.cid')
    })

    it('returns null for non-string, whitespace, or missing id', () => {
      const envelopeWithoutId = {
        payload: { v: 1, id: 12345 },
        sig: 'abc',
      }
      const qrText = Buffer.from(JSON.stringify(envelopeWithoutId)).toString('base64url')
      assert.strictEqual(extractCredentialId(qrText), null)
      assert.strictEqual(extractCredentialId('not-base64'), null)
      assert.strictEqual(extractCredentialId(''), null)
    })
  })

  describe('8. Unsupported credentials', () => {
    it('identifies unsupported version or issuer', async () => {
      const unsupportedQr = createSignedCredential({ v: 2, iss: 'other-issuer' })
      let revocationChecked = false

      const outcome = await verifyCredentialWorkflow(unsupportedQr, {
        getPublicKey: async () => PUBLIC_KEY_B64,
        checkRevocation: async () => {
          revocationChecked = true
          return false
        },
      })

      assert.strictEqual(outcome.status, 'unsupported')
      assert.strictEqual(outcome.result.valid, false)
      assert.strictEqual(outcome.result.reason, 'unsupported')
      assert.strictEqual(revocationChecked, false, 'Revocation must NOT be queried for unsupported QR')

      const details = getStatusDetails(outcome.status)
      assert.strictEqual(details.title, 'Unsupported')
      assert.ok(details.titleClass.includes('bg-amber-100'))
    })
  })

  describe('9. Status distinctions', () => {
    it('correctly maps all 6 statuses in resolveCredentialStatus', () => {
      const statuses: CredentialStatus[] = [
        'malformed',
        'bad_signature',
        'unsupported',
        'expired',
        'revoked',
        'valid',
      ]

      assert.strictEqual(resolveCredentialStatus({ valid: true, offline: true }, false), 'valid')
      assert.strictEqual(resolveCredentialStatus({ valid: true, offline: true }, true), 'revoked')
      assert.strictEqual(
        resolveCredentialStatus({ valid: false, reason: 'expired', offline: true }, false),
        'expired'
      )
      assert.strictEqual(
        resolveCredentialStatus({ valid: false, reason: 'bad_signature', offline: true }, false),
        'bad_signature'
      )
      assert.strictEqual(
        resolveCredentialStatus({ valid: false, reason: 'unsupported', offline: true }, false),
        'unsupported'
      )
      assert.strictEqual(
        resolveCredentialStatus({ valid: false, reason: 'malformed', offline: true }, false),
        'malformed'
      )

      for (const status of statuses) {
        const details = getStatusDetails(status)
        assert.ok(details.title.length > 0)
        assert.ok(details.titleClass.length > 0)
        assert.ok(details.panelClass.length > 0)
      }
    })
  })
})
