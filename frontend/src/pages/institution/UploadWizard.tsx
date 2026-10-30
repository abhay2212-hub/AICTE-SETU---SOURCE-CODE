import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { components } from "../../lib/api-types";
import { api } from "../../lib/api";
import { apiErrorMessage } from "../../components/format";
import { useActionHint } from "../../lib/roles";

type Batch = components["schemas"]["Batch"];
type UploadResult = Omit<
  components["schemas"]["BatchUploadResult"],
  "duplicate_upload"
> & {
  duplicate_upload?: boolean;
};
type ValidationIssue = components["schemas"]["ValidationIssue"];
type CommitResult = components["schemas"]["CommitResult"];

const destinationColumns = [
  "institution_aicte_code",
  "programme_code",
  "academic_year",
  "student_name",
  "dob",
  "gender",
  "category",
  "pwd",
  "apaar_id",
  "apaar_opt_out",
  "provisional_id",
  "nationality",
  "oci_status",
  "fn_status",
  "nri_category",
  "seat_pool",
  "admission_mode",
  "admission_date",
  "qualifying_exam",
  "qualifying_exam_pct",
  "domicile_state",
  "contact_phone",
  "contact_email",
  "guardian_name",
] as const;

const requiredColumns = new Set<string>([
  "institution_aicte_code",
  "programme_code",
  "academic_year",
  "student_name",
  "dob",
  "gender",
  "category",
  "pwd",
  "apaar_opt_out",
  "nationality",
  "oci_status",
  "fn_status",
  "nri_category",
  "seat_pool",
  "admission_mode",
  "admission_date",
  "qualifying_exam",
  "qualifying_exam_pct",
  "domicile_state",
]);

function destinationLabel(column: string): string {
  return column
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
const severityStyles: Record<ValidationIssue["severity"], string> = {
  error: "bg-red-100 text-red-800",
  warning: "bg-amber-100 text-amber-800",
  review: "bg-violet-100 text-violet-800",
  info: "bg-sky-100 text-sky-800",
};

export default function UploadWizard({
  institutionId,
}: {
  institutionId: string;
}) {
  const queryClient = useQueryClient();
  const uploadHint = useActionHint("upload_batch");
  const mapHint = useActionHint("map_batch");
  const commitHint = useActionHint("commit_batch");
  const [file, setFile] = useState<File | null>(null);
  const [upload, setUpload] = useState<UploadResult | null>(null);
  const [batch, setBatch] = useState<Batch | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [issues, setIssues] = useState<ValidationIssue[]>([]);
  const [commitResult, setCommitResult] = useState<CommitResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState<
    "upload" | "mapping" | "review" | "committed"
  >("upload");

  const destinationOptions = destinationColumns.map(
    (column) => [column, destinationLabel(column)] as const,
  );

  function resetWizard() {
    setFile(null);
    setUpload(null);
    setBatch(null);
    setMapping({});
    setIssues([]);
    setCommitResult(null);
    setError("");
    setStep("upload");
  }

  async function uploadFile() {
    if (!file) {
      setError("Choose a CSV or XLSX file first.");
      return;
    }

    setBusy(true);
    setError("");
    setCommitResult(null);

    try {
      const body = new FormData();
      body.append("file", file);

      const result = await api<UploadResult>("/batches", {
        method: "POST",
        body,
      });

      setUpload(result);
      setBatch(result.batch);
      setMapping(result.suggested_mapping ?? {});
      setIssues([]);
      setStep("mapping");
    } catch (cause) {
      setError(apiErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function saveMapping() {
    if (!upload || !batch) return;

    const selectedTargets = Object.values(mapping).filter(Boolean);
    if (new Set(selectedTargets).size !== selectedTargets.length) {
      setError("Each template column can be mapped only once.");
      return;
    }

    setBusy(true);
    setError("");

    try {
      const updatedBatch = await api<Batch>(`/batches/${batch.id}/mapping`, {
        method: "POST",
        body: JSON.stringify({ mapping }),
      });

      setBatch(updatedBatch);

      const [latestBatch, latestIssues] = await Promise.all([
        api<Batch>(`/batches/${batch.id}`),
        api<ValidationIssue[]>(`/batches/${batch.id}/issues`),
      ]);

      setBatch(latestBatch);
      setIssues(latestIssues);
      setStep("review");
    } catch (cause) {
      setError(apiErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function commitBatch() {
    if (!batch) return;

    if (issues.some((issue) => issue.severity === "error" && !issue.resolved)) {
      setError(
        "Resolve or correct the blocking validation errors before committing.",
      );
      return;
    }

    const confirmed = window.confirm(
      "Commit the valid rows in this batch to the Seat Ledger? This action cannot be undone from this screen.",
    );
    if (!confirmed) return;

    setBusy(true);
    setError("");

    try {
      const result = await api<CommitResult>(`/batches/${batch.id}/commit`, {
        method: "POST",
      });

      setCommitResult(result);
      setBatch(await api<Batch>(`/batches/${batch.id}`));
      setStep("committed");

      await queryClient.invalidateQueries({
        queryKey: ["seat-ledger", institutionId],
      });
    } catch (cause) {
      setError(apiErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-5 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <header className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
        <div>
          <p className="text-sm font-medium text-indigo-700">
            Admissions ingestion
          </p>
          <h2 className="mt-1 text-xl font-semibold text-slate-900">
            Upload admissions data
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Upload a file, verify its column mapping, review validation results,
            and explicitly commit valid rows.
          </p>
        </div>
        {step !== "upload" && (
          <button
            type="button"
            onClick={resetWizard}
            disabled={busy}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50 disabled:opacity-50"
          >
            Start new upload
          </button>
        )}
      </header>

      <ol className="grid gap-2 text-sm sm:grid-cols-4">
        {(["upload", "mapping", "review", "committed"] as const).map(
          (item, index) => (
            <li
              key={item}
              className={`rounded-lg border p-3 ${
                step === item
                  ? "border-indigo-300 bg-indigo-50 text-indigo-900"
                  : "border-slate-200 text-slate-500"
              }`}
            >
              <span className="font-medium">{index + 1}. </span>
              {
                [
                  "Upload file",
                  "Map columns",
                  "Review issues",
                  "Commit result",
                ][index]
              }
            </li>
          ),
        )}
      </ol>

      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800"
        >
          {error}
        </div>
      )}

      {step === "upload" && (
        <div className="space-y-3 rounded-lg border border-dashed border-slate-300 p-5">
          <label
            htmlFor="admissions-file"
            className="block text-sm font-medium text-slate-800"
          >
            Admissions file (CSV or XLSX)
          </label>
          <input
            id="admissions-file"
            type="file"
            accept=".csv,.xlsx"
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setError("");
            }}
            className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-2"
          />
          <p className="text-xs text-slate-500">
            Use synthetic or approved test data. Do not upload real Aadhaar
            numbers or other unnecessary sensitive information.
          </p>
          <button
            type="button"
            onClick={() => void uploadFile()}
            disabled={!file || busy || Boolean(uploadHint)}
            title={uploadHint}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {busy ? "Uploading…" : "Upload and suggest mapping"}
          </button>
          {uploadHint && <p className="text-xs text-slate-500">{uploadHint}</p>}
        </div>
      )}

      {step === "mapping" && upload && batch && (
        <div className="space-y-4">
          <div className="rounded-lg bg-slate-50 p-4 text-sm">
            <p className="font-medium text-slate-900">{batch.file_name}</p>
            <p className="mt-1 text-slate-500">
              Batch status: {batch.status} · {batch.counts.rows_total} rows
            </p>
            {upload.duplicate_upload && (
              <p className="mt-2 text-amber-800">
                This file was already uploaded. The existing batch is being
                displayed.
              </p>
            )}
          </div>

          {upload.missing_required.length > 0 && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              Required template columns still missing:{" "}
              {upload.missing_required.join(", ")}
            </div>
          )}

          {upload.unmapped_columns.length > 0 && (
            <p className="text-sm text-slate-600">
              Unmapped source columns: {upload.unmapped_columns.join(", ")}
            </p>
          )}

          <div className="overflow-x-auto rounded-lg border border-slate-200">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">Uploaded column</th>
                  <th className="px-4 py-3">Template column</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {Array.from(
                  new Set([
                    ...Object.keys(upload.suggested_mapping),
                    ...upload.unmapped_columns,
                  ]),
                ).map((source) => (
                  <tr key={source}>
                    <td className="px-4 py-3 font-medium">{source}</td>
                    <td className="px-4 py-3">
                      <select
                        aria-label={`Map ${source}`}
                        value={mapping[source] ?? ""}
                        onChange={(event) =>
                          setMapping((current) => {
                            const next = { ...current };
                            if (event.target.value)
                              next[source] = event.target.value;
                            else delete next[source];
                            return next;
                          })
                        }
                        className="w-full rounded-md border border-slate-300 bg-white px-3 py-2"
                      >
                        <option value="">Do not map</option>
                        {destinationOptions.map(([value, label]) => {
                          const usedByOther = Object.entries(mapping).some(
                            ([key, target]) =>
                              key !== source && target === value,
                          );
                          return (
                            <option
                              key={value}
                              value={value}
                              disabled={usedByOther}
                            >
                              {label}
                              {requiredColumns.has(value) ? " *" : ""} ({value})
                            </option>
                          );
                        })}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <button
            type="button"
            onClick={() => void saveMapping()}
            disabled={busy || Boolean(mapHint)}
            title={mapHint}
            className="rounded-lg bg-indigo-700 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-600 disabled:opacity-50"
          >
            {busy ? "Applying mapping…" : "Apply mapping and validate"}
          </button>
          {mapHint && <p className="text-xs text-slate-500">{mapHint}</p>}
        </div>
      )}

      {step === "review" && batch && (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {[
              ["Rows", batch.counts.rows_total],
              ["Errors", batch.counts.errors],
              ["Warnings", batch.counts.warnings],
              ["Review", batch.counts.review],
              ["Info", batch.counts.info],
            ].map(([label, value]) => (
              <div
                key={label}
                className="rounded-lg border border-slate-200 p-3"
              >
                <p className="text-xs text-slate-500">{label}</p>
                <p className="mt-1 text-xl font-semibold">{value}</p>
              </div>
            ))}
          </div>

          {issues.some(
            (issue) => issue.severity === "error" && !issue.resolved,
          ) && (
            <p
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800"
            >
              This batch has unresolved errors. Resolve or correct them before
              committing.
            </p>
          )}

          {issues.length === 0 ? (
            <p className="rounded-lg bg-slate-50 p-4 text-sm text-slate-600">
              The API returned no validation issues for this batch.
            </p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-3 py-3">Row</th>
                    <th className="px-3 py-3">Severity</th>
                    <th className="px-3 py-3">Rule</th>
                    <th className="px-3 py-3">Message</th>
                    <th className="px-3 py-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {issues.map((issue) => (
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
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <p className="text-xs text-slate-500">
            This screen displays validation results; it does not mark issues as
            resolved or alter admissions records.
          </p>

          <button
            type="button"
            onClick={() => void commitBatch()}
            disabled={busy || batch.status === "committed" || Boolean(commitHint)}
            title={commitHint}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {busy ? "Processing…" : "Commit valid rows"}
          </button>
          {commitHint && <p className="text-xs text-slate-500">{commitHint}</p>}
        </div>
      )}

      {step === "committed" && commitResult && (
        <div className="space-y-4 rounded-lg border border-emerald-200 bg-emerald-50 p-5">
          <h3 className="text-lg font-semibold text-emerald-900">
            Commit confirmed by API
          </h3>
          <p className="text-sm text-emerald-800">
            Batch {commitResult.batch_id} · Status: {commitResult.status}
          </p>
          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <p className="text-xs text-emerald-800">Rows committed</p>
              <p className="text-2xl font-semibold text-emerald-950">
                {commitResult.rows_committed}
              </p>
            </div>
            <div>
              <p className="text-xs text-emerald-800">Rows rejected</p>
              <p className="text-2xl font-semibold text-emerald-950">
                {commitResult.rows_rejected}
              </p>
            </div>
            <div>
              <p className="text-xs text-emerald-800">Existing rows skipped</p>
              <p className="text-2xl font-semibold text-emerald-950">
                {commitResult.rows_skipped_existing}
              </p>
            </div>
          </div>
          {commitResult.review_cases_created.length > 0 && (
            <p className="text-sm text-emerald-900">
              Review cases created: {commitResult.review_cases_created.length}
            </p>
          )}
          <p className="text-sm text-emerald-800">
            The Seat Ledger query has been invalidated so the dashboard can
            fetch updated figures.
          </p>
        </div>
      )}
    </section>
  );
}
