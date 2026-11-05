import { describe, it, expect } from "vitest";
import { filterCases, label, isWorking, type CaseSummary } from "./domain";
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
});
