// Owner: Dev X
// Rear-camera QR scanning: full-frame decode at ~9 attempts per second, torch and camera switching.

import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'
import { decodeCanvas } from './qr-decoder'

export type CameraStatus = 'off' | 'starting' | 'scanning' | 'error'

const SCAN_INTERVAL_MS = 110

// Torch and focusMode are not in the DOM lib types yet.
interface ExtendedCapabilities extends MediaTrackCapabilities {
  torch?: boolean
  focusMode?: string[]
}

function capabilitiesOf(track: MediaStreamTrack): ExtendedCapabilities {
  return (track.getCapabilities?.() ?? {}) as ExtendedCapabilities
}

function cameraUnavailableReason(): string | null {
  if (!window.isSecureContext) {
    return 'The camera only works over HTTPS. Use "Scan from image" or paste the QR text below.'
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    return 'This browser cannot open a camera. Use "Scan from image" or paste the QR text below.'
  }
  return null
}

function describeCameraError(error: unknown): string {
  const name = error instanceof DOMException ? error.name : ''
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return 'Camera permission was denied. Allow camera access in your browser settings, or use "Scan from image" or paste the QR text below.'
  }
  if (name === 'NotFoundError' || name === 'OverconstrainedError') {
    return 'No camera was found on this device. Use "Scan from image" or paste the QR text below.'
  }
  if (name === 'NotReadableError') {
    return 'The camera is being used by another app. Close it and try again, or use "Scan from image".'
  }
  return 'The camera could not be started. Use "Scan from image" or paste the QR text below.'
}

async function openCamera(deviceId: string | undefined): Promise<MediaStream> {
  const target: MediaTrackConstraints = deviceId
    ? { deviceId: { exact: deviceId } }
    : { facingMode: { ideal: 'environment' } }
  try {
    return await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: { ...target, width: { ideal: 1920 }, height: { ideal: 1080 } },
    })
  } catch (error) {
    if (error instanceof DOMException && (error.name === 'NotAllowedError' || error.name === 'SecurityError')) {
      throw error
    }
    return navigator.mediaDevices.getUserMedia({
      audio: false,
      video: { ...target, width: { ideal: 1280 }, height: { ideal: 720 } },
    })
  }
}

async function enableContinuousFocus(track: MediaStreamTrack): Promise<void> {
  if (!capabilitiesOf(track).focusMode?.includes('continuous')) return
  try {
    await track.applyConstraints({ advanced: [{ focusMode: 'continuous' } as MediaTrackConstraintSet] })
  } catch {
    // Focus is a nice-to-have; scanning still works with the default mode.
  }
}

export function useQrCamera(videoRef: RefObject<HTMLVideoElement | null>, onDecoded: (text: string) => void) {
  const [status, setStatus] = useState<CameraStatus>('off')
  const [error, setError] = useState<string | null>(null)
  const [torchSupported, setTorchSupported] = useState(false)
  const [torchOn, setTorchOn] = useState(false)
  const [cameraIds, setCameraIds] = useState<string[]>([])
  const sessionRef = useRef(0)
  const streamRef = useRef<MediaStream | null>(null)
  const timerRef = useRef<number | undefined>(undefined)
  const deviceIdRef = useRef<string | undefined>(undefined)
  const onDecodedRef = useRef(onDecoded)

  useEffect(() => {
    onDecodedRef.current = onDecoded
  }, [onDecoded])

  const stop = useCallback(() => {
    sessionRef.current += 1
    window.clearTimeout(timerRef.current)
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
    setTorchSupported(false)
    setTorchOn(false)
    setStatus((current) => (current === 'error' ? current : 'off'))
  }, [videoRef])

  const start = useCallback(
    async (deviceId?: string) => {
      stop()
      const session = sessionRef.current
      const unavailable = cameraUnavailableReason()
      if (unavailable) {
        setStatus('error')
        setError(unavailable)
        return
      }
      setStatus('starting')
      setError(null)

      let stream: MediaStream
      try {
        stream = await openCamera(deviceId)
      } catch (cameraError) {
        if (session !== sessionRef.current) return
        setStatus('error')
        setError(describeCameraError(cameraError))
        return
      }
      if (session !== sessionRef.current || !videoRef.current) {
        stream.getTracks().forEach((track) => track.stop())
        return
      }

      streamRef.current = stream
      const track = stream.getVideoTracks()[0]
      deviceIdRef.current = track.getSettings().deviceId
      await enableContinuousFocus(track)
      setTorchSupported(capabilitiesOf(track).torch === true)

      const video = videoRef.current
      video.srcObject = stream
      try {
        await video.play()
      } catch {
        // A muted inline video normally autoplays; frames are still read once it does.
      }
      if (session !== sessionRef.current) return
      setStatus('scanning')

      // Device labels and ids are only complete after permission is granted.
      navigator.mediaDevices
        .enumerateDevices()
        .then((devices) => {
          if (session !== sessionRef.current) return
          setCameraIds(devices.filter((item) => item.kind === 'videoinput' && item.deviceId).map((item) => item.deviceId))
        })
        .catch(() => undefined)

      const canvas = document.createElement('canvas')
      const context = canvas.getContext('2d', { willReadFrequently: true })
      const tick = async () => {
        if (session !== sessionRef.current) return
        const startedAt = performance.now()
        let text: string | null = null
        if (context && video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && video.videoWidth > 0) {
          // Decode the whole frame; the on-screen guide is only a hint.
          if (canvas.width !== video.videoWidth) canvas.width = video.videoWidth
          if (canvas.height !== video.videoHeight) canvas.height = video.videoHeight
          context.drawImage(video, 0, 0)
          try {
            text = await decodeCanvas(canvas)
          } catch {
            text = null
          }
        }
        if (session !== sessionRef.current) return
        if (text) {
          navigator.vibrate?.(80)
          stop()
          onDecodedRef.current(text)
          return
        }
        const elapsed = performance.now() - startedAt
        timerRef.current = window.setTimeout(() => void tick(), Math.max(0, SCAN_INTERVAL_MS - elapsed))
      }
      void tick()
    },
    [stop, videoRef],
  )

  const toggleTorch = useCallback(async () => {
    const track = streamRef.current?.getVideoTracks()[0]
    if (!track) return
    const next = !torchOn
    try {
      await track.applyConstraints({ advanced: [{ torch: next } as MediaTrackConstraintSet] })
      setTorchOn(next)
    } catch {
      setTorchSupported(false)
    }
  }, [torchOn])

  const switchCamera = useCallback(() => {
    if (cameraIds.length < 2) return
    const index = cameraIds.indexOf(deviceIdRef.current ?? '')
    void start(cameraIds[(index + 1) % cameraIds.length])
  }, [cameraIds, start])

  useEffect(() => stop, [stop])

  return {
    status,
    error,
    torchSupported,
    torchOn,
    canSwitchCamera: cameraIds.length > 1,
    start,
    stop,
    toggleTorch,
    switchCamera,
  }
}
