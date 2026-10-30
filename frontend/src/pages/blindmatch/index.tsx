// Owner: Dev D

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { useIdentity } from "../../lib/roles";
import { viewerHeader } from "../../lib/dashboards";
import DashboardHeader, { ReadOnlyBanner } from "../../components/DashboardHeader";
import type { components } from "../../lib/api-types";

type BlindMatchCase = components["schemas"]["BlindMatchCase"];

function formatScore(score: number) {
  return Number.isFinite(score) ? score.toFixed(3) : "Unavailable";
}

function scorePercent(score: number) {
  if (!Number.isFinite(score)) return 0;
  const percent = score <= 1 ? score * 100 : score;
  return Math.max(0, Math.min(100, percent));
}

function formatDate(value?: string | null) {
  if (!value) return "Timestamp unavailable";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Timestamp unavailable"
    : date.toLocaleString();
}

function statusStyle(status: string) {
  switch (status.toLowerCase()) {
    case "confirmed":
    case "dismissed":
      return "border-emerald-200 bg-emerald-50 text-emerald-800";
    case "open":
    case "correction_requested":
      return "border-amber-200 bg-amber-50 text-amber-800";
    default:
      return "border-slate-200 bg-slate-100 text-slate-700";
  }
}

function BarcodeAnimation() {
  const bars = [
    2, 1, 3, 1, 2, 4, 1, 2, 1, 3, 2, 1, 4, 2, 1, 3, 1, 2, 4, 1, 3, 2, 1, 4, 1,
    2, 3, 1, 2, 4, 1, 3, 2, 1, 4, 2,
  ];

  return (
    <div className="w-full max-w-64">
      <style>
        {`
          @keyframes blind-match-scan {
            from { left: 4%; }
            to { left: 96%; }
          }
        `}
      </style>

      <div className="relative overflow-hidden rounded-xl border border-cyan-400/20 bg-slate-900 p-4">
        <div
          aria-hidden="true"
          className="relative flex h-20 items-center justify-center gap-[3px] overflow-hidden"
        >
          {bars.map((width, index) => (
            <span
              key={index}
              className="shrink-0 rounded-sm bg-cyan-300/80"
              style={{
                width: `${width * 2}px`,
                height: `${35 + ((index * 17) % 45)}%`,
              }}
            />
          ))}

          <span
            className="absolute inset-y-0 w-1 bg-cyan-300 shadow-[0_0_18px_5px_rgba(103,232,249,0.35)]"
            style={{
              animation: "blind-match-scan 2.5s ease-in-out infinite alternate",
            }}
          />
        </div>

        <div className="mt-3 flex items-center justify-between gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-widest text-cyan-300">
            Blind comparison
          </span>
          <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
        </div>
      </div>

      <p className="mt-2 text-center text-xs leading-5 text-slate-400">
        Illustrative animation · No identity data encoded
      </p>
    </div>
  );
}

function MetadataValue({ value }: { value?: string | null }) {
  return (
    <p className="mt-1 break-words text-sm text-slate-700">
      {value || "Not available"}
    </p>
  );
}

export default function BlindMatchPage() {
  const { role } = useIdentity();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const canSeeIdentityHints = role === "aicte_admin" || role === "auditor";

  const query = useQuery({
    queryKey: ["blind-match-cases", role],
    queryFn: () => api<BlindMatchCase[]>("/blind-match/cases"),
  });

  const cases = Array.isArray(query.data) ? query.data : [];
  const selectedCase = cases.find((item) => item.id === selectedId) ?? cases[0];

  const averageScore =
    cases.length > 0
      ? cases.reduce((total, item) => total + item.dice, 0) / cases.length
      : null;

  return (
    <div className="space-y-6" data-role-dashboard={role}>
      {role === "auditor" && (
        <ReadOnlyBanner>
          You can view, verify and download. Decisions and edits are made by
          AICTE admins.
        </ReadOnlyBanner>
      )}
      <DashboardHeader
        header={viewerHeader(
          role,
          "Blind Match",
          "Same student at two institutions, found without sharing identity",
        )}
        eyebrow="Privacy-preserving matching"
        actions={<BarcodeAnimation />}
      >
        <div className="flex flex-wrap gap-2">
          <span className="rounded-lg border border-white/20 bg-white/10 px-3 py-2 text-xs text-white/85">
            Dice similarity
          </span>
          <span className="rounded-lg border border-white/20 bg-white/10 px-3 py-2 text-xs text-white/85">
            Role-based visibility
          </span>
        </div>

        <div className="mt-5 grid grid-cols-1 rounded-xl border border-white/15 bg-black/15 sm:grid-cols-3">
          <div className="border-b border-white/15 p-4 sm:border-b-0 sm:border-r">
            <p className="text-xs uppercase tracking-wider text-white/65">
              Cases returned
            </p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">
              {query.isSuccess ? cases.length : "—"}
            </p>
            <p className="mt-1 text-xs text-white/65">From the cases API</p>
          </div>

          <div className="border-b border-white/15 p-4 sm:border-b-0 sm:border-r">
            <p className="text-xs uppercase tracking-wider text-white/65">
              Identity exposure
            </p>
            <p className="mt-1 font-medium">Role-restricted</p>
            <p className="mt-1 text-xs text-white/65">
              API-enforced visibility
            </p>
          </div>

          <div className="p-4">
            <p className="text-xs uppercase tracking-wider text-white/65">
              Average returned score
            </p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">
              {averageScore === null ? "—" : formatScore(averageScore)}
            </p>
            <p className="mt-1 text-xs text-white/65">Across returned cases</p>
          </div>
        </div>
      </DashboardHeader>

      {/* Loading */}
      {query.isPending && (
        <div className="rounded-xl border border-slate-200 bg-white p-8 text-center">
          <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
          <p className="mt-4 font-medium text-slate-800">Loading match cases</p>
          <p className="mt-1 text-sm text-slate-500">
            Retrieving available case records.
          </p>
        </div>
      )}

      {/* Error */}
      {query.isError && (
        <div
          role="alert"
          className="rounded-xl border border-red-200 bg-red-50 p-5"
        >
          <h2 className="font-semibold text-red-900">
            Could not load match cases
          </h2>
          <p className="mt-1 text-sm text-red-800">
            Check your API connection and permissions, then try again.
          </p>
          <button
            type="button"
            onClick={() => void query.refetch()}
            className="mt-4 rounded-lg bg-red-700 px-4 py-2 text-sm font-semibold text-white hover:bg-red-800"
          >
            Retry request
          </button>
        </div>
      )}

      {/* Empty state */}
      {query.isSuccess && cases.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-xl text-slate-500">
            ↔
          </div>
          <h2 className="mt-4 text-lg font-semibold text-slate-900">
            No match cases yet
          </h2>
          <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">
            No cases were returned by the API. Available matching cases will
            appear here.
          </p>
        </div>
      )}

      {/* Case list and details */}
      {query.isSuccess && cases.length > 0 && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <section className="min-w-0 space-y-3">
            <div className="flex items-end justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">
                  Match cases
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  Select a case to inspect its score and details.
                </p>
              </div>
              <span className="text-xs text-slate-500">
                {cases.length} total
              </span>
            </div>

            <div className="space-y-3">
              {cases.map((item) => {
                const isSelected = selectedCase?.id === item.id;

                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setSelectedId(item.id)}
                    aria-pressed={isSelected}
                    className={`w-full rounded-xl border p-4 text-left transition ${
                      isSelected
                        ? "border-blue-500 bg-blue-50/70 ring-1 ring-blue-500"
                        : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <p className="break-words text-sm font-semibold text-slate-900">
                          {item.institution_a_name ||
                            "Institution A unavailable"}
                        </p>

                        <p className="mt-1 break-words text-sm text-slate-700">
                          {item.institution_b_name ||
                            "Institution B unavailable"}
                        </p>

                        <p className="mt-2 break-all text-xs text-slate-400">
                          Case ID: {item.id}
                        </p>

                        <p className="mt-2 text-xs text-slate-500">
                          Dice similarity
                        </p>
                      </div>

                      <span
                        className={`shrink-0 rounded-full border px-2.5 py-1 text-xs font-medium ${statusStyle(item.status)}`}
                      >
                        {item.status.replaceAll("_", " ")}
                      </span>
                    </div>

                    <div className="mt-4 flex items-center gap-3">
                      <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                        <div
                          className="h-full rounded-full bg-blue-600 transition-all"
                          style={{ width: `${scorePercent(item.dice)}%` }}
                        />
                      </div>

                      <span className="min-w-14 text-right text-sm font-semibold tabular-nums text-slate-800">
                        {formatScore(item.dice)}
                      </span>
                    </div>

                    {item.created_at && (
                      <p className="mt-3 text-xs text-slate-500">
                        Created {formatDate(item.created_at)}
                      </p>
                    )}
                  </button>
                );
              })}
            </div>
          </section>

          <section className="min-w-0 space-y-4">
            <div>
              <h2 className="text-lg font-semibold text-slate-900">
                Comparison details
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Case-level information returned by the matching service.
              </p>
            </div>

            {selectedCase && (
              <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
                {/* Selected case heading */}
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Selected case
                    </p>
                    <h3 className="mt-1 break-all text-lg font-semibold text-slate-900">
                      {selectedCase.id}
                    </h3>
                  </div>
                  <span
                    className={`rounded-full border px-3 py-1 text-xs font-semibold ${statusStyle(selectedCase.status)}`}
                  >
                    {selectedCase.status.replaceAll("_", " ")}
                  </span>
                </div>

                {/* Score */}
                <div className="rounded-xl bg-slate-50 p-5">
                  <p className="text-sm font-medium text-slate-600">
                    Returned Dice score
                  </p>
                  <p className="mt-2 text-4xl font-semibold tracking-tight text-slate-950 tabular-nums">
                    {formatScore(selectedCase.dice)}
                  </p>
                  <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-200">
                    <div
                      className="h-full rounded-full bg-blue-600 transition-all"
                      style={{
                        width: `${scorePercent(selectedCase.dice)}%`,
                      }}
                    />
                  </div>
                  <p className="mt-2 text-xs leading-5 text-slate-500">
                    Similarity is not the probability that two records belong to
                    the same person. Review the available evidence before making
                    a decision.
                  </p>
                </div>

                {/* References */}
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-xl border border-slate-200 p-4">
                    <p className="text-xs text-slate-500">Case reference</p>
                    <p className="mt-1 break-all text-sm font-semibold text-slate-900">
                      {selectedCase.id}
                    </p>
                  </div>
                  <div className="rounded-xl border border-slate-200 p-4">
                    <p className="text-xs text-slate-500">Review case</p>
                    <p className="mt-1 break-all text-sm font-semibold text-slate-900">
                      {selectedCase.review_case_id || "Not linked"}
                    </p>
                  </div>
                </div>

                {/* Record and institution IDs */}
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-xl border border-slate-200 p-4">
                    <p className="text-xs text-slate-500">Record A</p>
                    <MetadataValue value={selectedCase.record_a} />
                  </div>

                  <div className="rounded-xl border border-slate-200 p-4">
                    <p className="text-xs text-slate-500">Record B</p>
                    <MetadataValue value={selectedCase.record_b} />
                  </div>
                </div>

                {/* Programme metadata */}

                {/* Institution and programme metadata */}
                <div className="rounded-xl border border-slate-200 p-4">
                  <h4 className="text-sm font-semibold text-slate-900">
                    Institution and programme details
                  </h4>

                  <div className="mt-3 grid gap-4 sm:grid-cols-2">
                    <div>
                      <p className="text-xs text-slate-500">Institution A</p>
                      <p className="mt-1 break-words text-sm font-semibold text-slate-900">
                        {selectedCase.institution_a_name ||
                          (selectedCase.institution_a_id === "hidden"
                            ? "Hidden institution"
                            : "Institution name unavailable")}
                      </p>
                      <MetadataValue
                        value={
                          [
                            selectedCase.programme_a,
                            selectedCase.academic_year_a,
                          ]
                            .filter(Boolean)
                            .join(" · ") || "Programme details unavailable"
                        }
                      />
                    </div>

                    <div>
                      <p className="text-xs text-slate-500">Institution B</p>
                      <p className="mt-1 break-words text-sm font-semibold text-slate-900">
                        {selectedCase.institution_b_name ||
                          (selectedCase.institution_b_id === "hidden"
                            ? "Hidden institution"
                            : "Institution name unavailable")}
                      </p>
                      <MetadataValue
                        value={
                          [
                            selectedCase.programme_b,
                            selectedCase.academic_year_b,
                          ]
                            .filter(Boolean)
                            .join(" · ") || "Programme details unavailable"
                        }
                      />
                    </div>
                  </div>

                  <div className="mt-4 border-t border-slate-100 pt-3">
                    <p className="text-xs text-slate-500">Case created</p>
                    <MetadataValue
                      value={formatDate(selectedCase.created_at)}
                    />
                  </div>
                </div>

                {/* Restricted identity hints */}
                {canSeeIdentityHints &&
                  (selectedCase.identity_hint_a ||
                    selectedCase.identity_hint_b) && (
                    <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                      <h4 className="text-sm font-semibold text-amber-950">
                        Restricted identity hints
                      </h4>
                      <p className="mt-1 text-xs leading-5 text-amber-800">
                        Visible only to AICTE administrators and auditors.
                      </p>
                      <div className="mt-3 grid gap-3 sm:grid-cols-2">
                        <div>
                          <p className="text-xs text-amber-800">Hint A</p>
                          <MetadataValue value={selectedCase.identity_hint_a} />
                        </div>
                        <div>
                          <p className="text-xs text-amber-800">Hint B</p>
                          <MetadataValue value={selectedCase.identity_hint_b} />
                        </div>
                      </div>
                    </div>
                  )}

                {/* Compared fields */}
                <div className="rounded-xl border border-slate-200 p-4">
                  <h4 className="text-sm font-semibold text-slate-900">
                    Fields compared
                  </h4>

                  {selectedCase.fields_compared.length > 0 ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {selectedCase.fields_compared.map((field) => (
                        <span
                          key={field}
                          className="rounded-md bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700"
                        >
                          {field}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-2 text-sm text-slate-500">
                      No compared fields were returned.
                    </p>
                  )}
                </div>

                {/* Privacy notice */}
                <div className="flex items-start gap-3 rounded-xl border border-cyan-100 bg-cyan-50 p-4">
                  <span
                    className="mt-0.5 font-semibold text-cyan-800"
                    aria-hidden="true"
                  >
                    i
                  </span>
                  <p className="text-sm leading-6 text-cyan-950">
                    This screen displays only information returned by the API.
                    Identity visibility must be enforced by the backend. A
                    similarity score alone is not proof of a duplicate.
                  </p>
                </div>
              </div>
            )}
          </section>
        </div>
      )}

      <p className="text-xs leading-5 text-slate-500">
        API: <code>/blind-match/cases</code>. This page displays returned case
        data; it does not perform identity matching itself.
      </p>
    </div>
  );
}
