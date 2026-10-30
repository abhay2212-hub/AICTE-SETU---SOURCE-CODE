// Owner: Dev D
// Four linked "hash blocks" lighting up in sequence, for the audit chain tile.
export default function HashChain() {
  return (
    <div className="relative flex items-center gap-2" aria-hidden="true">
      <div className="absolute inset-x-1 top-1/2 h-0.5 -translate-y-1/2 bg-emerald-200" />
      {[0, 1, 2, 3].map((i) => (
        <span
          key={i}
          className="hash-block relative h-3.5 w-3.5 rounded"
          style={{ animationDelay: `${i * 0.3}s` }}
        />
      ))}
    </div>
  )
}
