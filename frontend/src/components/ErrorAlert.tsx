// Owner: Dev D
import { apiErrorMessage } from './format'

/** Red alert box showing a failed request's server error code and message. */
export default function ErrorAlert({ error, action }: { error: unknown; action?: string }) {
  const text = apiErrorMessage(error)
  const coded = /^([A-Z][A-Z0-9_]+|HTTP \d{3}): ([\s\S]*)$/.exec(text)
  return (
    <div
      role="alert"
      className="break-words rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800"
    >
      {action && <span className="font-medium">{action} failed. </span>}
      {coded ? (
        <>
          <code className="rounded bg-red-100 px-1 py-0.5 font-mono text-xs font-semibold">
            {coded[1]}
          </code>{' '}
          {coded[2]}
        </>
      ) : (
        text
      )}
    </div>
  )
}
