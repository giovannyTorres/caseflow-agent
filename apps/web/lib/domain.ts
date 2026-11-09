export type Role = "analyst" | "supervisor";
export interface User {
  username: string;
  role: Role;
  mode: string;
}
export interface Config {
  mode: string;
  live_ready: boolean;
  missing: string[];
  provider: string;
  model: string;
}
export interface CaseSummary {
  id: string;
  title: string;
  scenario: string;
  status: string;
  priority: string;
  assignee: string;
  amount: number;
  currency: string;
}
export interface Proposal {
  version: number;
  amount: number;
  reason: string;
  status: string;
}
export interface Event {
  id: string;
  event: string;
  actor: string;
  created_at: string;
  detail: unknown;
}
export interface Job {
  id: string;
  status: string;
  error?: string;
}
export interface CaseDetail extends CaseSummary {
  proposal?: Proposal | null;
  events: Event[];
  messages: { role: string; content: string }[];
  movements: Record<string, unknown>[];
  evidence: Record<string, unknown>[];
  job?: Job | null;
}
export function label(value: string | undefined) {
  return (value || "unknown")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
export function money(amount: number, currency = "MXN") {
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(
    amount,
  );
}
export function filterCases(
  cases: CaseSummary[],
  query: string,
  status: string,
) {
  return cases.filter(
    (c) =>
      (status === "all" || c.status === status) &&
      `${c.title} ${c.id} ${c.assignee} ${c.scenario}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
}
export function isWorking(job?: Job | null) {
  return ["queued", "running", "pending", "processing"].includes(
    job?.status || "",
  );
}
export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}
export async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(
      typeof data.detail === "string"
        ? data.detail
        : response.status === 401
          ? "Please sign in to continue."
          : `Request could not be completed (${response.status}).`,
      response.status,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}
export interface ConsultedPolicy {
  id: string;
  version?: number;
  text?: string;
}
/** Policy returned by the MCP get_policy tool, as recorded in the case trail. */
export function consultedPolicy(events: Event[]): ConsultedPolicy | null {
  const gathered = [...events]
    .reverse()
    .find((e) => e.event === "evidence_gathered");
  const detail = gathered?.detail as Record<string, unknown> | undefined;
  if (!detail || typeof detail.policy !== "string") return null;
  return {
    id: detail.policy,
    version:
      typeof detail.policy_version === "number"
        ? detail.policy_version
        : undefined,
    text:
      typeof detail.policy_text === "string" ? detail.policy_text : undefined,
  };
}
export function evidenceRetrieved(events: Event[]) {
  return events.some((e) => e.event === "evidence_gathered");
}
/** Next step for the signed-in role, derived from the persisted case status. */
export function nextAction(status: string, role: Role, version?: number) {
  const proposal = version ? `proposal v${version}` : "the proposal";
  const supervisor = role === "supervisor";
  switch (status) {
    case "new":
      return supervisor
        ? "Waiting for the analyst to run the investigation."
        : "Run the investigation to retrieve movements and policy through the MCP tools.";
    case "investigating":
      return "Investigation in progress. Tool results are saved as they complete.";
    case "awaiting_approval":
      return supervisor
        ? `Review the evidence, then approve or reject ${proposal}.`
        : `Waiting for a supervisor to review ${proposal}. Any edit requires a new approval.`;
    case "approved":
      return supervisor
        ? `Record the simulator resolution for approved ${proposal}.`
        : `Waiting for the supervisor to record the resolution of approved ${proposal}.`;
    case "needs_evidence":
      return supervisor
        ? "Review the evidence request. Reject the case if the purchase is confirmed."
        : "Waiting for the requested evidence. A supervisor reviews the case.";
    case "failed":
      return "A tool failed. Resume the investigation from its saved progress.";
    case "interrupted":
      return "Resume the investigation from its saved checkpoint.";
    case "resolved":
      return "No further action. The simulator resolution is recorded in the activity trail.";
    case "rejected":
      return "No further action. The rejection is recorded in the activity trail.";
    default:
      return "Review the case activity for the next authorized action.";
  }
}
const MATCH_FIELDS = ["merchant", "amount", "currency", "posted_at"] as const;
/** Fields whose values are identical across every retrieved movement (2+ movements). */
export function sharedMovementFields(movements: Record<string, unknown>[]) {
  if (movements.length < 2) return [];
  return MATCH_FIELDS.filter((field) =>
    movements.every(
      (m) => m[field] !== undefined && m[field] === movements[0][field],
    ),
  );
}
function amountText(value: unknown, currency = "MXN") {
  return typeof value === "number" ? money(value, currency) : String(value);
}
/** One readable sentence per audit event; falls back to key/value pairs. */
export function eventSummary(event: Event, currency = "MXN"): string {
  const d = (event.detail ?? {}) as Record<string, unknown>;
  switch (event.event) {
    case "job_queued":
      return `${label(String(d.action ?? "job"))} job queued`;
    case "evidence_gathered":
      return `${d.movement_count ?? 0} movements retrieved · policy ${d.policy ?? "unknown"}${d.policy_version ? ` v${d.policy_version}` : ""}`;
    case "decision_prepared":
      return `${String(d.mode ?? "")} decision: ${label(String(d.action ?? ""))}`.trim();
    case "proposal_prepared":
      return `Proposal v${d.version} · ${amountText(d.amount, currency)}`;
    case "proposal_approved":
      return `Approved proposal v${d.version}`;
    case "proposal_rejected":
      return `Rejected proposal v${d.version}`;
    case "resolution_registered":
      return `Simulator resolution for v${d.version} · ${amountText(d.amount, currency)}`;
    case "evidence_requested":
      return String(d.description ?? "Evidence requested");
    case "rejection_recommended":
      return String(d.message ?? "Rejection recommended");
    case "job_waiting":
      return "Paused at the approval checkpoint";
    case "job_completed":
      return "Workflow step completed";
  }
  if (typeof event.detail === "string") return event.detail;
  const pairs = Object.entries(d)
    .filter(([, v]) => ["string", "number", "boolean"].includes(typeof v))
    .map(([k, v]) => `${label(k)}: ${v}`);
  return pairs.join(" · ");
}
