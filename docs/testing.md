# Testing Caseflow

Start with the [README's five simple backend checks](../README.md#run-simple-tests), then the [complete validation commands](../README.md#full-validation). Both use locked dependencies and require no model credentials. The health endpoint is a read-only installation check; the backend workflow test additionally runs the real MCP client/server and persists the approval/resolution flow.

The current audit verified **71 backend tests passed / 1 opt-in LIVE test skipped**, **3 frontend unit tests**, **7 browser tests**, lint/types/builds and a final uncached Docker rebuild. See [audit.md](audit.md#final-candidate-verification) for evidence and limitations. Contract fixtures are not authenticated provider verification.

Backend tests use a disposable PostgreSQL database ending in `_test`, default `caseflow_test` at port 5542. Never point `TEST_DATABASE_URL` at your demonstration or other retained data. Browser tests use the running web origin and intentionally mutate the five initial synthetic cases; for a separate installation use the audit Compose override/project. `WEB_BASE_URL` overrides the web origin, and `CHROMIUM_PATH` selects an installed browser. Otherwise install Chromium with `npx playwright install --with-deps chromium` from `apps/web`.

<details>
<summary>Historical implementation record — superseded by the completed technical audit</summary>

# Initial implementation verification (superseded by the audit)

Current release-candidate evidence and corrected behavior are in [audit.md](audit.md). The following record is retained as historical context, not a current approval.

# Verification record — 2026-11-05

All data and decisions used in local tests are synthetic fixtures. A passing test count is software verification, not model quality or financial impact.

| Area | Evidence |
|---|---|
| Backend | `uv run pytest -q`: 22 passed, 1 skipped (explicit LIVE smoke) |
| Security | Direct HTTP session/role/CSRF/mode checks; no approval, stale approval, active-job approval bypass, and amount bounds blocked |
| Concurrency | 16 concurrent simulator resolution attempts produce one row and one resolution event |
| MCP | Official client initializes a separate stdio server and invokes typed tools; scope and role violations are rejected |
| Durability | Fresh LangGraph instances reload PostgreSQL checkpoints; expired worker leases, tool recovery, explicit interruption and pre-start cancellation recovery tested |
| Providers | OpenAI and Gemini official SDK HTTP transport fixtures; schema rejection and bounded OpenAI retry/no-fallback checked |
| Web | ESLint, TypeScript, 3 unit tests and Next production build passed |
| Browser | 4 Playwright tests passed: fresh investigation → approval → resolution, mobile/error/focus/filter states, no-proposal supervisor rejection, and insufficient/tool-failure/interruption scenarios |
| Dependencies | Online npm audit reported 0 known vulnerabilities after patching development dependencies; this is not a security certification |
| Infrastructure | Compose configurations parse; Bicep compiles locally to ARM JSON. No Azure deployment or cloud validation was performed |

Tests use a separate PostgreSQL database, default `caseflow_test`, and refuse to truncate any database whose name does not end in `_test`. Create it once with `docker compose exec -T db createdb -U caseflow caseflow_test`. Override only with an isolated `TEST_DATABASE_URL` for CI. Tests do not use the persistent demonstration database.

`npm run test:e2e` runs against the existing same-origin DEMO stack. The audited browser suite requires fresh fixture state and fails if a named transition is skipped. It no longer counts pre-resolved cases as execution of a new investigation. For independent full CI evidence, the workflow provisions a fresh Compose volume. System Chromium is used if available; otherwise `npx playwright install --with-deps chromium` supplies the Playwright browser. `CHROMIUM_PATH` and `WEB_BASE_URL` may override those locations. Use `localhost:3102` to match the configured trusted origin.

Actual screenshots are in `docs/screenshots`: inbox, investigation awaiting review, resolved audit trail and mobile layout. Desktop and mobile were visually inspected; keyboard focus and no horizontal mobile overflow were checked. This does not establish full WCAG conformance.

A transitive Starlette/AnyIO deprecation warning is recorded in pytest output; it does not fail the pinned test stack. Provider smoke is deliberately skipped unless `RUN_LIVE=1`; external model availability, output quality, latency, tokens and cost remain unmeasured. No synthetic model score is reported. Azure Container Apps deployment, managed identity, network reachability and cloud runtime remain unverified.

## Final runtime verification and external block

`./scripts/demo-local.sh` was executed successfully twice using locked dependencies: PostgreSQL in Docker, FastAPI and worker processes, and a production Next build on the host. An additional synthetic case was paused at a persisted LangGraph interruption; the entire launcher (API, worker and web) was stopped and started again. The case remained interrupted, resumed, received supervisor approval and produced exactly one simulator resolution. [The retained audit evidence](restart-verification.json) records the actual events. The temporary verification case was removed, and only the five original synthetic DEMO fixtures were explicitly reset with their checkpoints so the two-minute walkthrough can be repeated. Startup does not reset data.

The first image build completed, but its runtime check found copied source permissions incompatible with the non-root backend user. The Dockerfile now explicitly grants read/traverse permission. A final rebuild of the corrected sources was attempted and blocked before image construction by the environment's external registry/proxy response:

```text
https://auth.docker.io/token?scope=repository%3Adocker%2Fdockerfile%3Apull&service=registry.docker.io
503 Service Unavailable
```

Therefore **the final all-container images and Compose application boot remain unverified**. The successful final local launcher and host browser tests do not establish that container boot passed. The final Compose files parse correctly, PostgreSQL runs with its healthcheck, and the local application remains available at port 3102. Re-run `docker compose up --build -d --wait` once registry connectivity is restored, or use `docker compose -f compose.yaml -f compose.cloud.yaml up --build -d --wait` in the managed proxy workspace. No network controls were bypassed.

</details>
