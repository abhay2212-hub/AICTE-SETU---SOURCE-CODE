// Owner: Dev X
// QR decoding for the verifier: native BarcodeDetector first, zxing-wasm as the fallback.

import { prepareZXingModule, readBarcodes, type ReaderOptions } from 'zxing-wasm/reader'

export interface Pixels {
  width: number
  height: number
  data: Uint8ClampedArray
}

interface DetectedBarcode {
  rawValue: string
}

interface NativeBarcodeDetector {
  detect(source: ImageBitmapSource): Promise<DetectedBarcode[]>
}

interface NativeBarcodeDetectorClass {
  new (options: { formats: string[] }): NativeBarcodeDetector
  getSupportedFormats?: () => Promise<string[]>
}

// Credential QRs are ~740 characters (version 18-21), so the reader is tuned for dense codes.
const READER_OPTIONS: ReaderOptions = {
  formats: ['QRCode'],
  tryHarder: true,
  tryRotate: true,
  tryInvert: true,
  tryDownscale: true,
  maxNumberOfSymbols: 1,
}

/** Serve the zxing wasm binary from our own origin instead of the library's CDN default. */
export function configureZxingWasm(wasmUrl: string): void {
  prepareZXingModule({
    overrides: {
      locateFile: (path: string, prefix: string) => (path.endsWith('.wasm') ? wasmUrl : prefix + path),
    },
  })
}

export async function decodeWithZxing(pixels: Pixels): Promise<string | null> {
  const results = await readBarcodes(pixels as ImageData, READER_OPTIONS)
  return results.find((item) => item.isValid && item.text)?.text ?? null
}

let nativeDetector: Promise<NativeBarcodeDetector | null> | undefined

/** The platform BarcodeDetector restricted to QR codes, or null where it is missing (e.g. desktop Windows). */
export function getNativeDetector(): Promise<NativeBarcodeDetector | null> {
  nativeDetector ??= createNativeDetector()
  return nativeDetector
}

async function createNativeDetector(): Promise<NativeBarcodeDetector | null> {
  const Detector = (globalThis as { BarcodeDetector?: NativeBarcodeDetectorClass }).BarcodeDetector
  if (!Detector) return null
  try {
    const formats = await Detector.getSupportedFormats?.()
    if (formats && !formats.includes('qr_code')) return null
    return new Detector({ formats: ['qr_code'] })
  } catch {
    return null
  }
}

/**
 * Decodes the whole canvas: native detector if present, then zxing-wasm.
 * The canvas must already hold the frame or image to read.
 */
export async function decodeCanvas(canvas: HTMLCanvasElement): Promise<string | null> {
  const native = await getNativeDetector()
  if (native) {
    try {
      const found = await native.detect(canvas)
      const text = found.find((item) => item.rawValue)?.rawValue
      if (text) return text
    } catch {
      // Fall through to zxing; some platforms throw on detect() for unsupported sources.
    }
  }
  const context = canvas.getContext('2d', { willReadFrequently: true })
  if (!context) return null
  return decodeWithZxing(context.getImageData(0, 0, canvas.width, canvas.height))
}

// Large phone photos are scaled down to this longest side; a QR that fills even a third of it stays readable.
const MAX_IMAGE_SIDE = 2400

/** Decodes an uploaded photo or screenshot (PNG/JPG) with the same decoders as the camera. */
export async function decodeImageFile(file: Blob): Promise<string | null> {
  const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  try {
    const ratio = Math.min(1, MAX_IMAGE_SIDE / Math.max(bitmap.width, bitmap.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(bitmap.width * ratio)
    canvas.height = Math.round(bitmap.height * ratio)
    const context = canvas.getContext('2d', { willReadFrequently: true })
    if (!context) return null
    // Screenshots with transparency would otherwise decode against black.
    context.fillStyle = '#fff'
    context.fillRect(0, 0, canvas.width, canvas.height)
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    return await decodeCanvas(canvas)
  } finally {
    bitmap.close()
  }
}
