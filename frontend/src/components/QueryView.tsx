// Owner: Dev D
// Plain loading / error / JSON rendering for placeholder pages.
import type { UseQueryResult } from '@tanstack/react-query'
import { ApiError } from '../lib/api'

interface Props<T> {
  title: string
  endpoint: string
  query: UseQueryResult<T>
}

export default function QueryView<T>({ title, endpoint, query }: Props<T>) {
  return (
    <section className="space-y-3">
      <h1 className="text-xl font-semibold">{title}</h1>
      <p className="text-sm text-slate-500">
        Data from <code className="rounded bg-slate-100 px-1">{endpoint}</code>
      </p>
      {query.isPending && <p>Loading…</p>}
      {query.isError && (
        <p className="text-red-700">
          {query.error instanceof ApiError
            ? `Request failed with ${query.error.status}. Check the demo role.`
            : 'Cannot reach the API. Is the backend running on VITE_API_URL?'}
        </p>
      )}
      {query.isSuccess && (
        <pre className="overflow-auto rounded border border-slate-200 bg-white p-4 text-xs">
          {JSON.stringify(query.data, null, 2)}
        </pre>
      )}
    </section>
  )
}
