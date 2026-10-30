// Owner: Dev D

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "../../lib/api-types";
import { api, apiWithMetadata } from "../../lib/api";
import { canPerform, useActionHint, useIdentity } from "../../lib/roles";
import ErrorAlert from "../../components/ErrorAlert";
import DashboardHeader, {
  ReadOnlyBanner,
  headerButton,
} from "../../components/DashboardHeader";
import {
  aicteHeader,
  aicteSections,
  type AicteSection,
} from "../../lib/dashboards";
import {
  actorLabel,
  evidenceSentences,
  institutionLabel,
  shortInstitutionName,
  type InstitutionLookup,
} from "../../components/format";
import { useInstitutions } from "../../components/useInstitutions";
import Reports from "./Reports";
import { AuditChainCard, DecisionLog } from "./AuditPanels";

type ReviewCase = components["schemas"]["ReviewCase"];
type IntegrityRanking = components["schemas"]["IntegrityRanking"];
type IntegrityDetail = components["schemas"]["IntegrityDetail"];
type ResolveRequest = components["schemas"]["ResolveRequest"];
type EditRequest = components["schemas"]["EditRequest"];
type EditDecision = components["schemas"]["EditDecision"];

const panel = "rounded-xl border border-slate-200 bg-white p-5 shadow-sm";
const button =
  "rounded-lg px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50";
const primaryButton = `${button} bg-slate-900 text-white hover:bg-slate-700`;
const secondaryButton = `${button} border border-slate-300 bg-white text-slate-700 hover:bg-slate-50`;
const field =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100";

function statusStyle(status: string) {
  if (status === "open") return "bg-amber-100 text-amber-800";
  if (status === "confirmed") return "bg-green-100 text-green-800";
  if (status === "dismissed") return "bg-slate-100 text-slate-700";
  return "bg-blue-100 text-blue-800";
}

function ErrorMessage({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800"
    >
      {message}
    </div>
  );
}

function displayValue(value: unknown): string {
  if (value == null) return "Not available";

  if (typeof value === "string") return value;

  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  try {
    return JSON.stringify(value, null, 2) ?? String(value);
  } catch {
    return String(value);
  }
}

function EvidenceList({
  code,
  evidence,
  lookup,
  institutionId,
}: {
  code: string;
  evidence: Record<string, unknown>;
  lookup: InstitutionLookup;
  institutionId?: string;
}) {
  return (
    <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
      {evidenceSentences(code, evidence, lookup, institutionId).map(
        (sentence, index) => (
          <li key={index} className="break-words">
            {sentence}
          </li>
        ),
      )}
    </ul>
  );
}

/** "Shadow ↔ Narmada" for a Blind Match case, else the institution's name. */
function CaseInstitutions({
  item,
  lookup,
}: {
  item: ReviewCase;
  lookup: InstitutionLookup;
}) {
  if (item.kind === "blind_match") {
    const a = item.evidence.institution_a_id ?? item.institution_id;
    const b =
      item.evidence.institution_b_id ?? item.evidence.other_institution_id;
    const dice = item.evidence.dice;
    return (
      <div>
        <p className="font-medium text-slate-900">
          {shortInstitutionName(a, lookup)} ↔ {shortInstitutionName(b, lookup)}
        </p>
        {typeof dice === "number" && (
          <span className="mt-1 inline-block rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-800">
            Dice {dice.toFixed(2)}
          </span>
        )}
      </div>
    );
  }
  const found = lookup(item.institution_id);
  return (
    <div>
      <p className="font-medium text-slate-900">
        {institutionLabel(item.institution_id, lookup, false)}
      </p>
      {found && (
        <p className="mt-1 text-xs text-slate-500">
          AICTE {found.aicte_code}
        </p>
      )}
    </div>
  );
}

export default function AictePage() {
  const { role } = useIdentity();
  const decideEditHint = useActionHint("decide_edit_request");
  const resolveCaseHint = useActionHint("resolve_review_case");
  // GET /edit-requests allows both; only aicte_admin may decide.
  const canReadEditRequests = role === "aicte_admin" || role === "auditor";
  const queryClient = useQueryClient();
  const { lookup } = useInstitutions();
  const sections = aicteSections(role);
  const header = aicteHeader(role);

  const [statusFilter, setStatusFilter] = useState("open");
  const [kindFilter, setKindFilter] = useState("all");
  const [selectedCase, setSelectedCase] = useState<ReviewCase | null>(null);
  const [decision, setDecision] =
    useState<ResolveRequest["status"]>("confirmed");
  const [reviewerNote, setReviewerNote] = useState("");
  const [selectedInstitution, setSelectedInstitution] = useState<string | null>(
    null,
  );
  const [editNotes, setEditNotes] = useState<Record<string, string>>({});
  const [editStatus, setEditStatus] = useState("pending");

  const editRequestsQuery = useQuery({
    queryKey: ["aicte-edit-requests", role, editStatus],
    queryFn: () =>
      api<EditRequest[]>(
        editStatus === "all"
          ? "/edit-requests"
          : `/edit-requests?status=${editStatus}`,
      ),
    enabled: canReadEditRequests,
    refetchInterval: 15000,
  });

  const editDecisionMutation = useMutation({
    mutationFn: ({
      id,
      decision,
      note,
    }: {
      id: string;
      decision: EditDecision["decision"];
      note: string;
    }) =>
      api<EditRequest>(`/edit-requests/${id}/decision`, {
        method: "POST",
        body: JSON.stringify({ decision, note }),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["aicte-edit-requests"],
      });
    },
  });

  const drawerCloseRef = useRef<HTMLButtonElement | null>(null);
  // The Inspect button that opened the drawer gets focus back when it closes.
  const inspectTriggerRef = useRef<HTMLElement | null>(null);

  function inspect(institutionId: string, trigger: HTMLElement) {
    inspectTriggerRef.current = trigger;
    setSelectedInstitution(institutionId);
  }

  function closeDrawer() {
    setSelectedInstitution(null);
    inspectTriggerRef.current?.focus();
  }

  useEffect(() => {
    if (!selectedInstitution) return;
    drawerCloseRef.current?.focus();
  }, [selectedInstitution]);

  useEffect(() => {
    if (!selectedInstitution && !selectedCase) return;

    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      // The review dialog sits above the drawer, so Esc closes it first.
      if (selectedCase) {
        setSelectedCase(null);
      } else {
        setSelectedInstitution(null);
        inspectTriggerRef.current?.focus();
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selectedInstitution, selectedCase]);

  const casesQuery = useQuery({
    queryKey: ["aicte-review-cases", role, statusFilter, kindFilter],
    queryFn: () => {
      const params = new URLSearchParams();
      if (statusFilter !== "all") params.set("status", statusFilter);
      if (kindFilter !== "all") params.set("kind", kindFilter);

      const suffix = params.size ? `?${params.toString()}` : "";
      return apiWithMetadata<ReviewCase[]>(`/review-cases${suffix}`);
    },
    refetchInterval: 15000,
    refetchIntervalInBackground: false,
  });

  const pendingEditsQuery = useQuery({
    queryKey: ["aicte-edit-requests", role, "pending-count"],
    queryFn: () => api<EditRequest[]>("/edit-requests?status=pending"),
    enabled: sections.includes("decisions_waiting"),
    refetchInterval: 15000,
  });

  const openCasesQuery = useQuery({
    queryKey: ["aicte-open-review-cases", role],
    queryFn: () => api<ReviewCase[]>("/review-cases?status=open"),
    refetchInterval: 15000,
    refetchIntervalInBackground: false,
  });

  const rankingsQuery = useQuery({
    queryKey: ["aicte-integrity-rankings", role],
    queryFn: () =>
      apiWithMetadata<IntegrityRanking[]>("/integrity/institutions"),
    refetchInterval: 30000,
    refetchIntervalInBackground: false,
  });

  const detailQuery = useQuery({
    queryKey: ["aicte-institution-integrity", selectedInstitution, role],
    queryFn: () =>
      api<IntegrityDetail>(`/integrity/institutions/${selectedInstitution}`),
    enabled: Boolean(selectedInstitution),
  });

  const resolveMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ResolveRequest }) =>
      api<ReviewCase>(`/review-cases/${id}/resolve`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: async () => {
      setSelectedCase(null);
      setReviewerNote("");

      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ["aicte-review-cases"],
        }),
        queryClient.invalidateQueries({
          queryKey: ["aicte-open-review-cases"],
        }),
      ]);
    },
  });

  const cases = casesQuery.data?.data ?? [];
  // SIMULATED only when this page's own responses carried X-Mock: true.
  const isMock = Boolean(
    casesQuery.data?.isMock || rankingsQuery.data?.isMock,
  );

  const rankings = [...(rankingsQuery.data?.data ?? [])].sort((a, b) => {
    const scoreA = a.integrity_score ?? Number.POSITIVE_INFINITY;
    const scoreB = b.integrity_score ?? Number.POSITIVE_INFINITY;
    return scoreA - scoreB;
  });

  const selectedRef = selectedInstitution
    ? lookup(selectedInstitution)
    : undefined;
  const selectedName =
    selectedRef?.name ??
    rankings.find((item) => item.institution_id === selectedInstitution)
      ?.institution_name ??
    "Institution";

  const openCount = openCasesQuery.data?.length ?? 0;

  // A FUZZY_MATCH_CANDIDATE signal only names its Blind Match case; the review case for that
  // match carries the two institutions and the Dice score.
  function withLinkedCase(evidence: Record<string, unknown>) {
    const caseId = evidence.blind_match_case_id;
    if (!caseId) return evidence;
    const linked = [...cases, ...(openCasesQuery.data ?? [])].find(
      (item) => item.evidence.blind_match_case_id === caseId,
    );
    return linked ? { ...linked.evidence, ...evidence } : evidence;
  }

  const highAnomalyCount = rankings.filter(
    (item) => item.anomaly_score >= 0.7,
  ).length;

  const scoredInstitutions = rankings.filter(
    (item) => item.integrity_score != null,
  );

  const averageScore = scoredInstitutions.length
    ? Math.round(
        scoredInstitutions.reduce(
          (sum, item) => sum + (item.integrity_score ?? 0),
          0,
        ) / scoredInstitutions.length,
      )
    : null;

  async function refreshDashboard() {
    await Promise.all([
      casesQuery.refetch(),
      openCasesQuery.refetch(),
      rankingsQuery.refetch(),
    ]);
  }

  function submitDecision(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!selectedCase || !reviewerNote.trim()) return;

    resolveMutation.mutate({
      id: selectedCase.id,
      payload: {
        status: decision,
        note: reviewerNote.trim(),
      },
    });
  }


  // Cards at the top of the admin view; each scrolls to its list with the matching filter.
  const waiting = [
    {
      label: "Open review cases",
      count: openCasesQuery.isLoading ? null : openCount,
      detail: "Exception queue",
      target: "exception-queue",
      select: () => setStatusFilter("open"),
    },
    {
      label: "Pending edit requests",
      count: pendingEditsQuery.isLoading
        ? null
        : (pendingEditsQuery.data?.length ?? 0),
      detail: "Institution edit requests",
      target: "edit-requests",
      select: () => setEditStatus("pending"),
    },
  ];

  // One renderer per section; aicteSections(role) decides which appear and in what order.
  const render: Record<AicteSection, ReactNode> = {
    read_only_banner: (
      <ReadOnlyBanner>
        You can view, verify and download. Decisions and edits are made by
        AICTE admins; every one is in the decision log below.
      </ReadOnlyBanner>
    ),
    decisions_waiting: (
      <section aria-labelledby="decisions-waiting-title">
        <h2
          id="decisions-waiting-title"
          className="text-sm font-semibold uppercase tracking-wide text-slate-500"
        >
          Decisions waiting
        </h2>
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          {waiting.map((card) => (
            <button
              key={card.target}
              type="button"
              onClick={() => {
                card.select();
                document
                  .getElementById(card.target)
                  ?.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
              className="group flex items-center justify-between gap-4 rounded-xl border border-blue-200 bg-white p-5 text-left shadow-sm transition hover:border-blue-400 hover:shadow"
            >
              <span>
                <span className="block text-sm text-slate-500">{card.label}</span>
                <span
                  className={`mt-1 block text-4xl font-semibold tracking-tight ${
                    card.count ? "text-blue-800" : "text-slate-400"
                  }`}
                >
                  {card.count ?? "—"}
                </span>
                <span className="mt-1 block text-xs text-slate-500">
                  {card.count === 0 ? "Nothing waiting" : `Go to ${card.detail}`}
                </span>
              </span>
              <span
                aria-hidden="true"
                className="text-2xl text-blue-400 transition group-hover:translate-x-1"
              >
                →
              </span>
            </button>
          ))}
        </div>
      </section>
    ),
    exception_queue: (
      <section id="exception-queue" className={`${panel} scroll-mt-20`}>
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <div>
            <h2 className="text-lg font-semibold text-slate-950">
              Exception queue
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              {canPerform(role, "resolve_review_case")
                ? "Review cases and record a decision with a mandatory note."
                : "Read-only. Open a case to read its evidence; decisions are made by AICTE admins."}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <select
              aria-label="Filter cases by status"
              className={`${field} sm:w-auto`}
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option value="open">Open</option>
              <option value="confirmed">Confirmed</option>
              <option value="dismissed">Dismissed</option>
              <option value="correction_requested">Correction requested</option>
              <option value="all">All statuses</option>
            </select>
            <select
              aria-label="Filter cases by type"
              className={`${field} sm:w-auto`}
              value={kindFilter}
              onChange={(event) => setKindFilter(event.target.value)}
            >
              <option value="all">All types</option>
              <option value="intake_overrun">Intake overrun</option>
              <option value="blind_match">Blind match</option>
              <option value="dispute">Dispute</option>
              <option value="signal">Integrity signal</option>
            </select>
          </div>
        </div>

        {casesQuery.isLoading ? (
          <p className="py-8 text-sm text-slate-500">Loading review cases…</p>
        ) : cases.length === 0 ? (
          <div className="mt-5 rounded-lg border border-dashed border-slate-300 p-8 text-center">
            <p className="font-medium text-slate-800">No review cases found</p>
            <p className="mt-1 text-sm text-slate-500">
              Try another status or case-type filter.
            </p>
          </div>
        ) : (
          <div className="mt-5 overflow-x-auto">
            <table className="w-full text-left text-sm sm:min-w-[720px]">
              <thead className="max-sm:hidden">
                <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                  <th className="pb-3 pr-4 font-medium">Case</th>
                  <th className="pb-3 pr-4 font-medium">Type</th>
                  <th className="pb-3 pr-4 font-medium">Institution</th>
                  <th className="pb-3 pr-4 font-medium">Status</th>
                  <th className="pb-3 font-medium">Action</th>
                </tr>
              </thead>
              <tbody>
                {cases.map((item) => (
                  <tr
                    key={item.id}
                    className="border-b border-slate-100 last:border-0 max-sm:flex max-sm:flex-wrap max-sm:items-center max-sm:gap-x-3 max-sm:py-3"
                  >
                    <td className="py-4 pr-4 max-sm:w-full max-sm:p-0">
                      <p className="font-medium text-slate-900">{item.title}</p>
                      <p className="mt-1 text-xs text-slate-500">
                        {item.id.slice(0, 8)}
                      </p>
                    </td>
                    <td className="py-4 pr-4 capitalize text-slate-700 max-sm:w-full max-sm:p-0 max-sm:pt-1 max-sm:text-xs">
                      {item.kind.replaceAll("_", " ")}
                    </td>
                    <td className="py-4 pr-4 max-sm:w-full max-sm:p-0 max-sm:py-2">
                      <div className="flex items-start gap-3">
                        <CaseInstitutions item={item} lookup={lookup} />
                        <button
                          type="button"
                          className="shrink-0 text-sm font-medium text-blue-700 underline"
                          aria-label={`Inspect ${institutionLabel(item.institution_id, lookup, false)}`}
                          aria-expanded={
                            selectedInstitution === item.institution_id
                          }
                          onClick={(event) =>
                            inspect(item.institution_id, event.currentTarget)
                          }
                        >
                          Inspect
                        </button>
                      </div>
                    </td>
                    <td className="py-4 pr-4 max-sm:p-0">
                      <span
                        className={`rounded-full px-2.5 py-1 text-xs font-medium ${statusStyle(item.status)}`}
                      >
                        {item.status.replaceAll("_", " ")}
                      </span>
                    </td>
                    <td className="py-4 max-sm:ml-auto max-sm:p-0">
                      {item.status === "open" ? (
                        <button
                          type="button"
                          className={secondaryButton}
                          onClick={() => {
                            setSelectedCase(item);
                            setReviewerNote("");
                            setDecision("confirmed");
                            resolveMutation.reset();
                          }}
                        >
                          {canPerform(role, "resolve_review_case")
                            ? "Review"
                            : "View"}
                        </button>
                      ) : (
                        <span className="text-xs text-slate-500">Resolved</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {casesQuery.isError && (
          <div className="mt-4">
            <ErrorMessage message="Unable to load the exception queue." />
          </div>
        )}
      </section>
    ),
    edit_requests: (
  <section id="edit-requests" className={`${panel} scroll-mt-20`}>
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <div>
            <h2 className="text-lg font-semibold text-slate-950">
              Institution edit requests
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Approve or reject post-lock changes. A reviewer note is
              required.
            </p>
            {decideEditHint && (
              <p className="mt-1 text-xs font-medium text-amber-800">
                {decideEditHint}: decisions are disabled.
              </p>
            )}
          </div>
          <select
            aria-label="Filter edit requests by status"
            className={`${field} sm:w-auto`}
            value={editStatus}
            onChange={(event) => setEditStatus(event.target.value)}
          >
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="all">All statuses</option>
          </select>
        </div>
        {editRequestsQuery.isLoading ? (
          <p className="py-5 text-sm text-slate-500">
            Loading edit requests…
          </p>
        ) : editRequestsQuery.isError ? (
          <div className="mt-4">
            <ErrorAlert
              action="Loading edit requests"
              error={editRequestsQuery.error}
            />
          </div>
        ) : (editRequestsQuery.data ?? []).length === 0 ? (
          <p className="py-5 text-sm text-slate-500">
            No {editStatus === "all" ? "" : `${editStatus} `}edit requests.
          </p>
        ) : (
          <div className="mt-4 space-y-3">
            {(editRequestsQuery.data ?? []).map((request) => (
              <article
                key={request.id}
                className="rounded-lg border border-slate-200 p-4"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <h3 className="font-semibold capitalize text-slate-900">
                      {request.field.replaceAll("_", " ")}
                      {request.admission?.student_name &&
                        ` · ${request.admission.student_name}`}
                    </h3>
                    <p className="mt-1 text-xs text-slate-500">
                      Request {request.id.slice(0, 8)}
                      {request.institution_id &&
                        ` · ${institutionLabel(request.institution_id, lookup)}`}
                      {request.admission?.apaar_id_masked &&
                        ` · APAAR ${request.admission.apaar_id_masked}`}
                    </p>
                  </div>
                  <span
                    className={`rounded-full px-2 py-1 text-xs capitalize ${
                      request.status === "pending"
                        ? "bg-amber-100 text-amber-800"
                        : request.status === "approved"
                          ? "bg-green-100 text-green-800"
                          : "bg-red-100 text-red-800"
                    }`}
                  >
                    {request.status}
                  </span>
                </div>
                <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-slate-500">Requested by</dt>
                    <dd>
                      {actorLabel(request.requested_by)}
                      <span className="text-slate-500">
                        {" "}
                        · {new Date(request.created_at).toLocaleString()}
                      </span>
                    </dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Decided by</dt>
                    <dd>
                      {request.decided_by
                        ? actorLabel(request.decided_by)
                        : "Awaiting decision"}
                      {request.decided_at && (
                        <span className="text-slate-500">
                          {" "}
                          · {new Date(request.decided_at).toLocaleString()}
                        </span>
                      )}
                    </dd>
                  </div>
                </dl>
                <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-slate-500">Old value</dt>
                    <dd className="break-words whitespace-pre-wrap">
                      {displayValue(request.old_value)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Requested value</dt>
                    <dd className="break-words whitespace-pre-wrap font-medium">
                      {displayValue(request.new_value)}
                    </dd>
                  </div>
                </dl>
                <p className="mt-2 text-sm">
                  <span className="text-slate-500">Reason: </span>
                  {request.reason || "No reason supplied"}
                </p>
                {request.status !== "pending" ? (
                  <p className="mt-2 text-sm">
                    <span className="text-slate-500">Decision note: </span>
                    {request.decision_note || "—"}
                  </p>
                ) : (
                  <>
                    <label className="mt-3 block text-sm font-medium text-slate-700">
                      Reviewer note (required)
                      <textarea
                        className={`${field} mt-1`}
                        rows={2}
                        disabled={Boolean(decideEditHint)}
                        value={editNotes[request.id] ?? ""}
                        onChange={(event) =>
                          setEditNotes((current) => ({
                            ...current,
                            [request.id]: event.target.value,
                          }))
                        }
                      />
                    </label>
                    {editDecisionMutation.isError &&
                      editDecisionMutation.variables?.id === request.id && (
                        <div className="mt-2">
                          <ErrorAlert
                            action="Saving the decision"
                            error={editDecisionMutation.error}
                          />
                        </div>
                      )}
                    <div className="mt-3 flex justify-end gap-2">
                      <button
                        type="button"
                        className={secondaryButton}
                        disabled={
                          Boolean(decideEditHint) ||
                          !editNotes[request.id]?.trim() ||
                          editDecisionMutation.isPending
                        }
                        title={decideEditHint}
                        onClick={() =>
                          editDecisionMutation.mutate({
                            id: request.id,
                            decision: "rejected",
                            note: editNotes[request.id].trim(),
                          })
                        }
                      >
                        Reject
                      </button>
                      <button
                        type="button"
                        className={primaryButton}
                        disabled={
                          Boolean(decideEditHint) ||
                          !editNotes[request.id]?.trim() ||
                          editDecisionMutation.isPending
                        }
                        title={decideEditHint}
                        onClick={() =>
                          editDecisionMutation.mutate({
                            id: request.id,
                            decision: "approved",
                            note: editNotes[request.id].trim(),
                          })
                        }
                      >
                        Approve
                      </button>
                    </div>
                  </>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
    ),
    rankings: (
      <section id="rankings" className={panel}>
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
          <div>
            <h2 className="text-lg font-semibold text-slate-950">
              Integrity Score rankings
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Lowest integrity scores appear first for review priority.
              {!rankingsQuery.isLoading &&
                ` ${rankings.length} ranked · ${highAnomalyCount} with anomaly ≥ 0.70 · average ${averageScore === null ? "—" : `${averageScore}/100`}.`}
            </p>
          </div>
          <Link
            to="/map"
            className="shrink-0 text-sm font-medium text-blue-700 underline"
          >
            View on state map →
          </Link>
        </div>

        {rankingsQuery.isLoading ? (
          <p className="py-8 text-sm text-slate-500">Loading rankings…</p>
        ) : rankings.length === 0 ? (
          <p className="py-8 text-sm text-slate-500">
            No institution rankings available.
          </p>
        ) : (
          <div className="mt-5 overflow-x-auto">
            <table className="w-full min-w-[650px] text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                  <th className="pb-3 pr-4 font-medium">Rank</th>
                  <th className="pb-3 pr-4 font-medium">Institution</th>
                  <th className="pb-3 pr-4 font-medium">Integrity score</th>
                  <th className="pb-3 pr-4 font-medium">Anomaly score</th>
                  <th className="pb-3 font-medium">Top signals</th>
                </tr>
              </thead>
              <tbody>
                {rankings.map((item, index) => (
                  <tr
                    key={item.institution_id}
                    className="border-b border-slate-100 last:border-0"
                  >
                    <td className="py-4 pr-4 font-semibold text-slate-700">
                      #{index + 1}
                    </td>
                    <td className="py-4 pr-4">
                      <button
                        type="button"
                        className="text-left font-medium text-blue-700 hover:underline"
                        onClick={(event) =>
                          inspect(item.institution_id, event.currentTarget)
                        }
                      >
                        {item.institution_name}
                      </button>
                      <p className="mt-1 text-xs text-slate-500">
                        AICTE code: {item.aicte_code}
                      </p>
                    </td>
                    <td className="py-4 pr-4">
                      <span className="font-semibold text-slate-900">
                        {item.integrity_score == null
                          ? "Not yet calculated"
                          : `${item.integrity_score}/100`}
                      </span>
                    </td>
                    <td className="py-4 pr-4">
                      <span
                        className={
                          item.anomaly_score >= 0.7
                            ? "font-semibold text-red-700"
                            : "text-slate-700"
                        }
                      >
                        {item.anomaly_score.toFixed(2)}
                      </span>
                    </td>
                    <td className="py-4 text-slate-600">
                      {item.top_signals.length
                        ? item.top_signals.join(", ")
                        : "No top signals returned"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {rankingsQuery.isError && (
          <div className="mt-4">
            <ErrorMessage message="Unable to load integrity rankings." />
          </div>
        )}
      </section>
    ),
    reports: <Reports rankings={rankings} />,
    audit_chain: <AuditChainCard auto={false} compact />,
    audit_status: <AuditChainCard auto />,
    decision_log: <DecisionLog lookup={lookup} />,
  };

  return (
    <main
      className="mx-auto max-w-7xl space-y-6 p-4 md:p-6"
      data-role-dashboard={role}
    >
      {sections[0] === "read_only_banner" && render.read_only_banner}
      <DashboardHeader
        header={header}
        eyebrow="AICTE portal"
        simulated={isMock}
        actions={
          <button
            type="button"
            className={headerButton}
            onClick={() => void refreshDashboard()}
            disabled={casesQuery.isFetching || rankingsQuery.isFetching}
          >
            {casesQuery.isFetching || rankingsQuery.isFetching
              ? "Refreshing…"
              : "Refresh dashboard"}
          </button>
        }
      />

      {(casesQuery.isError ||
        openCasesQuery.isError ||
        rankingsQuery.isError) && (
        <ErrorMessage message="Some dashboard data could not be loaded. Check your API connection and try refreshing." />
      )}

      {sections
        .filter((id) => id !== "read_only_banner")
        .map((id) => (
          <div key={id} data-section={id}>
            {render[id]}
          </div>
        ))}

      {selectedInstitution && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div
            aria-hidden="true"
            className="absolute inset-0 bg-slate-950/30"
            onClick={closeDrawer}
          />
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="institution-drawer-title"
            className="relative flex h-full w-full max-w-xl flex-col bg-white shadow-2xl"
          >
            <div className="flex items-start justify-between gap-3 border-b border-slate-200 p-5">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-wide text-blue-700">
                  Institution integrity details
                </p>
                <h2
                  id="institution-drawer-title"
                  className="mt-1 text-xl font-semibold text-slate-950"
                >
                  {selectedName}
                </h2>
                {selectedRef && (
                  <p className="mt-1 text-xs text-slate-500">
                    AICTE code {selectedRef.aicte_code}
                  </p>
                )}
              </div>
              <button
                ref={drawerCloseRef}
                type="button"
                className={secondaryButton}
                onClick={closeDrawer}
                aria-label="Close institution details"
              >
                Close
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-5">
              {detailQuery.isLoading ? (
                <p className="text-sm text-slate-500">
                  Loading institution signals…
                </p>
              ) : detailQuery.isError ? (
                <ErrorAlert
                  action="Loading integrity details"
                  error={detailQuery.error}
                />
              ) : detailQuery.data ? (
                <div className="space-y-5">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-lg bg-slate-50 p-4">
                      <p className="text-sm text-slate-500">Integrity score</p>
                      <p className="mt-1 text-3xl font-semibold text-slate-950">
                        {detailQuery.data.integrity_score == null
                          ? "—"
                          : `${detailQuery.data.integrity_score}/100`}
                      </p>
                    </div>
                    <div className="rounded-lg bg-slate-50 p-4">
                      <p className="text-sm text-slate-500">Anomaly score</p>
                      <p
                        className={`mt-1 text-3xl font-semibold ${
                          detailQuery.data.anomaly.score >= 0.7
                            ? "text-red-700"
                            : "text-slate-950"
                        }`}
                      >
                        {detailQuery.data.anomaly.score.toFixed(2)}
                      </p>
                    </div>
                  </div>

                  <div>
                    <h3 className="font-medium text-slate-900">
                      Score components
                    </h3>
                    <div className="mt-3 grid gap-3 sm:grid-cols-2">
                      {Object.entries(detailQuery.data.components).map(
                        ([name, value]) => (
                          <div
                            key={name}
                            className="rounded-lg border border-slate-200 p-3"
                          >
                            <p className="text-sm capitalize text-slate-500">
                              {name.replaceAll("_", " ")}
                            </p>
                            <p className="mt-1 text-lg font-semibold text-slate-900">
                              {value}
                            </p>
                          </div>
                        ),
                      )}
                    </div>
                  </div>

                  <div>
                    <h3 className="font-medium text-slate-900">
                      Integrity signals
                    </h3>
                    {detailQuery.data.signals.length === 0 ? (
                      <p className="mt-2 text-sm text-slate-500">
                        No signals returned.
                      </p>
                    ) : (
                      <ul className="mt-3 space-y-2">
                        {detailQuery.data.signals.map((signal, index) => (
                          <li
                            key={`${signal.code}-${index}`}
                            className="rounded-lg border border-slate-200 p-3"
                          >
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <span className="font-mono text-xs font-medium text-slate-900">
                                {signal.code}
                              </span>
                              <span
                                className={`rounded-full px-2 py-1 text-xs ${statusStyle(signal.severity)}`}
                              >
                                {signal.severity}
                              </span>
                            </div>
                            <EvidenceList
                              code={signal.code}
                              evidence={withLinkedCase(signal.evidence)}
                              lookup={lookup}
                              institutionId={selectedInstitution}
                            />
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              ) : null}
            </div>
          </section>
        </div>
      )}

      {selectedCase && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/50 p-0 sm:items-center sm:p-4">
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="review-dialog-title"
            className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-t-2xl bg-white p-5 shadow-xl sm:rounded-2xl"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-blue-700">
                  Review case
                </p>
                <h2
                  id="review-dialog-title"
                  className="mt-1 text-xl font-semibold text-slate-950"
                >
                  {selectedCase.title}
                </h2>
              </div>
              <button
                type="button"
                className={secondaryButton}
                onClick={() => {
                  setSelectedCase(null);
                  resolveMutation.reset();
                }}
              >
                Close
              </button>
            </div>

            <div className="mt-4 rounded-lg bg-slate-50 p-3 text-sm">
              <p>
                <span className="text-slate-500">Type:</span>{" "}
                {selectedCase.kind.replaceAll("_", " ")}
              </p>
              <p className="mt-1 break-all">
                <span className="text-slate-500">Case ID:</span>{" "}
                {selectedCase.id}
              </p>
              <p className="mt-1">
                <span className="text-slate-500">Institution:</span>{" "}
                {institutionLabel(selectedCase.institution_id, lookup)}
              </p>
            </div>

            <div className="mt-4">
              <h3 className="font-medium text-slate-900">Case evidence</h3>
              <div className="mt-2 max-h-48 overflow-auto rounded-lg border border-slate-200 p-3">
                <EvidenceList
                  code={selectedCase.kind}
                  evidence={selectedCase.evidence}
                  lookup={lookup}
                  institutionId={selectedCase.institution_id}
                />
              </div>
            </div>

            <form onSubmit={submitDecision} className="mt-5 space-y-4">
              {resolveCaseHint && (
                <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
                  {resolveCaseHint}. You can read the evidence but not record a
                  decision.
                </p>
              )}
              <fieldset
                disabled={Boolean(resolveCaseHint)}
                className="space-y-4 disabled:opacity-60"
              >
              <div>
                <label
                  htmlFor="decision"
                  className="mb-1 block text-sm font-medium text-slate-700"
                >
                  Decision
                </label>
                <select
                  id="decision"
                  className={field}
                  value={decision}
                  onChange={(event) =>
                    setDecision(event.target.value as ResolveRequest["status"])
                  }
                >
                  <option value="confirmed">Confirm finding</option>
                  <option value="dismissed">Dismiss finding</option>
                  <option value="correction_requested">
                    Request correction
                  </option>
                </select>
              </div>

              <div>
                <label
                  htmlFor="reviewer-note"
                  className="mb-1 block text-sm font-medium text-slate-700"
                >
                  Reviewer note <span className="text-red-600">*</span>
                </label>
                <textarea
                  id="reviewer-note"
                  className={field}
                  rows={4}
                  required
                  minLength={1}
                  value={reviewerNote}
                  onChange={(event) => setReviewerNote(event.target.value)}
                  placeholder="Explain the evidence and rationale for this decision."
                />
                <p className="mt-1 text-xs text-slate-500">
                  A non-empty note is required for every decision.
                </p>
              </div>
              </fieldset>

              {resolveMutation.isError && (
                <ErrorAlert
                  action="Saving the decision"
                  error={resolveMutation.error}
                />
              )}

              {resolveMutation.isSuccess && (
                <p role="status" className="text-sm text-green-700">
                  Decision saved.
                </p>
              )}

              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  className={secondaryButton}
                  onClick={() => {
                    setSelectedCase(null);
                    resolveMutation.reset();
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className={primaryButton}
                  disabled={
                    Boolean(resolveCaseHint) ||
                    resolveMutation.isPending ||
                    !reviewerNote.trim()
                  }
                  title={resolveCaseHint}
                >
                  {resolveMutation.isPending ? "Saving…" : "Save decision"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </main>
  );
}
