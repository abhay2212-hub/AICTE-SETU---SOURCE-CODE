// Owner: Dev D
// Open validation issues across the institution's recent batches. The API lists issues per
// batch only, so this reads the latest batches and then each batch's issues.
import { useState } from "react";
import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import type { components } from "../../lib/api-types";
import { api } from "../../lib/api";
import { useActionHint } from "../../lib/roles";
import ErrorAlert from "../../components/ErrorAlert";

type Batch = components["schemas"]["Batch"];
type BatchList = components["schemas"]["BatchList"];
type ValidationIssue = components["schemas"]["ValidationIssue"];
type CommitResult = components["schemas"]["CommitResult"];

const RECENT_BATCHES = 5;

const severityStyles: Record<ValidationIssue["severity"], string> = {
  error: "bg-red-100 text-red-800",
  warning: "bg-amber-100 text-amber-800",
  review: "bg-violet-100 text-violet-800",
  info: "bg-sky-100 text-sky-800",
};

type Mode = "fix" | "resolve";

const copy: Record<Mode, { title: string; description: string; empty: string }> = {
  fix: {
    title: "Rows to fix",
    description:
      "Rejected rows and open warnings from your recent batches. Fix the rows in your file and upload the corrections against the batch.",
    empty: "Nothing to fix: recent batches have no rejected rows or open warnings.",
  },
  resolve: {
    title: "Warnings to resolve",
    description:
      "Open warnings from recent batches. Check each row and resolve it with a note.",
    empty: "No open warnings in recent batches.",
  },
};

function wanted(mode: Mode, issue: ValidationIssue): boolean {
  if (issue.resolved) return false;
  return mode === "fix"
    ? issue.severity === "error" || issue.severity === "warning"
    : issue.severity === "warning";
}

function CorrectionUpload({ batch }: { batch: Batch }) {
  const queryClient = useQueryClient();
  const hint = useActionHint("upload_corrections");
  const [file, setFile] = useState<File | null>(null);
  const inputId = `corrections-${batch.id}`;

  const mutation = useMutation({
    mutationFn: (upload: File) => {
      const body = new FormData();
      body.append("file", upload);
      return api<CommitResult>(`/batches/${batch.id}/corrections`, {
        method: "POST",
        body,
      });
    },
    onSuccess: async () => {
      setFile(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["issue-queue"] }),
        queryClient.invalidateQueries({ queryKey: ["institution-batches"] }),
        queryClient.invalidateQueries({ queryKey: ["seat-ledger"] }),
      ]);
    },
  });

  return (
    <div className="space-y-2 rounded-lg bg-teal-50 p-3">
      <label htmlFor={inputId} className="block text-sm font-medium text-teal-900">
        Upload corrections for this batch
      </label>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <input
          id={inputId}
          type="file"
          accept=".csv,.xlsx"
          disabled={Boolean(hint)}
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          className="block w-full min-w-0 text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-white file:px-3 file:py-2"
        />
        <button
          type="button"
          disabled={!file || Boolean(hint) || mutation.isPending}
          title={hint}
          onClick={() => file && mutation.mutate(file)}
          className="shrink-0 rounded-lg bg-teal-700 px-3 py-2 text-sm font-medium text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {mutation.isPending ? "Uploading…" : "Upload corrections"}
        </button>
      </div>
      <p className="text-xs text-teal-900/70">
        {hint ??
          "Only rows matching a rejected row are committed; add a source_row column with the original row number."}
      </p>
      {mutation.isError && (
        <ErrorAlert action="Uploading corrections" error={mutation.error} />
      )}
      {mutation.isSuccess && (
        <p role="status" className="text-sm text-teal-900">
          {mutation.data.rows_committed} rows committed,{" "}
          {mutation.data.rows_rejected} still rejected.
        </p>
      )}
    </div>
  );
}

export default function IssueQueue({
  institutionId,
  mode,
}: {
  institutionId: string;
  mode: Mode;
}) {
  const queryClient = useQueryClient();
  const resolveHint = useActionHint("resolve_issue");
  const batchesQuery = useQuery({
    queryKey: ["institution-batches", institutionId, "recent"],
    queryFn: () => api<BatchList>(`/batches?limit=${RECENT_BATCHES}`),
  });
  const batches = batchesQuery.data?.items ?? [];

  const issueQueries = useQueries({
    queries: batches.map((batch) => ({
      queryKey: ["issue-queue", batch.id],
      queryFn: () => api<ValidationIssue[]>(`/batches/${batch.id}/issues`),
    })),
  });

  const resolveMutation = useMutation({
    mutationFn: (payload: { issueId: number; note: string }) =>
      api<ValidationIssue>(`/validation-issues/${payload.issueId}/resolve`, {
        method: "POST",
        body: JSON.stringify({ note: payload.note }),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["issue-queue"] });
    },
  });

  function resolve(issue: ValidationIssue) {
    const note = window
      .prompt(`Resolution note for row ${issue.row_number} (${issue.rule_code})?`)
      ?.trim();
    if (!note) return;
    resolveMutation.mutate({ issueId: issue.id, note });
  }

  const groups = batches
    .map((batch, index) => ({
      batch,
      issues: (issueQueries[index]?.data ?? []).filter((issue) =>
        wanted(mode, issue),
      ),
    }))
    .filter((group) => group.issues.length > 0);
  const loading =
    batchesQuery.isPending || issueQueries.some((query) => query.isPending);
  const failed =
    batchesQuery.isError || issueQueries.some((query) => query.isError);
  const total = groups.reduce((sum, group) => sum + group.issues.length, 0);
  const text = copy[mode];

  return (
    <section
      id={mode === "fix" ? "rows-to-fix" : "warnings-to-resolve"}
      className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold text-slate-900">
            {text.title}
            {!loading && total > 0 && (
              <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 align-middle text-xs font-semibold text-amber-800">
                {total} open
              </span>
            )}
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-slate-500">
            {text.description}
          </p>
        </div>
      </div>

      {resolveMutation.isError && (
        <ErrorAlert action="Resolving the issue" error={resolveMutation.error} />
      )}

      {loading ? (
        <p className="py-4 text-sm text-slate-500">Loading recent batches…</p>
      ) : failed ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          Could not load validation issues.{" "}
          <button
            type="button"
            className="font-medium underline"
            onClick={() => {
              void batchesQuery.refetch();
              issueQueries.forEach((query) => void query.refetch());
            }}
          >
            Retry
          </button>
        </div>
      ) : groups.length === 0 ? (
        <p className="rounded-lg bg-emerald-50 p-5 text-center text-sm text-emerald-800">
          {text.empty}
        </p>
      ) : (
        <div className="space-y-4">
          {groups.map(({ batch, issues }) => (
            <article
              key={batch.id}
              className="space-y-3 rounded-lg border border-slate-200 p-4"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="min-w-0 break-words font-medium text-slate-900">
                  {batch.file_name}
                </h3>
                <p className="text-xs text-slate-500">
                  {new Date(batch.created_at).toLocaleString()} ·{" "}
                  <span className="capitalize">{batch.status}</span>
                </p>
              </div>
              <ul className="divide-y divide-slate-100">
                {issues.map((issue) => (
                  <li
                    key={issue.id}
                    className="flex flex-wrap items-start gap-x-3 gap-y-1 py-2 text-sm"
                  >
                    <span className="w-14 shrink-0 tabular-nums text-slate-500">
                      Row {issue.row_number}
                    </span>
                    <span
                      className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${severityStyles[issue.severity]}`}
                    >
                      {issue.severity}
                    </span>
                    <span className="min-w-0 flex-1 basis-48">
                      {issue.message}
                      <span className="ml-2 font-mono text-xs text-slate-400">
                        {issue.rule_code}
                      </span>
                    </span>
                    {mode === "resolve" && (
                      <button
                        type="button"
                        onClick={() => resolve(issue)}
                        disabled={Boolean(resolveHint) || resolveMutation.isPending}
                        title={resolveHint}
                        className="shrink-0 rounded-lg border border-indigo-300 px-2.5 py-1 text-xs font-medium text-indigo-800 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Resolve
                      </button>
                    )}
                  </li>
                ))}
              </ul>
              {mode === "fix" &&
                issues.some((issue) => issue.severity === "error") && (
                  <CorrectionUpload batch={batch} />
                )}
              {mode === "fix" &&
                issues.some((issue) => issue.severity === "warning") && (
                  <p className="text-xs text-slate-500">
                    Warnings are resolved by your institution admin.
                  </p>
                )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
