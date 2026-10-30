// Owner: Dev D
import { roleBadge, useIdentity } from '../lib/roles'

/** "Signed in as Institution operator", "Signed in as Auditor · read-only", … */
export default function RoleBadge({ className = '' }: { className?: string }) {
  const { role } = useIdentity()
  return (
    <span
      data-testid="role-badge"
      className={`rounded-full border border-indigo-200 bg-indigo-50 px-2.5 py-0.5 text-xs font-medium text-indigo-800 ${className}`}
    >
      Signed in as {roleBadge(role)}
    </span>
  )
}
