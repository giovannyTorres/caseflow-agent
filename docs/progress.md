# Build record

- 2026-11-05: inspected empty project workspace and applicable environment instructions; created independent repository.
- Consulted official Next, MCP, LangGraph, OpenAI and Gemini documentation; pinned dependencies and generated lockfiles.
- Implemented PostgreSQL domain, salted-password sessions, role authorization, mode separation and idempotent migrations/seed.
- Implemented separate MCP stdio subprocess tools and real SDK client; bounded LangGraph workflow and PostgreSQL interrupts/checkpoints.
- Implemented durable leased worker, recovery and cancellation, current-version supervisor approvals and transactional unique resolutions.
- Implemented official OpenAI/Gemini structured-output adapters with fixture transports and opt-in LIVE smoke.
- Implemented responsive Next desk and UI review, reproducible containers, CI and Azure configuration.
- Verification results are recorded in testing.md; external provider calls and Azure deployment remain unverified.

- Final verification: 22 pytest tests passed with 1 explicit LIVE skip; frontend lint/types/3 unit tests/build and 4 browser tests passed. npm audit reported 0 known findings.
- Fixed a no-proposal rejection UI gap, pre-start cancellation recovery and container source permissions.
- Verified the single-command local launcher twice and an actual API/worker process restart across a persisted interruption; retained its audit trace. Reset only the five owned synthetic fixtures for the next reviewer.
- Final corrected Docker rebuild blocked by external registry HTTP 503; final full Compose boot is explicitly pending, while the local app remains functional. No external model service or Azure deployment was verified.


## Technical audit update — 2026-11-05

The previous build record above is historical. The audit began from clean commit7207707 and preserved existing data/history. It corrected lease/cancellation/checkpoint integrity, resolution enqueue semantics, terminal provider validation and resource cleanup, bounded request handling, LIVE/configuration UI state and keyboard focus. It reproduced a clean `--pull --no-cache` build and four healthy services on a new audit Compose project; a real API/worker restart retained the interruption checkpoint and led to exactly one resolution. The final snapshot, including query-log redaction and UI corrections, also completed an uncached rebuild; 71 backend tests passed with 1 LIVE skip, 3 frontend unit tests and all 7 browser tests passed. A second actual container restart again preserved the session/checkpoint and produced exactly one resolution. [audit.md](audit.md) contains exact commands, findings, source references and current evidence; no LIVE service verification or external publication is claimed.
