// Owner: Dev D
import type { ReactNode } from "react";
import type { Accent, DashboardHeader as Header } from "../lib/dashboards";
import RoleBadge from "./RoleBadge";

// Same dark gradient and dot grid as the landing hero, tinted per role.
const bands: Record<Accent, { band: string; eyebrow: string; rule: string }> = {
  teal: {
    band: "from-teal-950 via-teal-800 to-teal-600",
    eyebrow: "text-teal-200",
    rule: "bg-teal-300",
  },
  indigo: {
    band: "from-[#0b1437] via-[#1e1b6b] to-indigo-700",
    eyebrow: "text-indigo-200",
    rule: "bg-indigo-300",
  },
  blue: {
    band: "from-blue-950 via-blue-800 to-sky-600",
    eyebrow: "text-sky-200",
    rule: "bg-sky-300",
  },
  slate: {
    band: "from-slate-950 via-slate-800 to-slate-600",
    eyebrow: "text-slate-300",
    rule: "bg-slate-300",
  },
  emerald: {
    band: "from-emerald-950 via-emerald-800 to-emerald-600",
    eyebrow: "text-emerald-200",
    rule: "bg-emerald-300",
  },
  amber: {
    band: "from-[#2b1503] via-amber-800 to-amber-600",
    eyebrow: "text-amber-200",
    rule: "bg-amber-300",
  },
};

/** The auditor's read-only notice, shown above the header on AICTE pages. */
export function ReadOnlyBanner({ children }: { children: ReactNode }) {
  return (
    <div
      role="note"
      className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-slate-300 bg-slate-100 px-5 py-3 text-sm text-slate-800"
    >
      <span className="rounded-md bg-slate-800 px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-white">
        Read-only
      </span>
      <span>{children}</span>
    </div>
  );
}

/** Role dashboard header: accent band, title, one-line subtitle, role badge and actions. */
export default function DashboardHeader({
  header,
  eyebrow,
  simulated = false,
  actions,
  children,
}: {
  header: Header;
  eyebrow: string;
  simulated?: boolean;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  const style = bands[header.accent];
  return (
    <header
      data-testid="dashboard-header"
      data-accent={header.accent}
      className={`relative overflow-hidden rounded-2xl bg-linear-135 ${style.band} p-5 text-white shadow-sm sm:p-7`}
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(rgb(255_255_255/0.09)_1px,transparent_1px)] bg-size-[22px_22px]"
      />
      <div className="relative flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`h-1 w-6 rounded-full ${style.rule}`} aria-hidden="true" />
            <p className={`text-xs font-semibold uppercase tracking-[0.18em] ${style.eyebrow}`}>
              {eyebrow}
            </p>
            {simulated && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
                SIMULATED
              </span>
            )}
            <RoleBadge />
          </div>
          <h1 className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl">
            {header.title}
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-white/75">{header.subtitle}</p>
        </div>
        {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
      </div>
      {children && <div className="relative mt-5">{children}</div>}
    </header>
  );
}

/** Translucent button for use on the header band. */
export const headerButton =
  "rounded-lg border border-white/30 bg-white/10 px-3 py-2 text-sm font-medium text-white backdrop-blur transition hover:bg-white/20 disabled:cursor-not-allowed disabled:opacity-50";
