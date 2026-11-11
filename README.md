# Caseflow Agent

**A review desk for disputed card charges: an agent gathers the movements and the policy through tools, proposes a resolution with its justification, and nothing is executed until a supervisor approves that exact proposal version.**

![Actual Caseflow browser screenshot](docs/screenshots/audit-caseflow-resolved.png)

## Product at a glance

| Question | Answer |
|---|---|
| **What is it?** | An investigation desk for fictional disputed charges. A durable LangGraph workflow calls real MCP tools, prepares a versioned proposal, waits for human approval and then records the outcome in a simulator, with a full audit trail. |
| **Who is it for?** | The **analyst** who investigates the dispute and the **supervisor** who reviews and authorizes the proposed resolution. |
| **What problem does it solve?** | Resolving a dispute means collecting movements and policies, understanding what happened and leaving a trace of the proposal. A sensitive action needs supervision and must not run twice by mistake. Caseflow binds approval to an exact proposal version and refuses duplicate resolutions. |
| **What can it do today?** | Five synthetic cases (duplicate charge, missing delivery evidence, purchase confirmed by the customer, merchant feed outage, interrupted run). The analyst runs an investigation that retrieves movements and policy through MCP; the proposal and its justification appear next to the evidence; the supervisor approves or rejects the exact version; editing a proposal invalidates the previous approval; the resolution is recorded once and later retries are refused; every step is in the activity trail with actor and time. |
| **What is simulated?** | In DEMO the **decision** (propose, request evidence or reject, and its reason) is a per-scenario fixture, shown under *DEMO decisions* and prefixed *"Fixture:"*. Tool calls, authorization, persistence, checkpoints, approvals and the audit trail run for real. The **resolution is a row in a simulator table**: no refunds, no payment systems, no customer messages. |
| **What needs a real model provider?** | LIVE mode asks OpenAI or Gemini for the typed decision (API keys in the backend). **No external model call has been verified**; adapters are tested against simulated HTTP transports only. The simulator stays synthetic even in LIVE. |
| **Main limitations** | Synthetic data and one fictional organization; no SSO; no merchant or bank integration; no model-quality claims; server-side authorization does not prove immunity to prompt injection; Azure files are configuration, not a deployment. |

## Two-minute demo

| Time | Do this | What it shows |
|---|---|---|
| 0:00–0:10 | Open http://localhost:3102, keep role **analyst** (password `demo-pass` is prefilled in DEMO) and click **Enter workspace**. | Inbox of five fictional cases; DEMO mode is always visible. |
| 0:10–0:40 | Open **Two charges, one purchase** and click **Run investigation**. Wait a few seconds. | A *Retrieved movements* table that flags what both charges share (same merchant, amount, currency and posting time), the *Consulted policy* returned by the MCP tool, proposal **v1** with its justification, and *Next action: waiting for a supervisor*. |
| 0:40–0:50 | Open the **Activity** tab. | Tool calls, decision and proposal events with actor and time. No private model reasoning is shown. |
| 0:50–1:20 | Sign out, sign in as **supervisor**, open the same case, click **Approve v1** and confirm. **Record resolution** appears only after the approval; click it and confirm. | The approval dialog applies only to v1. The case becomes **Resolved** in the simulator. |
| 1:20–1:35 | Open **Activity** again. | *Proposal Approved {version 1}*, *Resolution Registered*, *Job Completed*. |
| 1:35–2:00 | Retry the resolution: open http://localhost:3102/api/docs, expand **POST /api/cases/{case_id}/resolve**, *Try it out*, `case_id` = `demo-001`, body `{"version": 1}`, *Execute* (same browser session). | **409**: *"This case is already resolved. The recorded simulator resolution was kept; no new action was created."* Still one resolution. |

Optional, to show approval invalidation: open **Merchant feed unavailable**, run the investigation, then **Resume investigation** after the simulated outage. Approve v1 as supervisor, sign in as analyst and use **Edit proposal**. The proposal becomes **v2**, its status returns to *Awaiting Approval* and resolving v1 is refused until v2 is approved.

Without the browser (Linux, macOS or Git Bash on Windows), the same retry check is:

```sh
curl -s -c cf.cookies -H 'content-type: application/json' -d '{"username":"supervisor","password":"demo-pass"}' http://localhost:3102/api/auth/login
curl -s -b cf.cookies -H 'content-type: application/json' -d '{"version":1}' -w '\nHTTP %{http_code}\n' http://localhost:3102/api/cases/demo-001/resolve
```

The interactive API page loads Swagger UI assets from `cdn.jsdelivr.net`, so it needs internet access; the application itself does not.

## What has been verified and what is pending

| Capability | Status | Evidence |
|---|---|---|
| Clean Docker build and start (`db`, `api`, `worker`, `web` healthy) | Verified | Fresh Compose install in an isolated workspace, 2026-11-09 |
| Analyst → supervisor → resolution walkthrough in a real browser | Verified | Playwright suite (7 flows) against the running containers |
| Approval bound to the exact version; edits invalidate it; amount cannot exceed the dispute | Verified | Direct HTTP checks and `tests/test_security.py`, `tests/test_audit_execution.py` |
| Retries and concurrent resolution requests create one resolution | Verified | Four concurrent requests returned the same job; `test_resolution_retry_is_explicitly_refused_without_duplicate` |
| Tool outage and interrupted runs resume from the saved checkpoint | Verified | `tests/test_workflow.py` and browser flow |
| OpenAI/Gemini structured decisions, truncation and refusal handling | Contract-tested with simulated transports only | `tests/test_providers.py` |
| Real model decisions and their quality | **Not verified** | Needs API keys |
| Azure deployment | **Not verified** | Configuration only |

## Install and start DEMO

Prerequisite: Docker Engine or Docker Desktop with Docker Compose **2.24.4+**. No host Python/Node installation, API key or `.env` file is needed for the container route. The first build downloads the pinned application dependencies and official base images. Ports **3102** (web) and **5542** (PostgreSQL) must be available.

Clone with Git, then start from the repository directory (skip the first two lines if already cloned):

```sh
git clone https://github.com/giovannyTorres/caseflow-agent.git
cd caseflow-agent
docker compose up --build -d --wait
docker compose ps
```

Wait for **db, api, worker and web** to become healthy. Open **http://localhost:3102**. Sign in as `analyst` or `supervisor`, password `demo-pass`. These are public local simulator accounts. No signup or model provider account is needed. Interactive API documentation is at **http://localhost:3102/api/docs**.

A quick read-only check of the web-to-API connection and PostgreSQL is:

```sh
curl --fail --silent --show-error http://localhost:3102/api/health
```

Expected response: `{"status":"ok","mode":"DEMO"}`. This does not run an investigation; use the walkthrough below to check MCP, approvals and resolution. If startup fails, inspect `docker compose logs --tail=80 api worker web`. In the managed workspace with a trusted proxy CA, use `docker compose -f compose.yaml -f compose.cloud.yaml up --build -d --wait`; normal hosts use the first command.

Stop and later restart without deleting case history:

```sh
docker compose down
docker compose up -d --wait
```

Data stays in the named PostgreSQL volume. `down -v` deletes that volume and is not part of the normal stop procedure. Migrations and synthetic seed data run automatically and do not reset completed cases.

For host development, the verified alternative `./scripts/demo-local.sh` requires Python 3.12, uv, Node 24 and Docker. It installs locked dependencies, builds Next, starts API/worker/web on the host and keeps PostgreSQL in Docker. Ctrl+C stops the application processes; `docker compose stop db` then stops PostgreSQL while preserving its data. Stop the container application stack before selecting this alternative, because both routes use port 3102. This launcher always forces DEMO and the default `caseflow-demo` PostgreSQL password; keep using your configured Compose setup if an existing database volume has a custom password.

DEMO replaces only model decisions with labelled scenario fixtures. Tool calls, authorization, proposals, exact-version approvals, checkpoints, audit events and simulator resolutions execute for real. LIVE never falls back to DEMO.

## More scenarios

1. Sign in as analyst; select **Two charges, one purchase** and investigate. The worker retrieves movements and policy through MCP and creates proposal version 1.
2. Inspect movements, user-facing explanation and the event timeline. No private model reasoning is shown.
3. Switch to supervisor, approve version 1 and request resolution. The workflow resumes its PostgreSQL checkpoint and records one simulator resolution.
4. Try **Merchant feed unavailable**, then resume after its fixture outage. Try **Interrupted investigation** to resume an explicit persisted interrupt.
5. **Missing delivery evidence** records an evidence request. **Purchase confirmed by customer** recommends rejection, which requires a supervisor.

To repeat the walkthrough intentionally, run this from the repository root while the DEMO containers are running and no jobs are active:

```sh
docker compose exec -T api .venv/bin/python - --confirm-synthetic-data < scripts/reset_demo.py
```

This resets only the five shipped DEMO cases and their checkpoints; startup never resets data automatically. The script is passed over stdin because the runtime image does not include development scripts. For the host launcher, after installing Python/uv, use `PYTHONPATH=services/api uv run python scripts/reset_demo.py --confirm-synthetic-data` instead.

Editing a proposal invalidates approval. Reimbursements cannot exceed the disputed amount. Row locks and a unique resolution constraint prevent concurrent retries from duplicating the action. These controls establish authorization properties, **not model immunity to prompt injection**.

## Audit and reproducibility

[The technical audit](docs/audit.md) records the initial commit, defects, transaction/lease corrections, exact commands, fresh Compose project, provider contracts and limits. Do not infer model quality from software test counts. The isolated audit uses ports 3202/8202/5642 and a new volume, preserving the ordinary demo.

## Run simple tests

Use Python **3.12** and **uv 0.13.4** for backend tests. From the repository root, create the separate test database once:

```sh
docker compose up -d --wait db
uv sync --frozen
docker compose exec -T db createdb -U caseflow caseflow_test
```

If `caseflow_test` already exists, continue without dropping it. Tests clear their own test tables; they never use the demonstration database. The default URL is `postgresql://caseflow:caseflow-demo@localhost:5542/caseflow_test`. A custom `TEST_DATABASE_URL` must identify a disposable database ending in `_test`.

Start with this small selection of existing regression tests:

```sh
uv run pytest -q \
  tests/test_security.py::test_authentication_and_csrf \
  tests/test_security.py::test_analyst_cannot_approve_or_resolve \
  tests/test_workflow.py::test_investigate_restart_approve_resolve \
  tests/test_providers.py::test_official_sdk_contract_and_resource_close
```

Expected: **5 passed**. These checks exercise direct HTTP authorization, a real MCP investigation/approval/resolution with persisted graph state, and both official SDKs through simulated HTTP transports. They require no API keys and make no model service calls.

For a small frontend test, use Node **24.22.1**:

```sh
cd apps/web
npm ci
npm test
```

Expected: **3 passed**. These unit tests check presentation/filtering helpers; they do not replace the backend or browser workflows.

## Full validation

The audited environment used Docker Compose 2.40.3; the optional audit override requires Compose 2.24.4+. Exact package pins and transitive lockfiles are committed. After the test database setup above, run from the repository root:

```sh
uv run pytest -q
uv run ruff check services tests scripts
uv run python -m compileall -q services scripts
cd apps/web
npm ci
npm run lint
npm run typecheck
npm test
npm run build
npx playwright install --with-deps chromium
npm run test:e2e
```

The last command needs a running DEMO stack and the five shipped cases in their initial states. It performs real mutations and deliberately fails if a completed case would skip a transition. Use a fresh independent Compose project as described in [the audit](docs/audit.md#reproduction-commands), or intentionally reset only your synthetic fixtures using the walkthrough's explicit reset command. No test or startup silently resets the demonstration database. [Testing notes](docs/testing.md) explain browser overrides and storage isolation; [the audit](docs/audit.md#final-candidate-verification) records the complete verified results.

Host development: `PYTHONPATH=services/api uv run uvicorn caseflow.main:app --port 8102` and `PYTHONPATH=services/api uv run python -m caseflow.worker`; in `apps/web`, `API_INTERNAL_URL=http://localhost:8102 npm run dev -- --port 3102`. API and worker run the same idempotent SQL migration and seed under PostgreSQL advisory locks.

## LIVE

Keep `APP_MODE=DEMO` while no API keys are available. All tests above run without credentials. If you explicitly select LIVE without configuration, `/api/config` reports what is missing and investigation fails clearly; it never returns a DEMO decision. Later, follow [exact activation and opt-in smoke verification](docs/live.md). OpenAI and Gemini official SDK adapters validate structured output, bound concurrent requests, set timeouts and apply bounded retries. Terminal truncation, refusal and safety blocks are rejected even if their text looks like valid JSON. They are tested through mocked HTTP transports. **No external model call has been verified in this delivery.** The model proposes a typed decision; server-side tools authorize actual effects. The simulator remains synthetic even in LIVE.

## Engineering review

- [Architecture and decisions](docs/architecture.md)
- [Security and operating model](docs/operations.md)
- [Testing evidence and limits](docs/testing.md)
- [Azure deployment configuration](infra/README.md) — configuration, not a deployed service
- [Guía en español](docs/GUIA_ES.md)
- [Progress log](docs/progress.md)

The product is intentionally a compact portfolio system: one API, one durable worker and MCP child processes. No external merchant integration, real reimbursements, SSO, multitenant customer administration or model quality claims are implied.
