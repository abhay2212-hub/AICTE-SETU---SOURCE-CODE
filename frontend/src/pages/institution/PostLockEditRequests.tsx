// Owner: Dev D
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "../../lib/api-types";
import { api } from "../../lib/api";
import ErrorAlert from "../../components/ErrorAlert";
import { actorLabel } from "../../components/format";
import { useActionHint } from "../../lib/roles";

type Admission = components["schemas"]["Admission"];
type EditRequest = components["schemas"]["EditRequest"];
type EditRequestCreate = components["schemas"]["EditRequestCreate"];
type EditableField = components["schemas"]["EditableField"];

// Display names only; which fields exist, their types and allowed values come from
// GET /edit-requests/fields.
const fieldLabels: Record<string, string> = {
  admission_date: "Admission date",
  admission_mode: "Admission mode",
  qualifying_exam_pct: "Qualifying exam percentage",
  student_name: "Student name",
  dob: "Date of birth",
  withdrawal: "Withdrawal",
};

function fieldLabel(name: string): string {
  const label = fieldLabels[name] ?? name.replaceAll("_", " ");
  return label.charAt(0).toUpperCase() + label.slice(1);
}

const input =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm";

const statusStyles: Record<EditRequest["status"], string> = {
  pending: "bg-amber-100 text-amber-800",
  approved: "bg-emerald-100 text-emerald-800",
  rejected: "bg-red-100 text-red-800",
};

interface Props {
  institutionId: string;
  academicYear: string;
  title?: string;
  description?: string;
}

export default function PostLockEditRequests({
  institutionId,
  academicYear,
  title = "Post-lock Edit Requests",
  description = "Submit admission corrections for review after the submission window closes or locks. Requests require AICTE approval before changes are applied.",
}: Props) {
  const queryClient = useQueryClient();
  const requestHint = useActionHint("request_edit");

  const [admissionId, setAdmissionId] = useState("");
  const [selectedField, setSelectedField] = useState("");
  const [newValue, setNewValue] = useState("");
  const [reason, setReason] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const fieldsQuery = useQuery({
    queryKey: ["edit-request-fields"],
    queryFn: () => api<EditableField[]>("/edit-requests/fields"),
    staleTime: Infinity,
  });

  const fields = fieldsQuery.data ?? [];
  const field = selectedField || fields[0]?.field || "";
  const fieldSpec = fields.find((item) => item.field === field);

  const admissionsQuery = useQuery({
    queryKey: ["edit-request-admissions", institutionId, academicYear],
    queryFn: () => {
      const params = new URLSearchParams({
        institution_id: institutionId,
        academic_year: academicYear,
        limit: "100",
        offset: "0",
      });
      return api<Admission[]>(`/admissions?${params.toString()}`);
    },
    enabled: Boolean(institutionId),
  });

  const requestsQuery = useQuery({
    queryKey: [
      "institution-edit-requests",
      institutionId,
      academicYear,
      statusFilter,
    ],
    queryFn: () => {
      const params = new URLSearchParams({
        institution_id: institutionId,
        academic_year: academicYear,
        limit: "100",
        offset: "0",
      });

      if (statusFilter) params.set("status", statusFilter);

      return api<EditRequest[]>(`/edit-requests?${params.toString()}`);
    },
    enabled: Boolean(institutionId),
  });

  const createMutation = useMutation({
    mutationFn: (payload: {
      admissionId: string;
      body: EditRequestCreate;
    }) =>
      api<EditRequest>(
        `/admissions/${payload.admissionId}/edit-requests`,
        {
          method: "POST",
          body: JSON.stringify(payload.body),
        },
      ),
    onSuccess: async () => {
      setNewValue("");
      setReason("");
      await queryClient.invalidateQueries({
        queryKey: ["institution-edit-requests", institutionId],
      });
    },
  });

  const admissions = admissionsQuery.data ?? [];
  const requests = requestsQuery.data ?? [];

  function submitRequest(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!admissionId || !field || !newValue.trim() || !reason.trim()) return;

    createMutation.mutate({
      admissionId,
      body: { field, new_value: newValue.trim(), reason: reason.trim() },
    });
  }

  return (
    <section className="space-y-5 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
        <p className="mt-1 text-sm text-slate-500">{description}</p>
      </div>

      <form
        onSubmit={submitRequest}
        className="space-y-4 rounded-lg border border-slate-200 p-4"
      >
        <h3 className="font-medium text-slate-900">Request an admission change</h3>

        {admissionsQuery.isError ? (
          <p className="text-sm text-red-700">
            Could not load admissions. Refresh the page and try again.
          </p>
        ) : (
          <label className="block space-y-1">
            <span className="text-sm font-medium text-slate-700">
              Student admission
            </span>
            <select
              required
              value={admissionId}
              onChange={(event) => setAdmissionId(event.target.value)}
              disabled={admissionsQuery.isPending || admissions.length === 0}
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
            >
              <option value="">
                {admissionsQuery.isPending
                  ? "Loading admissions…"
                  : admissions.length === 0
                    ? "No admissions available"
                    : "Select a student"}
              </option>
              {admissions.map((admission) => (
                <option key={admission.id} value={admission.id}>
                  {admission.student_name} — {admission.programme_code}
                  {admission.apaar_id_masked
                    ? ` — ${admission.apaar_id_masked}`
                    : ""}
                </option>
              ))}
            </select>
            <span className="text-xs text-slate-500">
              APAAR identifiers are shown only in masked form.
            </span>
          </label>
        )}

        {fieldsQuery.isError ? (
          <ErrorAlert
            action="Loading the editable fields"
            error={fieldsQuery.error}
          />
        ) : (
          <label className="block space-y-1">
            <span className="text-sm font-medium text-slate-700">
              Field to change
            </span>
            <select
              value={field}
              disabled={fieldsQuery.isPending}
              onChange={(event) => {
                setSelectedField(event.target.value);
                setNewValue("");
              }}
              className={input}
            >
              {fieldsQuery.isPending && (
                <option value="">Loading fields…</option>
              )}
              {fields.map((item) => (
                <option key={item.field} value={item.field}>
                  {fieldLabel(item.field)}
                </option>
              ))}
            </select>
          </label>
        )}

        {field === "withdrawal" && (
          <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
            This requests withdrawal of the admission. If approved, the
            backend will process the withdrawal and release the seat.
          </p>
        )}

        {fieldSpec && (
          <label className="block space-y-1">
            <span className="text-sm font-medium text-slate-700">
              Proposed value
            </span>
            {fieldSpec.type === "enum" ? (
              <select
                required
                value={newValue}
                onChange={(event) => setNewValue(event.target.value)}
                className={input}
              >
                <option value="">Select a value</option>
                {(fieldSpec.allowed_values ?? []).map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            ) : (
              <input
                required
                value={newValue}
                onChange={(event) => setNewValue(event.target.value)}
                type={
                  fieldSpec.type === "date"
                    ? "date"
                    : fieldSpec.type === "number"
                      ? "number"
                      : "text"
                }
                step={fieldSpec.type === "number" ? "any" : undefined}
                className={input}
                placeholder="Enter the corrected value"
              />
            )}
            {fieldSpec.type === "enum" && fieldSpec.allowed_values && (
              <span className="block text-xs text-slate-500">
                Allowed values: {fieldSpec.allowed_values.join(", ")}
              </span>
            )}
          </label>
        )}

        <label className="block space-y-1">
          <span className="text-sm font-medium text-slate-700">
            Reason for request
          </span>
          <textarea
            required
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            rows={3}
            maxLength={1000}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            placeholder="Explain why this correction is needed…"
          />
        </label>

        {createMutation.isError && (
          <ErrorAlert
            action="Submitting the edit request"
            error={createMutation.error}
          />
        )}

        {createMutation.isSuccess && (
          <p role="status" className="text-sm text-emerald-700">
            Edit request submitted successfully.
          </p>
        )}

        <button
          type="submit"
          disabled={
            createMutation.isPending ||
            Boolean(requestHint) ||
            !admissionId ||
            !field ||
            !reason.trim() ||
            !newValue.trim()
          }
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {createMutation.isPending ? "Submitting…" : "Submit edit request"}
        </button>
        {requestHint && <p className="text-xs text-slate-500">{requestHint}</p>}
      </form>

      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="font-medium text-slate-900">Request history</h3>
            <p className="text-sm text-slate-500">
              Requests for academic year {academicYear}.
            </p>
          </div>

          <div className="flex gap-2">
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              aria-label="Filter edit requests by status"
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
            >
              <option value="">All statuses</option>
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
            </select>

            <button
              type="button"
              onClick={() => void requestsQuery.refetch()}
              disabled={requestsQuery.isFetching}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50 disabled:opacity-50"
            >
              {requestsQuery.isFetching ? "Refreshing…" : "Refresh"}
            </button>
          </div>
        </div>

        {requestsQuery.isPending ? (
          <p className="py-5 text-sm text-slate-500">
            Loading edit requests…
          </p>
        ) : requestsQuery.isError ? (
          <div className="space-y-2">
            <ErrorAlert
              action="Loading edit requests"
              error={requestsQuery.error}
            />
            <button
              type="button"
              onClick={() => void requestsQuery.refetch()}
              className="text-sm text-red-800 underline"
            >
              Retry
            </button>
          </div>
        ) : requests.length === 0 ? (
          <p className="rounded-lg bg-slate-50 p-6 text-center text-sm text-slate-500">
            No edit requests found.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-slate-200">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-3 py-3">Student</th>
                  <th className="px-3 py-3">Field</th>
                  <th className="px-3 py-3">Proposed value</th>
                  <th className="px-3 py-3">Reason</th>
                  <th className="px-3 py-3">Status</th>
                  <th className="px-3 py-3">Requested by</th>
                  <th className="px-3 py-3">Decided by</th>
                  <th className="px-3 py-3">Decision note</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {requests.map((request) => (
                  <tr key={request.id} className="align-top hover:bg-slate-50">
                    <td className="px-3 py-3">
                      <p className="font-medium text-slate-900">
                        {request.admission?.student_name ?? "Admission"}
                      </p>
                      <p className="mt-1 font-mono text-xs text-slate-500">
                        {request.admission?.apaar_id_masked ?? ""}
                      </p>
                    </td>
                    <td className="px-3 py-3">
                      {fieldLabel(request.field)}
                    </td>
                    <td className="px-3 py-3">
                      {request.old_value != null && (
                        <span className="text-slate-500">
                          {request.old_value} →{" "}
                        </span>
                      )}
                      <span className="font-medium">{request.new_value}</span>
                    </td>
                    <td className="max-w-64 whitespace-normal px-3 py-3">
                      {request.reason}
                    </td>
                    <td className="px-3 py-3">
                      <span
                        className={`whitespace-nowrap rounded-full px-2 py-1 text-xs font-medium ${statusStyles[request.status]}`}
                      >
                        {request.status}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-3 py-3">
                      <p>{actorLabel(request.requested_by)}</p>
                      <p className="mt-1 text-xs text-slate-500">
                        {new Date(request.created_at).toLocaleDateString()}
                      </p>
                    </td>
                    <td className="whitespace-nowrap px-3 py-3">
                      <p>{actorLabel(request.decided_by)}</p>
                      {request.decided_at && (
                        <p className="mt-1 text-xs text-slate-500">
                          {new Date(request.decided_at).toLocaleDateString()}
                        </p>
                      )}
                    </td>
                    <td className="px-3 py-3">
                      {request.decision_note || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
