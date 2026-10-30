// Owner: Dev D
// Auditor panels on /aicte: audit-chain status and the decision log. Both only read.
import { useQuery } from "@tanstack/react-query";
import type { components } from "../../lib/api-types";
import { api } from "../../lib/api";
import { useActionHint } from "../../lib/roles";
import ErrorAlert from "../../components/ErrorAlert";
import {
  actorLabel,
  institutionLabel,
  type InstitutionLookup,
} from "../../components/format";

type AuditVerifyResult = components["schemas"]["AuditVerifyResult"];
type ReviewCase = components["schemas"]["ReviewCase"];
type EditRequest = components["schemas"]["EditRequest"];

const panel = "rounded-xl border border-slate-200 bg-white p-5 shadow-sm";
const button =
  "rounded-lg px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50";

/** Recompute the audit hash chain. ``auto`` verifies on load (the auditor's first question). */
export function AuditChainCard({
  auto,
  compact = false,
}: {
  auto: boolean;
  compact?: boolean;
}) {
  const auditHint = useActionHint("verify_audit_chain");
  const query = useQuery({
    queryKey: ["audit-verify"],
    queryFn: () => api<AuditVerifyResult>("/audit/verify"),
    enabled: auto && !auditHint,
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  });
  const result = query.data;
  const checkedAt = query.dataUpdatedAt
    ? new Date(query.dataUpdatedAt).toLocaleString()
    : null;

  const tone = !result
    ? "border-slate-200 bg-white"
    : result.ok
      ? "border-emerald-200 bg-emerald-50"
      : "border-red-300 bg-red-50";

  return (
    <section
      id="audit-chain"
      className={`rounded-xl border p-5 shadow-sm ${tone}`}
    >
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold text-slate-950">
            {compact ? "Audit-chain verification" : "Audit chain status"}
          </h2>
          {!result ? (
            <p className="mt-1 text-sm text-slate-500">
              {query.isFetching
                ? "Recomputing the hash chain…"
                : "Recompute the audit hash chain to check its integrity."}
            </p>
          ) : (
            <div
              role={result.ok ? "status" : "alert"}
              className={result.ok ? "text-emerald-900" : "text-red-900"}
            >
              <p className="mt-2 flex items-center gap-2 text-2xl font-semibold tracking-tight">
                <span
                  aria-hidden="true"
                  className={`h-3 w-3 rounded-full ${result.ok ? "bg-emerald-500" : "bg-red-500"}`}
                />
                {result.ok ? "Verified" : "Broken: tampering detected"}
              </p>
              <dl className="mt-3 grid gap-x-8 gap-y-1 text-sm sm:flex">
                <div className="flex gap-2">
                  <dt className="opacity-75">Events checked</dt>
                  <dd className="font-semibold tabular-nums">
                    {result.checked.toLocaleString()}
                  </dd>
                </div>
                {!result.ok && (
                  <div className="flex gap-2">
                    <dt className="opacity-75">First broken index</dt>
                    <dd className="font-semibold tabular-nums">
                      {result.first_broken_index ?? "Not provided by the API"}
                    </dd>
                  </div>
                )}
                {checkedAt && (
                  <div className="flex gap-2">
                    <dt className="opacity-75">Last checked</dt>
                    <dd className="font-semibold">{checkedAt}</dd>
                  </div>
                )}
              </dl>
            </div>
          )}
        </div>
        <button
          type="button"
          className={`${button} shrink-0 bg-slate-900 text-white hover:bg-slate-700`}
          disabled={query.isFetching || Boolean(auditHint)}
          title={auditHint}
          onClick={() => void query.refetch()}
        >
          {query.isFetching
            ? "Verifying…"
            : compact
              ? "Verify audit chain"
              : "Verify now"}
        </button>
      </div>
      {query.isError && (
        <div className="mt-4">
          <ErrorAlert action="Audit verification" error={query.error} />
        </div>
      )}
    </section>
  );
}

interface Decision {
  key: string;
  kind: "Review case" | "Edit request";
  title: string;
  outcome: string;
  decidedBy: string;
  decidedAt: string | null;
  note: string;
  institution: string;
}

function outcomeStyle(outcome: string): string {
  if (outcome === "approved" || outcome === "confirmed")
    return "bg-green-100 text-green-800";
  if (outcome === "rejected") return "bg-red-100 text-red-800";
  if (outcome === "dismissed") return "bg-slate-100 text-slate-700";
  return "bg-blue-100 text-blue-800";
}

/** Decided review cases and edit requests, newest first. */
export function DecisionLog({ lookup }: { lookup: InstitutionLookup }) {
  const casesQuery = useQuery({
    queryKey: ["decision-log-cases"],
    queryFn: () => api<ReviewCase[]>("/review-cases"),
    refetchInterval: 30000,
  });
  const editsQuery = useQuery({
    queryKey: ["decision-log-edits"],
    queryFn: () => api<EditRequest[]>("/edit-requests"),
    refetchInterval: 30000,
  });

  const decisions: Decision[] = [
    ...(casesQuery.data ?? [])
      .filter((item) => item.status !== "open")
      .map((item) => ({
        key: `case-${item.id}`,
        kind: "Review case" as const,
        title: item.title,
        outcome: item.status,
        // ReviewCase carries no decider and only an AICTE admin may resolve one.
        decidedBy: "AICTE admin",
        decidedAt: item.resolved_at ?? item.updated_at ?? null,
        note: item.reviewer_note || "—",
        institution: institutionLabel(item.institution_id, lookup, false),
      })),
    ...(editsQuery.data ?? [])
      .filter((item) => item.status !== "pending")
      .map((item) => ({
        key: `edit-${item.id}`,
        kind: "Edit request" as const,
        title: `${item.field.replaceAll("_", " ")}${item.admission?.student_name ? ` · ${item.admission.student_name}` : ""}`,
        outcome: item.status,
        decidedBy: item.decided_by ? actorLabel(item.decided_by) : "—",
        decidedAt: item.decided_at ?? null,
        note: item.decision_note || "—",
        institution: item.institution_id
          ? institutionLabel(item.institution_id, lookup, false)
          : "—",
      })),
  ].sort((a, b) => (b.decidedAt ?? "").localeCompare(a.decidedAt ?? ""));

  const loading = casesQuery.isPending || editsQuery.isPending;

  return (
    <section id="decision-log" className={panel}>
      <h2 className="text-lg font-semibold text-slate-950">Decision log</h2>
      <p className="mt-1 text-sm text-slate-500">
        Decided review cases and edit requests, newest first, with who decided,
        when and the note they left.
      </p>
      {casesQuery.isError && (
        <div className="mt-3">
          <ErrorAlert action="Loading review cases" error={casesQuery.error} />
        </div>
      )}
      {editsQuery.isError && (
        <div className="mt-3">
          <ErrorAlert action="Loading edit requests" error={editsQuery.error} />
        </div>
      )}
      {loading ? (
        <p className="py-6 text-sm text-slate-500">Loading decisions…</p>
      ) : decisions.length === 0 ? (
        <p className="mt-4 rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
          No decisions recorded yet.
        </p>
      ) : (
        <ol className="mt-4 space-y-3">
          {decisions.map((item) => (
            <li
              key={item.key}
              className="rounded-lg border border-slate-200 border-l-4 border-l-slate-500 p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    {item.kind} · {item.institution}
                  </p>
                  <h3
                    className={`mt-1 break-words font-medium text-slate-900 ${item.kind === "Edit request" ? "capitalize" : ""}`}
                  >
                    {item.title}
                  </h3>
                </div>
                <span
                  className={`rounded-full px-2.5 py-1 text-xs font-medium capitalize ${outcomeStyle(item.outcome)}`}
                >
                  {item.outcome.replaceAll("_", " ")}
                </span>
              </div>
              <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-slate-500">Decided by</dt>
                  <dd>{item.decidedBy}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">When</dt>
                  <dd>
                    {item.decidedAt
                      ? new Date(item.decidedAt).toLocaleString()
                      : "—"}
                  </dd>
                </div>
              </dl>
              <p className="mt-2 text-sm">
                <span className="text-slate-500">Note: </span>
                {item.note}
              </p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
