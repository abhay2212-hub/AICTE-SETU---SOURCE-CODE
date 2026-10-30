// Owner: Dev X
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { before, describe, it } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { QRCodeSVG } from 'qrcode.react'
import testVectors from '../../shared/test-vectors.json' with { type: 'json' }
import { prepareZXingModule } from 'zxing-wasm/reader'
import { decodeWithZxing, type Pixels } from '../src/pages/verifier/qr-decoder.ts'

// Longest student credential fixture (739 chars) and an enrolment certificate credential (738 chars)
// produced by backend services.certificates.build_credential with the test seed.
const CREDENTIAL_QR = testVectors.credentials.cases.reduce(
  (longest, item) => (item.qr_text.length > longest.length ? item.qr_text : longest),
  '',
)
const CERTIFICATE_QR =
  'eyJwYXlsb2FkIjp7InYiOjEsImlkIjoiNzZkMGE1ZWMtOWIzNi00MDk3LThiNWMtYmM5ZGNmOTU5MDlmIiwiaXNzIjoiYXBhYXItaW50ZWdyaXR5LXBsYXRmb3JtIiwic3ViIjoiYjYyM2NjNmRmNjU1ZGYwMGI2Yzg2MDgzZTkwOTQ3NjUwYzY3ODBmZjg3OWJlM2Q2Y2RkYzJhYzAyZWI3Y2VlYyIsImF1ZCI6ImVucm9sbWVudC1jZXJ0aWZpY2F0ZSIsImNsYWltcyI6eyJlbnJvbG1lbnRfc3RhdHVzIjoic3R1ZGVudF9jb25maXJtZWQiLCJpbnN0aXR1dGlvbiI6Ik1lZ2hkb290IEluc3RpdHV0ZSBvZiBFbmdpbmVlcmluZyIsInByb2dyYW1tZSI6IkIuVGVjaCBDb21wdXRlciBTY2llbmNlIGFuZCBFbmdpbmVlcmluZyIsImFjYWRlbWljX3llYXIiOiIyMDI2LTI3In0sImlhdCI6MTc5Mjg5OTc5MywiZXhwIjoxODA4NDUxNzkzLCJub25jZSI6IjI1M2IxY2QyOTg2NjZmMjBiOGQ2NmExM2Q3ZWEwMGI3In0sInNpZyI6IkNHQ2pHbEpYNXh0WUFDL3dia2loL3psam1EcGl1cnpxb0tJOTB4VHh2RjVvYzcramhVczlTSzdZb2w2TmJiWUx0SWVPWWQzckxOWEUyVHZsV1Mvb0JBPT0ifQ'

/** Module grid exactly as the student page draws it (qrcode.react, 4-module quiet zone). */
function studentPageMatrix(value: string, level: 'L' | 'M'): boolean[][] {
  const svg = renderToStaticMarkup(createElement(QRCodeSVG, { value, level, marginSize: 4 }))
  const size = Number(/viewBox="0 0 (\d+) \1"/.exec(svg)?.[1])
  assert.ok(size > 0, 'could not read QR size from SVG')
  const grid = Array.from({ length: size }, () => new Array<boolean>(size).fill(false))
  for (const run of svg.matchAll(/M(\d+)[ ,](\d+)\s*h(\d+)v1H\d+z/g)) {
    const [x, y, width] = [Number(run[1]), Number(run[2]), Number(run[3])]
    for (let i = 0; i < width; i++) grid[y][x + i] = true
  }
  return grid
}

interface Shot {
  frameWidth: number
  frameHeight: number
  /** QR side length in output pixels, quiet zone included. */
  qrPixels: number
  angleDeg: number
  blurRadius: number
  noise: number
}

/** Renders the grid as a camera would see it: scaled, rotated, blurred, low-contrast and noisy. */
function photograph(grid: boolean[][], shot: Shot): Pixels {
  const { frameWidth, frameHeight, qrPixels, angleDeg, blurRadius, noise } = shot
  const modules = grid.length
  const scale = modules / qrPixels
  const angle = (angleDeg * Math.PI) / 180
  const [cos, sin] = [Math.cos(angle), Math.sin(angle)]
  const ink = 55
  const paper = 215
  const background = 140
  const sample = (mx: number, my: number) => {
    if (mx < 0 || my < 0 || mx >= modules || my >= modules) return background
    return grid[Math.floor(my)][Math.floor(mx)] ? ink : paper
  }

  // 2x2 supersampling per output pixel gives anti-aliased module edges.
  let gray = new Float32Array(frameWidth * frameHeight)
  for (let y = 0; y < frameHeight; y++) {
    for (let x = 0; x < frameWidth; x++) {
      let sum = 0
      for (const [ox, oy] of [[0.25, 0.25], [0.75, 0.25], [0.25, 0.75], [0.75, 0.75]]) {
        const dx = x + ox - frameWidth / 2
        const dy = y + oy - frameHeight / 2
        const mx = (cos * dx + sin * dy) * scale + modules / 2
        const my = (-sin * dx + cos * dy) * scale + modules / 2
        sum += sample(mx, my)
      }
      gray[y * frameWidth + x] = sum / 4
    }
  }

  for (let pass = 0; pass < blurRadius; pass++) {
    const next = new Float32Array(gray.length)
    for (let y = 0; y < frameHeight; y++) {
      for (let x = 0; x < frameWidth; x++) {
        let sum = 0
        let count = 0
        for (let ky = -1; ky <= 1; ky++) {
          for (let kx = -1; kx <= 1; kx++) {
            const sx = x + kx
            const sy = y + ky
            if (sx < 0 || sy < 0 || sx >= frameWidth || sy >= frameHeight) continue
            sum += gray[sy * frameWidth + sx]
            count++
          }
        }
        next[y * frameWidth + x] = sum / count
      }
    }
    gray = next
  }

  // Deterministic noise so the test is repeatable.
  let seed = 12345
  const random = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff
    return seed / 0x7fffffff - 0.5
  }
  const data = new Uint8ClampedArray(frameWidth * frameHeight * 4)
  for (let i = 0; i < gray.length; i++) {
    const value = gray[i] + random() * noise
    data[i * 4] = value
    data[i * 4 + 1] = value
    data[i * 4 + 2] = value
    data[i * 4 + 3] = 255
  }
  return { width: frameWidth, height: frameHeight, data }
}

const SHOTS: { name: string; shot: Shot }[] = [
  { name: 'screen-sized, 4 px per module', shot: { frameWidth: 420, frameHeight: 420, qrPixels: 400, angleDeg: 0, blurRadius: 0, noise: 0 } },
  { name: 'low resolution, ~2.6 px per module', shot: { frameWidth: 280, frameHeight: 280, qrPixels: 260, angleDeg: 0, blurRadius: 0, noise: 0 } },
  { name: '640x480 photo, rotated 8°, blurred', shot: { frameWidth: 640, frameHeight: 480, qrPixels: 330, angleDeg: 8, blurRadius: 1, noise: 30 } },
  { name: '1280x720 photo, rotated -17°, more blur', shot: { frameWidth: 1280, frameHeight: 720, qrPixels: 560, angleDeg: -17, blurRadius: 2, noise: 40 } },
  { name: '1920x1080 frame, QR fills most of it, rotated 4°', shot: { frameWidth: 1920, frameHeight: 1080, qrPixels: 900, angleDeg: 4, blurRadius: 2, noise: 30 } },
]

describe('verifier QR fallback decoder (zxing-wasm)', () => {
  before(() => {
    const require = createRequire(import.meta.url)
    // Node cannot fetch a file path, so hand the reader its wasm bytes directly.
    const wasm = readFileSync(require.resolve('zxing-wasm/reader/zxing_reader.wasm'))
    prepareZXingModule({ overrides: { wasmBinary: wasm.buffer.slice(wasm.byteOffset, wasm.byteOffset + wasm.byteLength) } })
  })

  it('uses real-length credential payloads', () => {
    assert.ok(CREDENTIAL_QR.length >= 735, `credential is ${CREDENTIAL_QR.length} chars`)
    assert.equal(CERTIFICATE_QR.length, 738)
  })

  for (const [label, value] of [['student credential', CREDENTIAL_QR], ['enrolment certificate', CERTIFICATE_QR]] as const) {
    for (const level of ['L', 'M'] as const) {
      for (const { name, shot } of SHOTS) {
        it(`decodes ${label} (EC ${level}) from ${name}`, async () => {
          const pixels = photograph(studentPageMatrix(value, level), shot)
          assert.equal(await decodeWithZxing(pixels), value)
        })
      }
    }
  }
})
