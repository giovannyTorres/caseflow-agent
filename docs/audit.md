# Technical audit — release candidate, 2026-11-05

## Baseline and scope

Initial branch `main`, commit `399befb`; working tree was clean. No applicable AGENTS.md existed in this repository at inspection. Existing volumes, case history, commits and the original local demo were preserved. The independent audit uses Compose project **audit-caseflow**, named volume `audit-caseflow_caseflow-db`, web `3202`, API `8202`, PostgreSQL `5642`. Destructive tests are restricted to the separately created `audit_caseflow_test` database; the fixture rejects database names not ending `_test`.

The audit inspected HTTP endpoints and domain transactions, MCP stdio client/server, LangGraph persistence and leases, official SDK request/response contracts, browser state/authorization handling, Dockerfiles, local launch scripts and documentation. No provider key, paid model invocation, remote Git publication or Azure deployment was used.

## Findings and corrections

| ID / impact | Concrete original behavior and reproduction | Correction and regression evidence |
|---|---|---|
| CF-01 **High: execution integrity** | `worker.py` updated leases and completion using only job ID. A reclaimed attempt could keep writing through MCP; cancellation was checked only by a later heartbeat. Claim a job, expire its lease, reclaim it, then invoke `prepare_proposal` as the old attempt. | `execution.py`, worker and MCP carry a job/attempt capability outside model arguments. Mutations lock the case and validate the running job, unexpired lease and attempt in the **same transaction**. A separate session advisory lock serializes graph/checkpoint writers without holding row locks across the child process. `test_superseded_actual_mcp_cannot_prepare_proposal`, `test_cancelled_mcp_cannot_resolve_after_backend_cancel` use the actual MCP subprocess, not a fake tool. |
| CF-02 **High: recovery** | Worker failure/cancellation always marked nonterminal cases failed, including an approved proposal. A later resolution retry was blocked by the resolution guard; a late cancelled worker could overwrite a newly resumed job. | Preserve exact approval as `approved`, existing unapproved proposal as `awaiting_approval`, otherwise `failed`. Superseded attempts and old cancelled jobs cannot overwrite a replacement. Tests cover failed resolution→retry→one resolution and cancelled old worker→new investigation state. |
| CF-03 **High: false accepted action** | `/resolve` could return an already-running investigation job when a supervisor approved the proposal before its checkpoint finished. The HTTP response implied resolution was queued while only investigation was running. `/proposal` also allowed creation before any investigation. | Return 409 until the investigation checkpoint is available; only duplicate requests for the same queued resolution are idempotent. API proposal editing requires an existing reviewable proposal under the domain transaction lock. Direct HTTP regressions cover both, independent of buttons. |
| CF-04 **High: LIVE output integrity** | `providers.py` accepted schema-valid JSON even when OpenAI reported `length`/filtering or Gemini reported `MAX_TOKENS`/safety. This could make incomplete output actionable. | Require the documented terminal success status; reject refusals, blocked prompts/candidates, unexpected tool/nontext parts and invalid schemas. Fixtures deliberately contain **valid-looking JSON with unsuccessful terminal statuses**. Missing/unspecified benign feedback is permitted. Both actual official SDK HTTP serializers are exercised. |
| CF-05 **Medium: resource and error handling** | Semaphore acquisition was outside the timeout, Gemini's synchronous client remained open, and raw SDK exceptions could propagate. | Deadline includes queue wait; bounded retries and sanitized provider errors; sync/async clients close on success, exception and cancellation. Contract tests cover 401/429/503 retry counts, cancellation, queue timeout and closure. MCP error is raised after session teardown, avoiding a wrapper ExceptionGroup for a normal tool refusal. |
| CF-06 **Medium: request abuse / credential echo** | JSON request bodies were unbounded; default validation responses echoed rejected password input; no login-attempt limit existed. | Streamed 64 KiB request cap, validation errors contain only field/type/message, persisted 20 attempts/minute per direct peer. Additive migration `migration_002.sql` preserves prior tables/history. Regressions exercise a chunked oversized body, a too-long password and limit expiry. This is a small deployment-local control, not a complete distributed identity/rate system. |
| CF-07 **Medium: mode and LIVE UX** | LIVE sign-in only offered the DEMO usernames and prefilled a DEMO password. A failed configuration request silently displayed DEMO mode. | LIVE uses an arbitrary operator-provisioned username with blank password; unavailable configuration has an explicit retry state; expired sessions return to sign-in. Two browser tests intentionally mock only configuration responses and are labelled UI-contract tests, not provider or backend verification. |
| CF-08 **Medium: evidence quality** | Previous browser assertions sometimes returned early on already-completed cases, so reruns could pass without performing the named transition. | Four real workflow tests require fresh known fixture state and execute the actual transitions. Use the isolated audit volume or an explicit DEMO-only reset; never silently reset data at startup. |
| CF-10 **High: log privacy** | Although application logs were bounded JSON, Uvicorn access logs and OpenTelemetry URL attributes could expose an arbitrary query canary sent even to `/api/health`. | Disable the raw Uvicorn access logger at shared startup; retain method/status/correlation JSON. A server-request trace hook removes query values from URL attributes. `test_actual_uvicorn_and_trace_export_do_not_log_query_canary` launches an actual process with console tracing, sends a synthetic canary, inspects both logs/exported spans, and asserts the canary is absent. |
| CF-11 **Medium: keyboard usability** | A confirmation dialog captured the focused Cancel element after autofocus; Escape then tried to restore focus to the removed dialog, rather than the triggering approval button. The focused-button assertion failed before correction. | Capture the invoking button before opening the dialog and restore it after dialog removal. The focused-view regression passes after correction; it is explicitly a mocked UI contract, not a new financial workflow. |
| CF-09 **Low: readability** | Muted text `#858592` had contrast 3.64 on white and 3.36 on the pale surface. | Muted text `#666675` measures 5.64 / 5.21; darkened secondary violet labels. Keyboard/mobile/browser visual review remains narrower than a full accessibility certification. |

Additional validation: strictly typed integer amounts/versions reject boolean or string coercion; decision action and amount must agree. Missing/obviously mismatched provider/model configuration is reported before execution. A complete graph invocation has a configurable 180-second default deadline (10–900 supported), in addition to model/MCP timeouts and the graph's 12-step recursion limit.

## Reproduction commands

From this repository, with Docker Compose 2.24.4+ (the audit used 2.40.3), Python 3.12, uv 0.13.4 and Node 24.22.1:

```sh
# A new isolated project/volume: existing default data is not removed.
docker compose -p audit-caseflow -f compose.yaml -f compose.audit.yaml up -d --wait db
docker compose -p audit-caseflow -f compose.yaml -f compose.audit.yaml exec -T db createdb -U caseflow audit_caseflow_test
uv sync --frozen
TEST_DATABASE_URL=postgresql://caseflow:caseflow-demo@localhost:5642/audit_caseflow_test uv run pytest -q
uv run ruff check services tests scripts
uv run python -m compileall -q services scripts
cd apps/web
npm ci
npm run lint
npm run typecheck
npm test
npm run build
cd ../..
# The managed environment requires its trusted CA; normal hosts omit compose.cloud.yaml.
docker compose -p audit-caseflow -f compose.yaml -f compose.audit.yaml -f compose.cloud.yaml build --pull --no-cache
docker compose -p audit-caseflow -f compose.yaml -f compose.audit.yaml -f compose.cloud.yaml up -d --no-build --wait
cd apps/web
WEB_BASE_URL=http://localhost:3202 npm run test:e2e
cd ../..
uv run python scripts/audit_restart.py
```

`createdb` is a one-time step; an existing-database error does not mean it should be dropped. The browser suite intentionally requires fresh fixture states. `scripts/reset_demo.py --confirm-synthetic-data` is an explicit, bounded reset of only the five shipped DEMO cases/checkpoints when no active jobs exist; do not use it to hide test failures.

The `--no-build` launch above is **after a successful `--pull --no-cache` build**, not offered as rebuild evidence. No TLS verification was disabled. Official base images and exact package lockfiles are retained.

## Model and MCP contracts

- OpenAI SDK `2.15.0`: Chat Completions with JSON-schema response format, validated `Decision`; only `finish_reason=stop`, one nonrefused textual candidate accepted. Native tool calls are not requested; unexpected calls are rejected.
- Google GenAI SDK `1.60.0`: `aio.models.generate_content`, JSON response schema, prompt/candidate blocking and terminal `STOP` checked before validation. Sync/async client resources close.
- This product uses **structured model decisions**, then backend-controlled graph nodes call real MCP tools. It does not claim native model API function-calling support or token streaming.
- The MCP server is a separate child executable over **stdio**. Actor, case and optional job-attempt capability are supplied by the trusted parent environment, never by model arguments. Domain roles and exact approvals are rechecked in tool transactions. A process already permitted to execute arbitrary code or change DB credentials is inside the trust boundary; stdio is not a network endpoint or public OAuth server.
- DEMO decisions come only from named original fixtures. LIVE decisions always invoke the selected adapter; missing configuration or provider failure never chooses a fixture. Synthetic case inputs/policies remain explicitly synthetic even during LIVE inference.

Official sources retrieved during this audit: [MCP transports](https://modelcontextprotocol.io/specification/latest/basic/transports), [MCP authorization](https://modelcontextprotocol.io/specification/latest/basic/authorization), [LangGraph durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution), [OpenAI Python SDK](https://github.com/openai/openai-python), [official ChatCompletion type](https://github.com/openai/openai-python/blob/main/src/openai/types/chat/chat_completion.py), [Gemini generateContent reference](https://ai.google.dev/api/generate-content), [Google GenAI SDK lifecycle](https://googleapis.github.io/python-genai/). These sources returned 200. The OpenAI API object documentation URL returned 403; the corresponding official SDK generated type and README were used and that gap is not concealed.

## Installation and trust boundaries

The checked-in local launcher installs frozen Python dependencies, compares the installed npm lock state and runs `npm ci` when required, then builds Next before starting API/worker/web. It requires the documented tools and PostgreSQL image; caches can speed installation but are not a substitute for dependency declarations. Its paths resolve from this repository; it imports no files from either other portfolio project. Font files/licenses are tracked locally. On a clean host, package/image network access is required for installation; no model credentials or GPU are required for DEMO.

Sessions are random HttpOnly/SameSite=Strict cookies, persisted as hashes, scoped to mode with eight-hour expiry. Browser mutations enforce the configured origin and JSON content type. LIVE users are explicitly provisioned; public DEMO passwords do not log in to LIVE. Production identity federation, distributed abuse control, real merchant integrations, managed backups, external deployment and load capacity have not been verified or claimed.

## Executed evidence and remaining limits

The former registry 503 was rechecked: official package/image access recovered. This audit performed an uncached image rebuild; the final execution results and new screenshot links are recorded below. Old `docs/testing.md` numbers describe the initial implementation, not this audit.

All test counts describe software behavior against synthetic data, not model quality or prompt-injection immunity. Provider contracts were exercised through official SDKs with simulated HTTP transports; no service authentication, current model availability, actual model quality, quotas or billing was verified. LIVE smoke tests remain explicit opt-in and were skipped.

Independent direct HTTP checks against the fresh containers (not the previous host server): unauthenticated case read401, hostile-Origin login403, valid analyst login200, analyst approval403, analyst resolution403, forged `actor: supervisor` field422, cross-mode `live-001` read404, same-origin web proxy health200. These checks did not rely on disabled buttons.

The actual-process logging regression passed with console OpenTelemetry enabled. Session expiry, HttpOnly/SameSite/Max-Age flags, DEMO cookie/password rejection after switching to LIVE and boolean approval-version rejection were independently exercised. Initial query-canary values were synthetic and no full runtime logs are committed.

The same per-case advisory lock also protects explicit DEMO reset from a cancelled worker still exiting its checkpoint task. The actual reset CLI refuses while that lock is held and leaves proposal state intact (`test_reset_refuses_a_worker_still_writing_after_cancellation`). Concurrent direct HTTP resolution was additionally exercised with 16 requests: all returned the same queued job, and running that job through the real graph/MCP produced exactly one resolution and one resolution event.


### Final candidate verification

| Check | Result and evidence |
|---|---|
| Backend, actual PostgreSQL and MCP subprocesses | `TEST_DATABASE_URL=postgresql://caseflow:caseflow-demo@localhost:5642/audit_caseflow_test uv run pytest -q`: **71 passed, 1 LIVE skipped**, 50.49 seconds. The only warning is Starlette's deprecated AnyIO alias. No model quality metric is implied. |
| Python and frontend checks | Ruff, compileall, ESLint, TypeScript and **3 Vitest tests** pass. The final Docker web stage ran a fresh `npm ci` and Next production build. |
| Final browser suite | **7 passed**, 54.6 seconds: four actual backend/MCP workflows covering all five scenarios, plus three clearly labelled UI contracts (LIVE sign-in, configuration outage/recovery, confirmation focus). Desktop 1440px and mobile 390px were inspected; keyboard focus, empty search, invalid credentials and recoverable tool failure were exercised. |
| Docker rebuild | Both the initial clean installation and the **final runtime snapshot** completed `build --pull --no-cache` using official base images and the managed environment's trusted CA. API, worker, web and PostgreSQL subsequently reported healthy. No registry failure remains blocking this repository. |
| Persistence | Initial installation used a new `audit-caseflow_caseflow-db` volume. The final rebuild reused that audit volume and retained the previous restart case/session history, independently read back through HTTP. The original default volume was untouched. |
| Container privacy | A synthetic query canary sent to final API `/api/health` returned 200 and was absent from actual container logs; structured correlation logs remained. Console trace sanitation also passed the actual-Uvicorn regression. |
| Infrastructure | Local Bicep compilation succeeded. Public HTTPS documentation returned 200 from inside the final API container with certificate verification enabled. Neither result verifies an Azure deployment or a model service. |

One final browser run correctly failed on an ambiguous title locator because the preserved restart case shared the title “Interrupted investigation” with `demo-005`. The locator now also matches the intended fixture ID; no assertions were removed. The audit fixtures were explicitly reset using the guarded CLI, and the full seven-test browser suite above then passed. The extra restart cases were retained. This was a test selection correction, not a runtime-image change.

Final locally rebuilt image IDs (evidence of this run, not registry-published artifacts):

```text
api    sha256:e8aca297d8d4971d21f625b43ae2b0dc55cac7fab74de368c0867b2f53d88704
worker sha256:64d96185e2c0780e566c181fc9296ff761654021af4319d4edc50e931220e376
web    sha256:4cdac367931e536d1b407592bab78be6371af7fbe84775f912084161535987bf
```

Independent final-image read-only review confirmed same-origin configuration and OpenAPI responses (14 documented paths), DEMO sign-in, persisted resolved case, HttpOnly/SameSite=Strict cookie flags and live PostgreSQL reads. Cookie Secure is intentionally false for the documented local HTTP origin; the LIVE guide requires it for HTTPS.

Actual final browser captures: [inbox](screenshots/audit-caseflow-inbox.png), [investigation](screenshots/audit-caseflow-investigation.png), [resolved timeline](screenshots/audit-caseflow-resolved.png), [rejection](screenshots/audit-caseflow-rejected.png), [mobile](screenshots/audit-caseflow-mobile.png). The [LIVE sign-in](screenshots/audit-live-sign-in.png) and [configuration error](screenshots/audit-configuration-error.png) captures show real rendered UI with explicitly intercepted configuration/auth fixtures; they are not evidence of LIVE inference. Full disposable test logs/traces are not committed.


The final-image restart check also passed: `scripts/audit_restart.py` created a separate synthetic audit case, persisted an interruption, restarted the actual API and worker containers, reused the existing session, resumed the LangGraph checkpoint and recorded exactly one resolution. The compact result is retained in [audit-restart.json](audit-restart.json). All four services were healthy afterward. The isolated stack was then stopped without `-v`; only generated audit application images/build cache were reclaimed for workspace capacity, with both original and audit data volumes preserved.

**Portfolio-review verdict:** ready for a technical portfolio review of the DEMO workflows and implemented integration contracts, with the limits above explicit. OpenAI/Gemini authenticated LIVE smoke calls, real model quality, deployed Azure behavior and production operational controls remain unverified. This is not a production-readiness statement or a claim of immunity to prompt injection.
