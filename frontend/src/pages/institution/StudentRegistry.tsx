
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "../../lib/api-types";
import { api } from "../../lib/api";
import { useActionHint } from "../../lib/roles";
import ErrorAlert from "../../components/ErrorAlert";

type Admission = components["schemas"]["Admission"];

interface Props {
  institutionId: string;
  academicYear: string;
}

const statusStyles: Record<Admission["status"], string> = {
  submitted: "bg-blue-100 text-blue-800",
  student_confirmed: "bg-emerald-100 text-emerald-800",
  student_disputed: "bg-red-100 text-red-800",
  no_response: "bg-amber-100 text-amber-800",
  withdrawn: "bg-slate-100 text-slate-600",
};

const pageSize = 20;

export default function StudentRegistry({
  institutionId,
  academicYear,
}: Props) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const queryClient = useQueryClient();
  const withdrawHint = useActionHint("withdraw_admission");

  const withdrawMutation = useMutation({
    mutationFn: (payload: { admissionId: string; reason: string }) =>
      api<Admission>(`/admissions/${payload.admissionId}/withdraw`, {
        method: "POST",
        body: JSON.stringify({ reason: payload.reason }),
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ["institution-admissions", institutionId],
        }),
        queryClient.invalidateQueries({
          queryKey: ["seat-ledger", institutionId],
        }),
      ]);
    },
  });

  function withdraw(admission: Admission) {
    const reason = window
      .prompt(
        `Reason for withdrawing ${admission.student_name}? This releases the seat.`,
      )
      ?.trim();
    if (!reason) return;
    withdrawMutation.mutate({ admissionId: admission.id, reason });
  }

  const query = useQuery({
    queryKey: [
      "institution-admissions",
      institutionId,
      academicYear,
      status,
      offset,
      search.trim().toLowerCase(),
    ],
    queryFn: async () => {
      const term = search.trim().toLowerCase();

      const fetchPage = async (pageOffset: number) => {
        const params = new URLSearchParams({
          institution_id: institutionId,
          academic_year: academicYear,
          limit: String(pageSize),
          offset: String(pageOffset),
        });

        if (status) {
          params.set("status", status);
        }

        return api<Admission[]>(`/admissions?${params.toString()}`);
      };

      // Normal browsing: fetch only the current page.
      if (!term) {
        return {
          admissions: await fetchPage(offset),
          totalMatches: null as number | null,
        };
      }

      // Search across every page returned by the API.
      const matches: Admission[] = [];
      let pageOffset = 0;

      while (true) {
        const page = await fetchPage(pageOffset);

        matches.push(
          ...page.filter((admission) =>
            [
              admission.student_name,
              admission.apaar_id_masked ?? "",
              admission.provisional_id ?? "",
              admission.programme_code,
            ].some((value) =>
              value.toLowerCase().includes(term),
            ),
          ),
        );

        if (page.length < pageSize) {
          break;
        }

        pageOffset += pageSize;
      }

      return {
        admissions: matches.slice(offset, offset + pageSize),
        totalMatches: matches.length,
      };
    },
    enabled: Boolean(institutionId),
  });

  const admissions = query.data?.admissions ?? [];
  const totalMatches = query.data?.totalMatches ?? null;
  const isSearching = Boolean(search.trim());

  return (
    <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">
          Student Registry
        </h2>
        <p className="mt-1 text-sm text-slate-500">
          Admission records for academic year {academicYear}.
          APAAR identifiers are displayed in masked form.
        </p>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row">
        <label className="flex-1">
          <span className="sr-only">Search student records</span>
          <input
            type="search"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setOffset(0);
            }}
            placeholder="Search name, masked APAAR, provisional ID or programme…"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
        </label>

        <label>
          <span className="sr-only">Filter by admission status</span>
          <select
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setOffset(0);
            }}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
          >
            <option value="">All statuses</option>
            <option value="submitted">Submitted</option>
            <option value="student_confirmed">Student confirmed</option>
            <option value="student_disputed">Student disputed</option>
            <option value="no_response">No response</option>
            <option value="withdrawn">Withdrawn</option>
          </select>
        </label>

        <button
          type="button"
          onClick={() => void query.refetch()}
          disabled={query.isFetching}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50 disabled:opacity-50"
        >
          {query.isFetching ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {withdrawHint && (
        <p id="withdraw-hint" className="text-xs text-slate-500">
          Withdraw: {withdrawHint}
        </p>
      )}

      {withdrawMutation.isError && (
        <ErrorAlert
          action="Withdrawing the admission"
          error={withdrawMutation.error}
        />
      )}

      {query.isPending ? (
        <p className="py-8 text-center text-sm text-slate-500">
          {isSearching
            ? "Searching all student records…"
            : "Loading student records…"}
        </p>
      ) : query.isError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <p>Could not load student records.</p>
          <button
            type="button"
            onClick={() => void query.refetch()}
            className="mt-2 underline"
          >
            Retry
          </button>
        </div>
      ) : admissions.length === 0 ? (
        <p className="rounded-lg bg-slate-50 p-8 text-center text-sm text-slate-500">
          {isSearching
            ? "No records match your search."
            : "No admission records found for this academic year."}
        </p>
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-slate-200">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">Student</th>
                  <th className="px-4 py-3">APAAR ID</th>
                  <th className="px-4 py-3">Provisional ID</th>
                  <th className="px-4 py-3">Programme</th>
                  <th className="px-4 py-3">Admission date</th>
                  <th className="px-4 py-3">Seat pool</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Action</th>
                </tr>
              </thead>

              <tbody className="divide-y divide-slate-100">
                {admissions.map((admission) => (
                  <tr
                    key={admission.id}
                    className="align-top hover:bg-slate-50"
                  >
                    <td className="px-4 py-3 font-medium text-slate-900">
                      {admission.student_name}
                    </td>

                    <td className="whitespace-nowrap px-4 py-3 font-mono text-xs">
                      {admission.apaar_id_masked ?? "Not available"}
                    </td>

                    <td className="px-4 py-3">
                      {admission.provisional_id ?? "—"}
                    </td>

                    <td className="px-4 py-3">
                      {admission.programme_code}
                    </td>

                    <td className="whitespace-nowrap px-4 py-3">
                      {admission.admission_date}
                    </td>

                    <td className="px-4 py-3">
                      {admission.seat_pool.replaceAll("_", " ")}
                    </td>

                    <td className="px-4 py-3">
                      <span
                        className={`whitespace-nowrap rounded-full px-2 py-1 text-xs font-medium ${
                          statusStyles[admission.status]
                        }`}
                      >
                        {admission.status.replaceAll("_", " ")}
                      </span>
                    </td>

                    <td className="px-4 py-3">
                      {admission.status !== "withdrawn" && (
                        <button
                          type="button"
                          onClick={() => withdraw(admission)}
                          disabled={
                            Boolean(withdrawHint) || withdrawMutation.isPending
                          }
                          title={withdrawHint}
                          aria-describedby={
                            withdrawHint ? "withdraw-hint" : undefined
                          }
                          className="rounded-lg border border-slate-300 px-2.5 py-1 text-xs font-medium hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          Withdraw
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-slate-500">
              {isSearching
                ? `${totalMatches ?? 0} matching records`
                : `Page ${Math.floor(offset / pageSize) + 1} · Showing ${admissions.length} records`}
            </p>

            <div className="flex gap-2">
              <button
                type="button"
                disabled={offset === 0 || query.isFetching}
                onClick={() =>
                  setOffset((current) =>
                    Math.max(0, current - pageSize),
                  )
                }
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm disabled:opacity-40"
              >
                Previous
              </button>

              <button
                type="button"
                disabled={
                  query.isFetching ||
                  (isSearching
                    ? offset + pageSize >= (totalMatches ?? 0)
                    : admissions.length < pageSize)
                }
                onClick={() =>
                  setOffset((current) => current + pageSize)
                }
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
