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
export async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : response.status === 401
          ? "Please sign in to continue."
          : `Request could not be completed (${response.status}).`,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}
