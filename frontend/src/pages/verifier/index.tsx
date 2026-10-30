// Owner: Dev X
import { useCallback, useEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import zxingWasmUrl from 'zxing-wasm/reader/zxing_reader.wasm?url'
import { ApiError, api } from '../../lib/api'
import type { components } from '../../lib/api-types'
import { DASHBOARD_HEADERS } from '../../lib/dashboards'
import DashboardHeader from '../../components/DashboardHeader'
import { configureZxingWasm, decodeImageFile } from './qr-decoder'
import { useQrCamera } from './use-qr-camera'
import {
  getStatusDetails,
  resolveCredentialStatus,
  verifyCredentialWorkflow,
  type VerificationResult,
} from './verify-stub'

configureZxingWasm(zxingWasmUrl)

type PublicKey = components['schemas']['PublicKey']
type RevocationList = components['schemas']['RevocationList']

const CLAIM_LABELS: Record<string, string> = {
  institution: 'Institution',
  programme: 'Programme',
  academic_year: 'Academic year',
  enrolment_status: 'Enrolment status',
  status: 'Enrolment status',
}

function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return `The verification service returned an error (${error.status}).`
  return 'We could not reach the verification service. Please try again.'
}

function formatDate(value: string | undefined): string {
  if (!value) return 'Unknown'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

function ResultCard({
  result,
  revoked,
  onReset,
}: {
  result: VerificationResult
  revoked: boolean
  onReset: () => void
}) {
  const status = resolveCredentialStatus(result, revoked)
  const { title, titleClass, panelClass, reason } = getStatusDetails(status)
  const claims = result.claims ?? {}

  const displayedClaims: { key: string; label: string; value: unknown }[] = []
  const seenLabels = new Set<string>()

  for (const [key, label] of Object.entries(CLAIM_LABELS)) {
    if (key.includes('apaar')) continue
    if (claims[key] !== undefined && claims[key] !== null && !seenLabels.has(label)) {
      seenLabels.add(label)
      displayedClaims.push({ key, label, value: claims[key] })
    }
  }

  return (
    <section data-status={status} className={`rounded-2xl border p-5 ${panelClass}`} aria-live="polite">
      <div className="flex items-center justify-between gap-3">
        <h2 className={`rounded-full px-3 py-1 text-lg font-bold ${titleClass}`}>{title}</h2>
        {result.offline && <span className="text-sm font-semibold text-slate-700">Checked offline</span>}
      </div>
      {reason && <p className="mt-4 text-base font-medium text-slate-800">{reason}</p>}
      {status === 'valid' && (
        <div className="mt-5 space-y-3">
          {displayedClaims.length > 0 ? (
            displayedClaims.map(({ key, label, value }) => (
              <div key={key} className="rounded-xl bg-white/80 p-3">
                <dt className="text-sm font-semibold text-slate-500">{label}</dt>
                <dd className="mt-1 break-words text-lg text-slate-900">{String(value)}</dd>
              </div>
            ))
          ) : (
            <p className="text-base text-slate-700">No shared facts were included.</p>
          )}
          <p className="pt-2 text-sm text-slate-700">Expires {formatDate(result.expiresAt)}</p>
        </div>
      )}
      <p className="mt-6 border-t border-slate-300/60 pt-4 text-sm text-slate-700">
        Verified with the institution&apos;s digital signature. No student data was looked up.
      </p>
      <button
        type="button"
        onClick={onReset}
        className="mt-5 w-full rounded-xl bg-slate-900 px-4 py-3 text-base font-bold text-white hover:bg-slate-700"
      >
        Verify another
      </button>
    </section>
  )
}

export default function VerifierPage() {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [qrText, setQrText] = useState('')
  const [result, setResult] = useState<VerificationResult | null>(null)
  const [revoked, setRevoked] = useState(false)
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [imageMessage, setImageMessage] = useState<string | null>(null)
  const [readingImage, setReadingImage] = useState(false)

  const verifyText = useCallback(async (value: string) => {
    const text = value.trim()
    if (!text) {
      setError('Paste the QR text or scan a credential before verifying.')
      return
    }
    setChecking(true)
    setError(null)
    setResult(null)
    setRevoked(false)
    try {
      const outcome = await verifyCredentialWorkflow(text, {
        getPublicKey: async () => {
          const key = await api<PublicKey>('/credentials/public-key')
          return key.public_key_b64
        },
        checkRevocation: async (credentialId: string) => {
          const revocations = await api<RevocationList>('/credentials/revocations')
          return revocations.revoked.some((item) => item.credential_id === credentialId)
        },
      })
      setRevoked(outcome.revoked)
      setResult(outcome.result)
    } catch (verificationError) {
      setError(getErrorMessage(verificationError))
    } finally {
      setChecking(false)
    }
  }, [])

  const handleDecoded = useCallback(
    (text: string) => {
      setQrText(text)
      setImageMessage(null)
      void verifyText(text)
    },
    [verifyText],
  )

  const camera = useQrCamera(videoRef, handleDecoded)
  const { start: startCamera, stop: stopCamera } = camera

  // The camera runs whenever the scan view is showing; it stops itself after a successful decode.
  useEffect(() => {
    if (result) return
    void startCamera()
    return stopCamera
  }, [result, startCamera, stopCamera])

  async function handleVerify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await verifyText(qrText)
  }

  async function handleImage(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setReadingImage(true)
    setImageMessage(null)
    try {
      const text = await decodeImageFile(file)
      if (text) {
        navigator.vibrate?.(80)
        stopCamera()
        handleDecoded(text)
      } else {
        setImageMessage('No QR code was found in that image. Use a sharp photo where the QR fills most of the picture.')
      }
    } catch {
      setImageMessage('That file could not be read. Choose a PNG or JPG image.')
    } finally {
      setReadingImage(false)
    }
  }

  function reset() {
    setResult(null)
    setRevoked(false)
    setError(null)
    setImageMessage(null)
    setQrText('')
  }

  // Same header for every role, and nothing here needs a login.
  const header = <DashboardHeader header={DASHBOARD_HEADERS.verifier} eyebrow="Verifier" />

  if (result) {
    return (
      <div className="space-y-6">
        {header}
        <section className="mx-auto max-w-lg space-y-5">
          <h2 className="text-3xl font-bold text-slate-900">Credential result</h2>
          <ResultCard result={result} revoked={revoked} onReset={reset} />
        </section>
      </div>
    )
  }

  const cameraLive = camera.status === 'scanning' || camera.status === 'starting'

  return (
    <div className="space-y-6">
      {header}
      <section className="mx-auto max-w-lg space-y-6">
        <div className="space-y-3 overflow-hidden rounded-2xl border border-slate-200 bg-white p-3">
          <div className={`relative aspect-[4/3] overflow-hidden rounded-xl bg-slate-900 ${cameraLive ? '' : 'hidden'}`}>
            <video
              ref={videoRef}
              muted
              playsInline
              autoPlay
              aria-label="Camera preview"
              className="h-full w-full object-cover"
            />
            <div aria-hidden="true" className="pointer-events-none absolute inset-0 flex items-center justify-center">
              <div className="aspect-square h-[85%] rounded-2xl border-4 border-white/80" />
            </div>
            <p className="pointer-events-none absolute inset-x-0 bottom-0 bg-slate-900/70 px-3 py-2 text-center text-sm font-semibold text-white">
              {camera.status === 'starting' ? 'Starting camera…' : 'Hold the QR flat, fill most of the frame'}
            </p>
          </div>
          {checking && <p className="px-1 text-base font-semibold text-slate-700">QR read. Checking…</p>}
          {camera.error && <p role="status" className="px-1 text-base text-slate-700">{camera.error}</p>}
          <div className="flex flex-wrap gap-2">
            {cameraLive ? (
              <>
                {camera.torchSupported && (
                  <button
                    type="button"
                    onClick={() => void camera.toggleTorch()}
                    aria-pressed={camera.torchOn}
                    className="rounded-xl border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50"
                  >
                    {camera.torchOn ? 'Torch off' : 'Torch on'}
                  </button>
                )}
                {camera.canSwitchCamera && (
                  <button
                    type="button"
                    onClick={camera.switchCamera}
                    className="rounded-xl border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50"
                  >
                    Switch camera
                  </button>
                )}
              </>
            ) : (
              !checking && (
                <button
                  type="button"
                  onClick={() => void startCamera()}
                  className="rounded-xl border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50"
                >
                  {camera.status === 'error' ? 'Try camera again' : 'Start camera'}
                </button>
              )
            )}
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={readingImage || checking}
              className="rounded-xl border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {readingImage ? 'Reading image…' : 'Scan from image'}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg"
              onChange={(event) => void handleImage(event)}
              className="hidden"
            />
          </div>
          {imageMessage && <p role="alert" className="px-1 text-base text-red-700">{imageMessage}</p>}
        </div>
        <form onSubmit={handleVerify} className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4">
          <label htmlFor="qr-text" className="text-base font-bold text-slate-900">
            Paste QR text
          </label>
          <textarea
            id="qr-text"
            value={qrText}
            onChange={(event) => setQrText(event.target.value)}
            rows={5}
            placeholder="Paste the credential QR text here"
            className="w-full resize-y rounded-xl border border-slate-300 p-3 font-mono text-sm outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
          />
          {error && <p role="alert" className="text-base text-red-700">{error}</p>}
          <button
            type="submit"
            disabled={checking || !qrText.trim()}
            className="w-full rounded-xl bg-blue-700 px-4 py-3 text-base font-bold text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {checking ? 'Checking…' : 'Verify'}
          </button>
        </form>
      </section>
    </div>
  )
}
