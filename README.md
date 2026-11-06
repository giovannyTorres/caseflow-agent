# Caseflow Agent

A working investigation desk for **fictional charges**, built with Next.js, FastAPI, PostgreSQL, LangGraph and an actual MCP client/server. No real financial operations, regulatory compliance claims or customer data.

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

![Actual Caseflow browser screenshot](docs/screenshots/audit-caseflow-resolved.png)

## Two-minute demonstration

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

- [Optional reviewed glossary / NVIDIA Auto Ontology](docs/ontology.md) — off by default, read-only definitions, exact context approval and decision-only comparison caller.
- [Architecture and decisions](docs/architecture.md)
- [Security and operating model](docs/operations.md)
- [Testing evidence and limits](docs/testing.md)
- [Azure deployment configuration](infra/README.md) — configuration, not a deployed service
- [Guía en español](docs/GUIA_ES.md)
- [Progress log](docs/progress.md)

The product is intentionally a compact portfolio system: one API, one durable worker and MCP child processes. No external merchant integration, real reimbursements, SSO, multitenant customer administration or model quality claims are implied.
