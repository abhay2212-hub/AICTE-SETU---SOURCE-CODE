// Owner: Dev D
// Two institutions turn a masked record into bit encodings that meet in the middle.
// Illustrative values; the real comparison runs on keyed Bloom-filter encodings.
// A has 7 set bits, B the same 7 plus one: Dice = 2 * 7 / (7 + 8) = 0.93.
const BITS_A = [1, 0, 1, 1, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1]
const BITS_B = [1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 0, 1, 0, 0, 0, 1]

function Bits({ bits, tone }: { bits: number[]; tone: 'indigo' | 'cyan' }) {
  const on = tone === 'indigo' ? 'bg-indigo-400' : 'bg-cyan-400'
  return (
    <div className="flex gap-1" aria-hidden="true">
      {bits.map((bit, i) => (
        <span
          key={i}
          className={`bm-bit h-3 w-3 rounded-sm sm:h-3.5 sm:w-3.5 ${bit ? on : 'bg-white/10'}`}
          style={{ animationDelay: `${i * 0.04}s` }}
        />
      ))}
    </div>
  )
}

function InstitutionCard({
  name,
  record,
  bits,
  tone,
}: {
  name: string
  record: string
  bits: number[]
  tone: 'indigo' | 'cyan'
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">{name}</p>
      <p className="mt-2 font-mono text-sm text-slate-200">{record}</p>
      <div className="mt-3">
        <Bits bits={bits} tone={tone} />
      </div>
    </div>
  )
}

export default function BlindMatchStrip() {
  return (
    <section className="rounded-3xl bg-slate-950 px-4 py-8 text-white sm:px-8 sm:py-10">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Blind Match</h2>
        <p className="text-sm text-slate-400">
          Duplicates found across institutions without exchanging identity.
        </p>
      </div>
      <div className="mt-8 grid grid-cols-1 items-center gap-6 md:grid-cols-[1fr_auto_1fr]">
        <InstitutionCard name="Institution A" record="R*** K***, 2007" bits={BITS_A} tone="indigo" />
        <div className="flex flex-col items-center gap-4">
          <div className="relative h-4">
            <div className="bm-row-a">
              <Bits bits={BITS_A} tone="indigo" />
            </div>
            <div className="bm-row-b absolute inset-0">
              <Bits bits={BITS_B} tone="cyan" />
            </div>
          </div>
          <span className="bm-chip inline-flex items-center gap-2 rounded-full bg-emerald-400/15 px-3 py-1.5 text-sm font-medium text-emerald-200 ring-1 ring-emerald-400/50">
            Dice 0.93 · same student, no names shared
          </span>
        </div>
        <InstitutionCard name="Institution B" record="R*** K***, 2007" bits={BITS_B} tone="cyan" />
      </div>
    </section>
  )
}
