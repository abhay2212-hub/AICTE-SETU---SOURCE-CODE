// Owner: Dev D
// Animated Shadow Institute story: UG-CSE fills to 60 approved seats, overflows to 71.
// Hard-coded from the demo dataset (backend/scripts/load_demo.py SHADOW_STORY).
const SCALE = 80 // seats across the full track
const APPROVED = 60
const ADMITTED = 71
const pct = (seats: number) => `${(seats / SCALE) * 100}%`

export default function SeatLedgerCard() {
  return (
    <div className="rounded-2xl border border-white/15 bg-white/[0.07] p-6 shadow-2xl shadow-indigo-950/50 backdrop-blur">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm font-semibold tracking-wide text-white">Seat Ledger</p>
        <p className="text-xs text-indigo-200">Shadow Institute · 2026-27</p>
      </div>

      <div className="mt-6 flex items-end justify-between gap-4">
        <p className="text-sm text-indigo-100">UG-CSE · {APPROVED} approved</p>
        <p className="text-sm text-indigo-100">
          Admitted{' '}
          <span className="ledger-count text-2xl font-semibold tabular-nums text-white" />
        </p>
      </div>

      <div className="relative mt-3 h-6">
        <div className="absolute inset-0 rounded-full bg-white/10" />
        <div className="ledger-fill absolute inset-0">
          <div
            className="ledger-green absolute inset-y-0 left-0 rounded-l-full bg-emerald-400"
            style={{ width: pct(APPROVED) }}
          />
          <div
            className="ledger-red absolute inset-y-0 rounded-r-full bg-gradient-to-r from-rose-500 to-red-500"
            style={{ left: pct(APPROVED), width: pct(ADMITTED - APPROVED) }}
          />
        </div>
        {/* Approved-intake marker */}
        <div
          className="absolute -inset-y-1.5 w-0.5 rounded bg-white"
          style={{ left: pct(APPROVED) }}
        />
      </div>

      <div className="relative mt-2 h-4 text-xs tabular-nums text-indigo-200">
        <span className="absolute left-0">0</span>
        <span className="absolute -translate-x-1/2" style={{ left: pct(APPROVED) }}>
          {APPROVED}
        </span>
        <span
          className="ledger-late absolute -translate-x-1/2 font-semibold text-rose-300"
          style={{ left: pct(ADMITTED) }}
        >
          {ADMITTED}
        </span>
      </div>

      <div className="mt-6 h-9">
        <span className="ledger-pop inline-flex items-center gap-2 rounded-full bg-rose-500/20 px-3 py-1.5 text-sm font-medium text-rose-100 ring-1 ring-rose-400/60">
          <span className="h-2 w-2 rounded-full bg-rose-400" aria-hidden="true" />
          Overrun +{ADMITTED - APPROVED} → review case opened
        </span>
      </div>

      <p className="mt-4 text-xs text-indigo-300">Example from the demo dataset</p>
    </div>
  )
}
