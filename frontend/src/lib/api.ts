// Owner: Dev D
// Typed fetch wrapper for the backend. Sends the demo identity headers and tracks X-Mock.
import { useSyncExternalStore } from 'react'
import { getIdentity } from './roles'

export const API_URL: string = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export class ApiError extends Error {
  readonly status: number
  readonly body: unknown

  constructor(status: number, body: unknown) {
    super(`API ${status}`)
    this.status = status
    this.body = body
  }
}

let lastMock = false
const mockListeners = new Set<() => void>()

function setLastMock(value: boolean): void {
  if (value === lastMock) return
  lastMock = value
  mockListeners.forEach((listener) => listener())
}

/** Whether the most recent API response carried `X-Mock: true`. */
export function lastResponseWasMock(): boolean {
  return lastMock
}

export function useMockMode(): boolean {
  return useSyncExternalStore(
    (listener) => {
      mockListeners.add(listener)
      return () => mockListeners.delete(listener)
    },
    lastResponseWasMock,
  )
}

export type ApiResponse<T> = { data: T; isMock: boolean }

/** Fetch data with X-Mock metadata for this exact response. */
export async function apiWithMetadata<T>(path: string, init: RequestInit = {}): Promise<ApiResponse<T>> {
  const { role, institutionId } = getIdentity()
  const headers = new Headers(init.headers)
  headers.set('X-Demo-Role', role)
  if (institutionId) headers.set('X-Demo-Institution', institutionId)
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const response = await fetch(`${API_URL}${path}`, { ...init, headers })
  const isMock = response.headers.get('X-Mock') === 'true'
  setLastMock(isMock)
  const isJson = response.headers.get('Content-Type')?.includes('application/json')
  const body: unknown = isJson ? await response.json() : await response.text()
  if (!response.ok) throw new ApiError(response.status, body)
  return { data: body as T, isMock }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  return (await apiWithMetadata<T>(path, init)).data
}
