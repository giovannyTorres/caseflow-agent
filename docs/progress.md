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
