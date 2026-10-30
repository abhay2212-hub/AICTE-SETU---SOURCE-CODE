// Owner: Dev D
import { useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "../../lib/api-types";
import { api, apiWithMetadata } from "../../lib/api";
import { actionHint, useIdentity } from "../../lib/roles";
import {
  institutionHeader,
  institutionSections,
  type InstitutionSection,
} from "../../lib/dashboards";
import ErrorAlert from "../../components/ErrorAlert";
import DashboardHeader, { headerButton } from "../../components/DashboardHeader";
import IssueQueue from "./IssueQueue";
import UploadWizard from "./UploadWizard";
import StudentRegistry from "./StudentRegistry";
import PostLockEditRequests from "./PostLockEditRequests";

type SeatLedger = components["schemas"]["SeatLedger"];
type ProgrammeLedger = components["schemas"]["ProgrammeLedger"];
type PoolLedger = components["schemas"]["PoolLedger"];
type Batch = components["schemas"]["Batch"];
type BatchList = components["schemas"]["BatchList"];
type ValidationIssue = components["schemas"]["ValidationIssue"];
type ReviewCase = components["schemas"]["ReviewCase"];

const poolLabels: Record<PoolLedger["pool"], string> = {
  regular: "Regular",
  tfw: "TFW",
  fn_oci_pio: "FN / OCI / PIO",
  nri: "NRI",
};

const statusStyles: Record<Batch["status"], string> = {
  uploaded: "bg-slate-100 text-slate-700",
  mapped: "bg-blue-100 text-blue-800",
  validated: "bg-emerald-100 text-emerald-800",
  committed: "bg-indigo-100 text-indigo-800",
  failed: "bg-red-100 text-red-800",
};

const severityStyles: Record<ValidationIssue["severity"], string> = {
  error: "bg-red-100 text-red-800",
  warning: "bg-amber-100 text-amber-800",
  review: "bg-violet-100 text-violet-800",
  info: "bg-sky-100 text-sky-800",
};

function Metric({
  label,
  value,
  description,
}: {
  label: string;
  value: number;
  description: string;
}) {
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-2 text-3xl font-semibold text-slate-900">
        {value.toLocaleString()}
      </p>
      <p className="mt-1 text-xs text-slate-500">{description}</p>
    </article>
  );
}

function BatchHistory({ institutionId }: { institutionId: string }) {
  const [offset, setOffset] = useState(0);
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null);
  const limit = 10;
  const { role } = useIdentity();
  const queryClient = useQueryClient();

  const batchesQuery = useQuery({
    queryKey: ["institution-batches", institutionId, offset],
    queryFn: () => api<BatchList>(`/batches?limit=${limit}&offset=${offset}`),
  });

  const issuesQuery = useQuery({
    queryKey: ["batch-issues", selectedBatchId],
    queryFn: () => api<ValidationIssue[]>(`/batches/${selectedBatchId}/issues`),
    enabled: Boolean(selectedBatchId),
  });

  const resolveMutation = useMutation({
    mutationFn: (payload: { issueId: number; note: string }) =>
      api<ValidationIssue>(`/validation-issues/${payload.issueId}/resolve`, {
        method: "POST",
        body: JSON.stringify({ note: payload.note }),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["batch-issues", selectedBatchId],
      });
    },
  });

  function resolve(issue: ValidationIssue) {
    const note = window
      .prompt(`Resolution note for row ${issue.row_number} (${issue.rule_code})?`)
      ?.trim();
    if (!note) return;
    resolveMutation.mutate({ issueId: issue.id, note });
  }

  // Errors are fixed by a correction upload; review findings need an AICTE admin.
  function resolveHint(issue: ValidationIssue): string | undefined {
    return actionHint(
      role,
      issue.severity === "review" ? "resolve_review_issue" : "resolve_issue",
    );
  }

  const data = batchesQuery.data;
  const total = data?.total ?? 0;
  const items = data?.items ?? [];

  return (
    <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">
            Batch History
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Previous admission uploads and their validation status.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void batchesQuery.refetch()}
          disabled={batchesQuery.isFetching}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50 disabled:opacity-50"
        >
          {batchesQuery.isFetching ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {batchesQuery.isPending ? (
        <p className="py-6 text-sm text-slate-500">Loading batch history…</p>
      ) : batchesQuery.isError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <p>Could not load batch history.</p>
          <button
            type="button"
            onClick={() => void batchesQuery.refetch()}
            className="mt-2 font-medium underline"
          >
            Retry
          </button>
        </div>
      ) : items.length === 0 ? (
        <p className="rounded-lg bg-slate-50 p-6 text-center text-sm text-slate-500">
          No admission uploads found yet.
        </p>
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-slate-200">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-3 py-3 font-medium">File</th>
                  <th className="px-3 py-3 font-medium">Status</th>
                  <th className="px-3 py-3 text-right font-medium">Rows</th>
                  <th className="px-3 py-3 text-right font-medium">Errors</th>
                  <th className="px-3 py-3 text-right font-medium">Warnings</th>
                  <th className="px-3 py-3 font-medium">Uploaded</th>
                  <th className="px-3 py-3 font-medium">Issues</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((batch) => (
                  <tr key={batch.id} className="align-top hover:bg-slate-50">
                    <td className="max-w-64 break-words px-3 py-4">
                      <p className="font-medium text-slate-900">
                        {batch.file_name}
                      </p>
                      {batch.parent_batch_id && (
                        <p className="mt-1 text-xs text-slate-500">
                          Correction batch
                        </p>
                      )}
                    </td>
                    <td className="px-3 py-4">
                      <span
                        className={`rounded-full px-2 py-1 text-xs font-medium capitalize ${statusStyles[batch.status]}`}
                      >
                        {batch.status}
                      </span>
                    </td>
                    <td className="px-3 py-4 text-right tabular-nums">
                      {batch.counts.rows_total.toLocaleString()}
                    </td>
                    <td className="px-3 py-4 text-right tabular-nums">
                      {batch.counts.errors.toLocaleString()}
                    </td>
                    <td className="px-3 py-4 text-right tabular-nums">
                      {batch.counts.warnings.toLocaleString()}
                    </td>
                    <td className="px-3 py-4 whitespace-nowrap text-slate-600">
                      {new Date(batch.created_at).toLocaleString()}
                    </td>
                    <td className="px-3 py-4">
                      <button
                        type="button"
                        onClick={() =>
                          setSelectedBatchId((current) =>
                            current === batch.id ? null : batch.id,
                          )
                        }
                        className="font-medium text-indigo-700 underline"
                        aria-expanded={selectedBatchId === batch.id}
                      >
                        {selectedBatchId === batch.id
                          ? "Hide issues"
                          : "View issues"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-slate-500">
              Showing {offset + 1}–{offset + items.length} of {total}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={offset === 0 || batchesQuery.isFetching}
                onClick={() =>
                  setOffset((current) => Math.max(0, current - limit))
                }
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm disabled:opacity-40"
              >
                Previous
              </button>
              <button
                type="button"
                disabled={offset + limit >= total || batchesQuery.isFetching}
                onClick={() => setOffset((current) => current + limit)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}

      {selectedBatchId && (
        <div className="space-y-3 rounded-lg border border-slate-200 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-semibold text-slate-900">Validation issues</h3>
            <button
              type="button"
              onClick={() => setSelectedBatchId(null)}
              className="text-sm text-slate-600 underline"
            >
              Close
            </button>
          </div>

          {resolveMutation.isError && (
            <ErrorAlert
              action="Resolving the issue"
              error={resolveMutation.error}
            />
          )}

          {issuesQuery.isPending ? (
            <p className="text-sm text-slate-500">Loading issues…</p>
          ) : issuesQuery.isError ? (
            <div className="text-sm text-red-800">
              Could not load issues for this batch.
              <button
                type="button"
                onClick={() => void issuesQuery.refetch()}
                className="ml-2 underline"
              >
                Retry
              </button>
            </div>
          ) : issuesQuery.data.length === 0 ? (
            <p className="text-sm text-slate-500">
              The API returned no validation issues for this batch.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-3 py-2">Row</th>
                    <th className="px-3 py-2">Severity</th>
                    <th className="px-3 py-2">Rule</th>
                    <th className="px-3 py-2">Message</th>
                    <th className="px-3 py-2">Status</th>
                    <th className="px-3 py-2">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {issuesQuery.data.map((issue) => (
                    <tr key={issue.id} className="align-top">
                      <td className="px-3 py-3 tabular-nums">
                        {issue.row_number}
                      </td>
                      <td className="px-3 py-3">
                        <span
                          className={`rounded-full px-2 py-1 text-xs font-medium ${severityStyles[issue.severity]}`}
                        >
                          {issue.severity}
                        </span>
                      </td>
                      <td className="px-3 py-3 font-mono text-xs">
                        {issue.rule_code}
                      </td>
                      <td className="px-3 py-3">{issue.message}</td>
                      <td className="px-3 py-3">
                        {issue.resolved ? "Resolved" : "Open"}
                      </td>
                      <td className="px-3 py-3">
                        {issue.resolved ? null : issue.severity === "error" ? (
                          <span className="text-xs text-slate-500">
                            Fixed by a correction upload
                          </span>
                        ) : (
                          <div className="space-y-1">
                            <button
                              type="button"
                              onClick={() => resolve(issue)}
                              disabled={
                                Boolean(resolveHint(issue)) ||
                                resolveMutation.isPending
                              }
                              title={resolveHint(issue)}
                              className="rounded-lg border border-slate-300 px-2.5 py-1 text-xs font-medium hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              Resolve
                            </button>
                            {resolveHint(issue) && (
                              <p className="whitespace-nowrap text-xs text-slate-500">
                                {resolveHint(issue)}
                              </p>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

type Totals = {
  approved: number;
  admitted: number;
  available: number;
  overruns: number;
};

function available(programme: ProgrammeLedger): number {
  return programme.pools.reduce((sum, pool) => sum + pool.available, 0);
}

function ProgrammeBreakdown({ programmes }: { programmes: ProgrammeLedger[] }) {
  const [search, setSearch] = useState("");
  const [overrunsOnly, setOverrunsOnly] = useState(false);

  const filteredProgrammes = programmes.filter((programme) => {
    const term = search.trim().toLowerCase();
    const matchesSearch =
      programme.programme_code.toLowerCase().includes(term) ||
      programme.programme_name.toLowerCase().includes(term);

    return matchesSearch && (!overrunsOnly || programme.overrun > 0);
  });

  return (
    <div className="space-y-2">
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-4 border-b border-slate-200 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold">Programme breakdown</h2>
            <p className="mt-1 text-sm text-slate-500">
              {filteredProgrammes.length} of {programmes.length} programmes
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <label className="sr-only" htmlFor="programme-search">
              Search programmes
            </label>
            <input
              id="programme-search"
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search programmes…"
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            />
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={overrunsOnly}
                onChange={(event) => setOverrunsOnly(event.target.checked)}
                className="rounded border-slate-300"
              />
              Overruns only
            </label>
          </div>
        </div>

        {programmes.length === 0 ? (
          <p className="p-8 text-center text-sm text-slate-500">
            No programme data was returned for this academic year.
          </p>
        ) : filteredProgrammes.length === 0 ? (
          <p className="p-8 text-center text-sm text-slate-500">
            No programmes match your filters.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-5 py-3 font-medium">Programme</th>
                  <th className="px-5 py-3 text-right font-medium">Approved</th>
                  <th className="px-5 py-3 text-right font-medium">Admitted</th>
                  <th className="px-5 py-3 text-right font-medium">
                    Available
                  </th>
                  <th className="px-5 py-3 text-right font-medium">Overrun</th>
                  <th className="px-5 py-3 font-medium">Pool breakdown</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredProgrammes.map((programme) => (
                  <tr
                    key={programme.programme_id}
                    className="align-top hover:bg-slate-50"
                  >
                    <td className="px-5 py-4">
                      <p className="font-medium text-slate-900">
                        {programme.programme_name}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        {programme.programme_code}
                      </p>
                    </td>
                    <td className="px-5 py-4 text-right tabular-nums">
                      {programme.approved_total.toLocaleString()}
                    </td>
                    <td className="px-5 py-4 text-right tabular-nums">
                      {programme.admitted_total.toLocaleString()}
                    </td>
                    <td className="px-5 py-4 text-right tabular-nums">
                      {available(programme).toLocaleString()}
                    </td>
                    <td className="px-5 py-4 text-right">
                      <span
                        className={
                          programme.overrun > 0
                            ? "rounded-full bg-red-100 px-2.5 py-1 text-xs font-semibold text-red-700"
                            : "rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600"
                        }
                      >
                        {programme.overrun.toLocaleString()}
                      </span>
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex flex-wrap gap-2">
                        {programme.pools.map((pool) => (
                          <span
                            key={pool.pool}
                            title={`Rule version: ${pool.rule_version}`}
                            className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-600"
                          >
                            {poolLabels[pool.pool]}: {pool.admitted}/
                            {pool.approved_seats}
                          </span>
                        ))}
                        {programme.pools.length === 0 && (
                          <span className="text-xs text-slate-400">
                            No pool details
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <p className="text-xs text-slate-400">
        Figures reflect the seat-ledger API response. Availability is summed
        from pool-level values; this page does not recalculate server rules.
      </p>
    </div>
  );
}

/** "UG-CSE is 11 over approved intake · 1 AICTE case open", or the all-clear. */
function IntakeAlert({
  programmes,
  openCases,
}: {
  programmes: ProgrammeLedger[];
  openCases: number | undefined;
}) {
  const over = programmes.filter((programme) => programme.overrun > 0);
  if (over.length === 0) {
    return (
      <div
        role="status"
        className="flex items-center gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-5 py-4 text-emerald-900"
      >
        <span
          className="h-2.5 w-2.5 shrink-0 rounded-full bg-emerald-500"
          aria-hidden="true"
        />
        <p className="font-medium">All programmes within intake</p>
      </div>
    );
  }
  const parts = over.map(
    (programme) =>
      `${programme.programme_code} is ${programme.overrun.toLocaleString()} over approved intake`,
  );
  if (openCases)
    parts.push(`${openCases} AICTE case${openCases === 1 ? "" : "s"} open`);
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-5 py-4 text-red-900"
    >
      <span
        className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full bg-red-500"
        aria-hidden="true"
      />
      <div>
        <p className="font-semibold">{parts.join(" · ")}</p>
        <p className="mt-1 text-sm text-red-800">
          Withdraw or correct admissions in the registry below; AICTE reviews
          every overrun.
        </p>
      </div>
    </div>
  );
}

/** Seat Ledger in one line, for the operator workspace. */
function LedgerStrip({
  totals,
  academicYear,
}: {
  totals: Totals;
  academicYear: string;
}) {
  const items = [
    ["Approved", totals.approved],
    ["Admitted", totals.admitted],
    ["Available", totals.available],
    ["Over intake", totals.overruns],
  ] as const;
  return (
    <section
      aria-label="Seat Ledger summary"
      className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white px-5 py-3 shadow-sm sm:flex-row sm:items-center sm:justify-between"
    >
      <p className="text-sm font-medium text-slate-700">
        Seat Ledger · {academicYear}
      </p>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:flex">
        {items.map(([label, value]) => (
          <div key={label} className="flex items-baseline gap-2">
            <dt className="text-slate-500">{label}</dt>
            <dd
              className={`font-semibold tabular-nums ${
                label === "Over intake" && value > 0
                  ? "text-red-700"
                  : "text-slate-900"
              }`}
            >
              {value.toLocaleString()}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/** Loading and error states for a section that needs the seat ledger. */
function LedgerState({
  query,
  children,
}: {
  query: { isPending: boolean; isError: boolean; refetch: () => unknown };
  children: ReactNode;
}) {
  if (query.isPending)
    return <div className="h-20 animate-pulse rounded-xl bg-slate-200" />;
  if (query.isError)
    return (
      <div className="rounded-xl border border-red-200 bg-white p-5 text-sm text-red-800">
        Could not load the seat ledger. Check the API connection and current
        demo identity.{" "}
        <button
          type="button"
          onClick={() => void query.refetch()}
          className="font-medium underline"
        >
          Retry
        </button>
      </div>
    );
  return <>{children}</>;
}

export default function InstitutionPage() {
  const { role, institutionId } = useIdentity();
  const academicYear = "2026-27";
  const endpoint = `/institutions/${institutionId}/seat-ledger?academic_year=${academicYear}`;
  const sections = institutionSections(role);
  const header = institutionHeader(role);

  const query = useQuery({
    queryKey: ["seat-ledger", institutionId, role, academicYear],
    queryFn: () => apiWithMetadata<SeatLedger>(endpoint),
    enabled: Boolean(institutionId),
  });

  const openCasesQuery = useQuery({
    queryKey: ["institution-open-overrun-cases", institutionId, role],
    queryFn: () =>
      api<ReviewCase[]>("/review-cases?status=open&kind=intake_overrun"),
    enabled: Boolean(institutionId) && sections.includes("intake_alert"),
  });

  const programmes = useMemo(
    () => query.data?.data.programmes ?? [],
    [query.data?.data.programmes],
  );

  const totals = useMemo(
    () =>
      programmes.reduce<Totals>(
        (total, programme) => {
          total.approved += programme.approved_total;
          total.admitted += programme.admitted_total;
          total.available += available(programme);
          total.overruns += programme.overrun > 0 ? 1 : 0;
          return total;
        },
        { approved: 0, admitted: 0, available: 0, overruns: 0 },
      ),
    [programmes],
  );

  if (!institutionId) {
    return (
      <section className="rounded-xl border border-amber-200 bg-amber-50 p-5">
        <h1 className="text-xl font-semibold">{header.title}</h1>
        <p className="mt-2 text-sm text-amber-900">
          No institution is associated with the current demo identity. Select an
          institution identity before viewing the seat ledger.
        </p>
      </section>
    );
  }

  const openCases = openCasesQuery.data?.filter(
    (item) => item.institution_id === institutionId,
  ).length;
  const year = query.data?.data.academic_year ?? academicYear;
  const isOperator = role !== "institution_admin";

  // One renderer per section; institutionSections(role) decides which appear and in what order.
  const render: Record<InstitutionSection, ReactNode> = {
    upload: <UploadWizard institutionId={institutionId} />,
    rows_to_fix: <IssueQueue institutionId={institutionId} mode="fix" />,
    batch_history: <BatchHistory institutionId={institutionId} />,
    edit_requests: (
      <PostLockEditRequests
        institutionId={institutionId}
        academicYear={academicYear}
        title={isOperator ? "My edit requests" : "Edit request history"}
        description={
          isOperator
            ? "Ask AICTE to change a committed admission after the window locks, and follow each request."
            : "Every post-lock change your institution has asked for, with AICTE's decision."
        }
      />
    ),
    ledger_strip: (
      <LedgerState query={query}>
        <LedgerStrip totals={totals} academicYear={year} />
      </LedgerState>
    ),
    intake_alert: (
      <LedgerState query={query}>
        <IntakeAlert programmes={programmes} openCases={openCases} />
      </LedgerState>
    ),
    kpis: (
      <LedgerState query={query}>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Metric
            label="Approved seats"
            value={totals.approved}
            description="Across all returned programmes"
          />
          <Metric
            label="Admitted"
            value={totals.admitted}
            description="Reported admissions"
          />
          <Metric
            label="Available seats"
            value={totals.available}
            description="Sum of pool availability"
          />
          <Metric
            label="Programmes over limit"
            value={totals.overruns}
            description="Programmes with a positive overrun"
          />
        </div>
      </LedgerState>
    ),
    programmes: (
      <LedgerState query={query}>
        <ProgrammeBreakdown programmes={programmes} />
      </LedgerState>
    ),
    warnings: <IssueQueue institutionId={institutionId} mode="resolve" />,
    registry: (
      <StudentRegistry
        institutionId={institutionId}
        academicYear={academicYear}
      />
    ),
    upload_collapsed: (
      <details className="group rounded-xl border border-slate-200 bg-white shadow-sm">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-5">
          <span>
            <span className="block text-lg font-semibold text-slate-900">
              Upload a batch
            </span>
            <span className="mt-1 block text-sm text-slate-500">
              Operators usually handle data entry; open this to upload a batch
              yourself.
            </span>
          </span>
          <span
            aria-hidden="true"
            className="text-xl text-slate-400 transition group-open:rotate-90"
          >
            ›
          </span>
        </summary>
        <div className="border-t border-slate-200 p-1">
          <UploadWizard institutionId={institutionId} />
        </div>
      </details>
    ),
  };

  return (
    <section className="space-y-6" data-role-dashboard={role}>
      <DashboardHeader
        header={header}
        eyebrow={`Institution portal · ${year}`}
        simulated={Boolean(query.data?.isMock)}
        actions={
          <button
            type="button"
            onClick={() => void query.refetch()}
            disabled={query.isFetching}
            className={headerButton}
          >
            {query.isFetching ? "Refreshing…" : "Refresh data"}
          </button>
        }
      />
      {sections.map((id) => (
        <div key={id} data-section={id}>
          {render[id]}
        </div>
      ))}
    </section>
  );
}
