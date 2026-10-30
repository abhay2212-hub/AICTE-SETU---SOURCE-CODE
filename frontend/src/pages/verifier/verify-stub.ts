// Owner: Dev X
// Compatibility re-export and verifier workflow helper module

export type { VerificationResult } from '../../lib/credential-verify.ts'
export {
  verifyCredential,
  verifyCredentialWithTimestamp,
  decodeBase64ToUtf8,
  decodeBase64ToBytes,
  canonicalJson,
  canonicalBytes,
} from '../../lib/credential-verify.ts'

import { decodeBase64ToUtf8, verifyCredential, type VerificationResult } from '../../lib/credential-verify.ts'

export type CredentialStatus =
  | 'malformed'
  | 'bad_signature'
  | 'unsupported'
  | 'expired'
  | 'revoked'
  | 'valid'

export interface CredentialEnvelope {
  payload?: Record<string, unknown>
  sig?: string
}

/**
 * Decodes the base64url QR envelope into payload and signature.
 * Uses decodeBase64ToUtf8 from credential-verify to avoid duplicate decoding logic.
 */
export function decodeCredentialEnvelope(qrText: string): CredentialEnvelope | null {
  const trimmed = qrText.trim()
  if (!trimmed) return null
  const decoded = decodeBase64ToUtf8(trimmed)
  if (!decoded) return null
  try {
    const parsed: unknown = JSON.parse(decoded)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      return null
    }
    const env = parsed as { payload?: unknown; sig?: unknown }
    const payload =
      typeof env.payload === 'object' && env.payload !== null && !Array.isArray(env.payload)
        ? (env.payload as Record<string, unknown>)
        : undefined
    const sig = typeof env.sig === 'string' ? env.sig : undefined
    return { payload, sig }
  } catch {
    return null
  }
}

/**
 * Extracts payload.id from the credential QR envelope.
 * Returns null if the envelope is malformed or payload.id is missing/non-string.
 */
export function extractCredentialId(qrText: string): string | null {
  const envelope = decodeCredentialEnvelope(qrText)
  const id = envelope?.payload?.id
  return typeof id === 'string' && id.trim().length > 0 ? id.trim() : null
}

/**
 * Resolves one of the 6 canonical credential verification statuses:
 * 'malformed' | 'bad_signature' | 'unsupported' | 'expired' | 'revoked' | 'valid'
 */
export function resolveCredentialStatus(
  result: VerificationResult,
  revoked: boolean
): CredentialStatus {
  if (revoked) return 'revoked'
  if (result.reason === 'expired') return 'expired'
  if (result.reason === 'bad_signature') return 'bad_signature'
  if (result.reason === 'unsupported') return 'unsupported'
  if (result.reason === 'malformed') return 'malformed'
  if (!result.valid) return 'malformed'
  return 'valid'
}

/**
 * UI presentation details corresponding to each credential verification status.
 */
export function getStatusDetails(status: CredentialStatus, customReason?: string) {
  switch (status) {
    case 'valid':
      return {
        title: 'Verified',
        titleClass: 'bg-emerald-100 text-emerald-800',
        panelClass: 'border-emerald-200 bg-emerald-50',
        reason: '',
      }
    case 'revoked':
      return {
        title: 'Revoked',
        titleClass: 'bg-amber-100 text-amber-900',
        panelClass: 'border-amber-200 bg-amber-50',
        reason: customReason ?? 'This credential was revoked by the student.',
      }
    case 'expired':
      return {
        title: 'Expired',
        titleClass: 'bg-amber-100 text-amber-900',
        panelClass: 'border-amber-200 bg-amber-50',
        reason: customReason ?? 'This credential is past its expiry time.',
      }
    case 'bad_signature':
      return {
        title: 'Invalid signature',
        titleClass: 'bg-red-100 text-red-800',
        panelClass: 'border-red-200 bg-red-50',
        reason: customReason ?? 'The cryptographic signature on this credential is invalid.',
      }
    case 'malformed':
      return {
        title: 'Malformed',
        titleClass: 'bg-red-100 text-red-800',
        panelClass: 'border-red-200 bg-red-50',
        reason: customReason ?? 'This QR code is not a recognised credential format.',
      }
    case 'unsupported':
      return {
        title: 'Unsupported',
        titleClass: 'bg-amber-100 text-amber-900',
        panelClass: 'border-amber-200 bg-amber-50',
        reason: customReason ?? 'This credential version or issuer is not supported.',
      }
  }
}

export interface VerificationWorkflowResult {
  result: VerificationResult
  status: CredentialStatus
  revoked: boolean
}

/**
 * Orchestrates credential verification workflow:
 * 1. Fetches platform public key.
 * 2. Runs verifyCredential (strictly offline, zero network requests).
 * 3. Stops immediately if offline verification fails (never calls online revocation on failed credentials).
 * 4. Only after offline verification succeeds: decodes QR envelope, extracts payload.id, and checks online revocation.
 */
export async function verifyCredentialWorkflow(
  qrText: string,
  options: {
    getPublicKey: () => Promise<string>
    checkRevocation: (credentialId: string) => Promise<boolean>
    verifyOffline?: (qrText: string, publicKeyB64: string) => Promise<VerificationResult> | VerificationResult
  }
): Promise<VerificationWorkflowResult> {
  const text = qrText.trim()
  if (!text) {
    const malformedResult: VerificationResult = {
      valid: false,
      reason: 'malformed',
      offline: true,
    }
    return {
      result: malformedResult,
      status: 'malformed',
      revoked: false,
    }
  }

  // 1. Fetch public key
  const publicKeyB64 = await options.getPublicKey()

  // 2. Perform offline cryptographic verification (single source of truth)
  const verifyFn = options.verifyOffline ?? verifyCredential
  const verification = await verifyFn(text, publicKeyB64)

  // 3. If offline verification failed, stop immediately without making online revocation requests
  if (!verification.valid) {
    const status = resolveCredentialStatus(verification, false)
    return {
      result: verification,
      status,
      revoked: false,
    }
  }

  // 4. Offline verification succeeded.
  // Extract payload.id from QR envelope and query revocation list
  const credentialId = extractCredentialId(text)
  let isRevoked = false
  if (credentialId) {
    isRevoked = await options.checkRevocation(credentialId)
  }

  const status = resolveCredentialStatus(verification, isRevoked)
  return {
    result: verification,
    status,
    revoked: isRevoked,
  }
}
