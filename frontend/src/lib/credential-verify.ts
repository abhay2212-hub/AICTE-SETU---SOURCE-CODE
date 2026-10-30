// Owner: Dev A
/**
 * Offline Ed25519 credential verification (shared/credentials.md).
 *
 * Verifies signed student credentials entirely offline without HTTP requests,
 * database queries, or server dependencies.
 */

import nacl from 'tweetnacl'

export interface VerificationResult {
  valid: boolean
  reason?: string
  claims?: Record<string, unknown>
  expiresAt?: string
  offline: boolean
}

const B64_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
const B64_LOOKUP = new Uint8Array(256)
B64_LOOKUP.fill(255)

for (let i = 0; i < B64_CHARS.length; i++) {
  B64_LOOKUP[B64_CHARS.charCodeAt(i)] = i
}
// Support Base64URL characters without requiring string replacements
B64_LOOKUP['-'.charCodeAt(0)] = 62
B64_LOOKUP['_'.charCodeAt(0)] = 63

/**
 * Decodes standard Base64 or Base64URL to Uint8Array.
 * Works uniformly across browser and Node.js environments.
 * Returns null if the input string is malformed or contains invalid characters.
 */
export function decodeBase64ToBytes(input: string): Uint8Array | null {
  const clean = input.replace(/\s+/g, '')
  let len = clean.length
  if (len === 0) return new Uint8Array(0)

  // Strip trailing padding '=' for byte count calculation
  while (len > 0 && clean[len - 1] === '=') {
    len--
  }

  // Base64 requires valid quantum: length % 4 cannot be 1
  if (len % 4 === 1) {
    return null
  }

  const byteLen = Math.floor((len * 3) / 4)
  const bytes = new Uint8Array(byteLen)

  let byteIndex = 0
  let buffer = 0
  let bits = 0

  for (let i = 0; i < len; i++) {
    const val = B64_LOOKUP[clean.charCodeAt(i)]
    if (val === 255) {
      return null
    }
    buffer = (buffer << 6) | val
    bits += 6
    if (bits >= 8) {
      bits -= 8
      bytes[byteIndex++] = (buffer >> bits) & 0xff
    }
  }

  return bytes
}

/**
 * Decodes Base64 or Base64URL into a UTF-8 string.
 * Returns null if decoding fails or the byte sequence is not valid UTF-8.
 */
export function decodeBase64ToUtf8(input: string): string | null {
  const bytes = decodeBase64ToBytes(input)
  if (!bytes) return null
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes)
  } catch {
    return null
  }
}

/**
 * Serializes a JavaScript value to canonical JSON string matching
 * Python's `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.
 *
 * Keys are recursively sorted by Unicode code point order. Delimiters have no whitespace.
 * Non-ASCII characters are preserved directly in UTF-8 without \u escaping.
 */
export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value)
  }
  if (Array.isArray(value)) {
    return '[' + value.map(canonicalJson).join(',') + ']'
  }
  const obj = value as Record<string, unknown>
  const keys = Object.keys(obj).sort()
  const entries = keys.map((k) => JSON.stringify(k) + ':' + canonicalJson(obj[k]))
  return '{' + entries.join(',') + '}'
}

/**
 * Returns canonical UTF-8 bytes for an object.
 */
export function canonicalBytes(value: Record<string, unknown>): Uint8Array {
  return new TextEncoder().encode(canonicalJson(value))
}

/**
 * Internal verification function allowing a custom timestamp for deterministic test validation.
 */
export function verifyCredentialWithTimestamp(
  qrText: string,
  publicKeyB64: string,
  nowSeconds: number
): VerificationResult {
  try {
    const trimmed = qrText.trim()
    if (!trimmed) {
      return { valid: false, reason: 'malformed', offline: true }
    }

    // Step 1: Decode envelope from Base64URL
    const envelopeUtf8 = decodeBase64ToUtf8(trimmed)
    if (!envelopeUtf8) {
      return { valid: false, reason: 'malformed', offline: true }
    }

    let parsed: unknown
    try {
      parsed = JSON.parse(envelopeUtf8)
    } catch {
      return { valid: false, reason: 'malformed', offline: true }
    }

    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      return { valid: false, reason: 'malformed', offline: true }
    }

    const envelope = parsed as { payload?: unknown; sig?: unknown }
    if (
      typeof envelope.payload !== 'object' ||
      envelope.payload === null ||
      Array.isArray(envelope.payload) ||
      typeof envelope.sig !== 'string'
    ) {
      return { valid: false, reason: 'malformed', offline: true }
    }

    const signatureBytes = decodeBase64ToBytes(envelope.sig)
    if (!signatureBytes || signatureBytes.length !== 64) {
      return { valid: false, reason: 'malformed', offline: true }
    }

    const publicKeyBytes = decodeBase64ToBytes(publicKeyB64)
    if (!publicKeyBytes || publicKeyBytes.length !== 32) {
      return { valid: false, reason: 'malformed', offline: true }
    }

    const payload = envelope.payload as Record<string, unknown>

    // Step 2: Verify Ed25519 signature over canonical payload bytes
    const canonical = canonicalBytes(payload)
    const isSigValid = nacl.sign.detached.verify(canonical, signatureBytes, publicKeyBytes)
    if (!isSigValid) {
      return { valid: false, reason: 'bad_signature', offline: true }
    }

    // Step 3: Check version and issuer
    if (payload.v !== 1 || payload.iss !== 'apaar-integrity-platform') {
      return { valid: false, reason: 'unsupported', offline: true }
    }

    // Step 4: Validate expiration
    const exp = typeof payload.exp === 'number' ? payload.exp : Number(payload.exp)
    if (!Number.isFinite(exp)) {
      return { valid: false, reason: 'malformed', offline: true }
    }

    const expiresAt = new Date(exp * 1000).toISOString()
    if (nowSeconds >= exp) {
      return { valid: false, reason: 'expired', expiresAt, offline: true }
    }

    // Step 5: Return valid result with claims
    const claims =
      typeof payload.claims === 'object' && payload.claims !== null && !Array.isArray(payload.claims)
        ? (payload.claims as Record<string, unknown>)
        : {}

    return {
      valid: true,
      claims,
      expiresAt,
      offline: true,
    }
  } catch {
    return { valid: false, reason: 'malformed', offline: true }
  }
}

/**
 * Offline credential verification function.
 * Matches project specification in shared/credentials.md.
 */
export async function verifyCredential(
  qrText: string,
  publicKeyB64: string
): Promise<{
  valid: boolean
  reason?: string
  claims?: Record<string, unknown>
  expiresAt?: string
  offline: boolean
}> {
  const nowSeconds = Math.floor(Date.now() / 1000)
  return verifyCredentialWithTimestamp(qrText, publicKeyB64, nowSeconds)
}
