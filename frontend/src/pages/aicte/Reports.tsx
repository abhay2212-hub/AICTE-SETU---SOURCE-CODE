// Owner: Dev D

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { components } from "../../lib/api-types";
import { API_URL, apiWithMetadata } from "../../lib/api";
import { getIdentity, useActionHint } from "../../lib/roles";
import { apiErrorMessage } from "../../components/format";

type IntegrityRanking = components["schemas"]["IntegrityRanking"];
type EnrolmentReport = components["schemas"]["EnrolmentReport"];
type AccreditationReport = components["schemas"]["AccreditationReport"];

type GroupBy = "state" | "programme" | "category" | "gender";
type ExportFormat = "pdf" | "xlsx";

const panel = "rounded-xl border border-slate-200 bg-white p-5 shadow-sm";
const field =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100";
const button =
  "rounded-lg px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50";
const primaryButton = `${button} bg-slate-900 text-white hover:bg-slate-700`;
const secondaryButton = `${button} border border-slate-300 bg-white text-slate-700 hover:bg-slate-50`;

function ErrorMessage({ message }: { message: string }) {
  return (
    <p
      role="alert"
      className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800"
    >
      {message}
    </p>
  );
}

function readableError(error: unknown): string {
  return apiErrorMessage(error);
}

async function downloadReport(
  path: string,
  fallbackFilename: string,
): Promise<void> {
  const { role, institutionId } = getIdentity();
  const headers = new Headers();
  headers.set("X-Demo-Role", role);

  if (institutionId) {
    headers.set("X-Demo-Institution", institutionId);
  }

  const response = await fetch(`${API_URL}${path}`, { headers });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Download failed (${response.status}).`);
  }

  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition");
  const filenameMatch = disposition?.match(/filename="?([^";]+)"?/i);
  const filename = filenameMatch?.[1] || fallbackFilename;
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

export default function Reports({
  rankings,
}: {
  rankings: IntegrityRanking[];
}) {
  const [groupBy, setGroupBy] = useState<GroupBy>("state");
  const [institutionId, setInstitutionId] = useState("");

  const enrolmentQuery = useQuery({
    queryKey: ["aicte-enrolment-report", groupBy],
    queryFn: () =>
      apiWithMetadata<EnrolmentReport>(
        `/reports/enrolment?group_by=${encodeURIComponent(groupBy)}&format=json`,
      ),
    enabled: false,
    retry: false,
  });

  const accreditationQuery = useQuery({
    queryKey: ["aicte-accreditation-report", institutionId],
    queryFn: () =>
      apiWithMetadata<AccreditationReport>(
        `/reports/accreditation/${encodeURIComponent(institutionId)}?format=json`,
      ),
    enabled: false,
    retry: false,
  });

  const downloadHint = useActionHint("download_enrolment_report");
  const accreditationHint = useActionHint("load_accreditation_report");
  const [downloadError, setDownloadError] = useState("");
  const [downloading, setDownloading] = useState<ExportFormat | null>(null);

  async function handleDownload(format: ExportFormat) {
    setDownloadError("");
    setDownloading(format);

    try {
      await downloadReport(
        `/reports/enrolment?group_by=${encodeURIComponent(groupBy)}&format=${format}`,
        `enrolment-report-${groupBy}.${format}`,
      );
    } catch (error) {
      setDownloadError(readableError(error));
    } finally {
      setDownloading(null);
    }
  }

  const selectedInstitution = rankings.find(
    (item) => item.institution_id === institutionId,
  );

  return (
    <div className="space-y-6">
      <section className={panel}>
        <div>
          {enrolmentQuery.data?.isMock && <p className="text-xs font-semibold uppercase tracking-wide text-blue-700">SIMULATED</p>}
          <h2 className="mt-1 text-lg font-semibold text-slate-950">
            Enrolment reports
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Group enrolment data and preview or export the report.
          </p>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-[1fr_auto_auto_auto] sm:items-end">
          <div>
            <label
              htmlFor="enrolment-group"
              className="mb-1 block text-sm font-medium text-slate-700"
            >
              Group report by
            </label>
            <select
              id="enrolment-group"
              className={field}
              value={groupBy}
              onChange={(event) => {
                setGroupBy(event.target.value as GroupBy);
              }}
            >
              <option value="state">State</option>
              <option value="programme">Programme</option>
              <option value="category">Category</option>
              <option value="gender">Gender</option>
            </select>
          </div>

          <button
            type="button"
            className={secondaryButton}
            disabled={enrolmentQuery.isFetching}
            onClick={() => void enrolmentQuery.refetch()}
          >
            {enrolmentQuery.isFetching ? "Loading…" : "Preview JSON"}
          </button>

          <button
            type="button"
            className={secondaryButton}
            disabled={downloading !== null || Boolean(downloadHint)}
            title={downloadHint}
            onClick={() => void handleDownload("pdf")}
          >
            {downloading === "pdf" ? "Downloading…" : "Download PDF"}
          </button>

          <button
            type="button"
            className={primaryButton}
            disabled={downloading !== null || Boolean(downloadHint)}
            title={downloadHint}
            onClick={() => void handleDownload("xlsx")}
          >
            {downloading === "xlsx" ? "Downloading…" : "Download Excel"}
          </button>
        </div>

        {downloadError && (
          <div className="mt-4">
            <ErrorMessage message={downloadError} />
          </div>
        )}

        {enrolmentQuery.isError && (
          <div className="mt-4">
            <ErrorMessage
              message={`Unable to load the enrolment report: ${readableError(enrolmentQuery.error)}`}
            />
          </div>
        )}

        {enrolmentQuery.data && (
          <div className="mt-5">
            <div className="mb-2 flex items-center justify-between gap-3">
              <h3 className="font-medium text-slate-900">
                Enrolment report preview
              </h3>
              <button
                type="button"
                className="text-sm text-blue-700 underline"
                onClick={() =>
                  void navigator.clipboard.writeText(
                    JSON.stringify(enrolmentQuery.data.data, null, 2),
                  )
                }
              >
                Copy JSON
              </button>
            </div>
            <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-4 text-xs text-slate-700">
              {JSON.stringify(enrolmentQuery.data.data, null, 2)}
            </pre>
          </div>
        )}
      </section>

      <section className={panel}>
        <div>
          {accreditationQuery.data?.isMock && <p className="text-xs font-semibold uppercase tracking-wide text-blue-700">SIMULATED</p>}
          <h2 className="mt-1 text-lg font-semibold text-slate-950">
            Accreditation report
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Select a ranked institution to retrieve its accreditation report.
          </p>
        </div>

        <div className="mt-5 flex flex-col gap-3 sm:flex-row">
          <select
            aria-label="Select institution for accreditation report"
            className={field}
            value={institutionId}
            onChange={(event) => {
              setInstitutionId(event.target.value);
            }}
          >
            <option value="">Select an institution</option>
            {rankings.map((item) => (
              <option key={item.institution_id} value={item.institution_id}>
                {item.institution_name} ({item.aicte_code})
              </option>
            ))}
          </select>

          <button
            type="button"
            className={primaryButton}
            disabled={
              !institutionId ||
              accreditationQuery.isFetching ||
              Boolean(accreditationHint)
            }
            title={accreditationHint}
            onClick={() => void accreditationQuery.refetch()}
          >
            {accreditationQuery.isFetching ? "Loading…" : "Load report"}
          </button>
        </div>

        {selectedInstitution && (
          <p className="mt-2 break-all text-xs text-slate-500">
            Institution ID: {selectedInstitution.institution_id}
          </p>
        )}

        {accreditationQuery.isError && (
          <div className="mt-4">
            <ErrorMessage
              message={`Unable to load the accreditation report: ${readableError(accreditationQuery.error)}`}
            />
          </div>
        )}

        {accreditationQuery.data && (
          <div className="mt-5">
            {accreditationQuery.data.data.integrity_score == null && accreditationQuery.data.data.integrity_note && (
              <p className="mb-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">{accreditationQuery.data.data.integrity_note}</p>
            )}
            <h3 className="mb-2 font-medium text-slate-900">
              Accreditation report details
            </h3>
            <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-4 text-xs text-slate-700">
              {JSON.stringify(accreditationQuery.data.data, null, 2)}
            </pre>
          </div>
        )}
      </section>
    </div>
  );
}
