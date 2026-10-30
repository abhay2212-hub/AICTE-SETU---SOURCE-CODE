// Owner: Dev D
import type { Accent } from "../lib/dashboards";

/** Light tints of each accent for cards on a white background (landing role cards). */
export const accentTints: Record<Accent, { badge: string; text: string; border: string }> = {
  teal: { badge: "bg-teal-50 text-teal-600", text: "text-teal-600", border: "hover:border-teal-400" },
  indigo: {
    badge: "bg-indigo-50 text-indigo-600",
    text: "text-indigo-600",
    border: "hover:border-indigo-400",
  },
  blue: { badge: "bg-blue-50 text-blue-600", text: "text-blue-600", border: "hover:border-blue-400" },
  slate: { badge: "bg-slate-100 text-slate-600", text: "text-slate-600", border: "hover:border-slate-400" },
  emerald: {
    badge: "bg-emerald-50 text-emerald-600",
    text: "text-emerald-600",
    border: "hover:border-emerald-400",
  },
  amber: { badge: "bg-amber-50 text-amber-600", text: "text-amber-600", border: "hover:border-amber-400" },
};
