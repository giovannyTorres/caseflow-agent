import { describe, it, expect } from "vitest";
import {
  consultedPolicy,
  eventSummary,
  evidenceRetrieved,
  sharedMovementFields,
  filterCases,
  label,
  isWorking,
  nextAction,
  type CaseSummary,
} from "./domain";
const cases: CaseSummary[] = [
  {
    id: "CF-01",
    title: "Duplicate charge",
    scenario: "duplicate",
    status: "new",
    priority: "high",
    assignee: "analyst",
    amount: 520,
    currency: "MXN",
  },
  {
    id: "CF-02",
    title: "Receipt needed",
    scenario: "insufficient",
    status: "awaiting_evidence",
    priority: "normal",
    assignee: "analyst",
    amount: 90,
    currency: "MXN",
  },
];
describe("work queue controls", () => {
  it("combines search and status filters", () => {
    expect(filterCases(cases, "receipt", "awaiting_evidence")).toEqual([
      cases[1],
    ]);
    expect(filterCases(cases, "receipt", "new")).toEqual([]);
    expect(filterCases(cases, "cf-01", "all")).toEqual([cases[0]]);
  });
  it("shows a useful workflow label", () => {
    expect(label("awaiting_approval")).toBe("Awaiting Approval");
  });
  it("polls only active jobs", () => {
    expect(isWorking({ id: "j", status: "running" })).toBe(true);
    expect(isWorking({ id: "j", status: "failed" })).toBe(false);
  });
  it("derives the next action from the persisted status, not only the role", () => {
    expect(nextAction("resolved", "supervisor", 1)).toMatch(/No further action/);
    expect(nextAction("awaiting_approval", "supervisor", 2)).toContain("v2");
    expect(nextAction("awaiting_approval", "analyst", 2)).toMatch(/Waiting/);
    expect(nextAction("new", "analyst")).toMatch(/Run the investigation/);
  });
  it("reads the consulted policy from the recorded tool event", () => {
    const events = [
      { id: "1", event: "job_queued", actor: "analyst", created_at: "", detail: {} },
      {
        id: "2",
        event: "evidence_gathered",
        actor: "analyst",
        created_at: "",
        detail: { policy: "juniper-policy-v1", policy_version: 1, policy_text: "Never exceed the disputed amount." },
      },
    ];
    expect(evidenceRetrieved(events.slice(0, 1))).toBe(false);
    expect(evidenceRetrieved(events)).toBe(true);
    expect(consultedPolicy(events)).toEqual({
      id: "juniper-policy-v1",
      version: 1,
      text: "Never exceed the disputed amount.",
    });
    expect(consultedPolicy([])).toBeNull();
  });
  it("names the fields shared by retrieved movements", () => {
    const a = { id: "TX-1A", merchant: "Juniper", amount: 1280, currency: "MXN", posted_at: "t" };
    expect(sharedMovementFields([a, { ...a, id: "TX-1B" }])).toEqual([
      "merchant",
      "amount",
      "currency",
      "posted_at",
    ]);
    expect(sharedMovementFields([a, { ...a, amount: 1 }])).not.toContain("amount");
    expect(sharedMovementFields([a])).toEqual([]);
  });
  it("summarizes audit events as readable sentences", () => {
    const base = { id: "1", actor: "supervisor", created_at: "" };
    expect(
      eventSummary({ ...base, event: "proposal_prepared", detail: { version: 2, amount: 900 } }),
    ).toBe("Proposal v2 · MX$900.00");
    expect(
      eventSummary({
        ...base,
        event: "evidence_gathered",
        detail: { movement_count: 2, policy: "juniper-policy-v1", policy_version: 1 },
      }),
    ).toBe("2 movements retrieved · policy juniper-policy-v1 v1");
    expect(eventSummary({ ...base, event: "custom_event", detail: { note: "ok", n: 3 } })).toBe(
      "Note: ok · N: 3",
    );
  });
});
