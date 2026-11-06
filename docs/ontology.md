# Reviewed semantic context

Caseflow can optionally add reviewed business definitions through NVIDIA Auto Ontology's public REST gateway. It uses only `GET /api/terms` and `GET /api/terms/{id}`. The same definitions can be loaded as a local glossary. The default is **off**; DEMO never reads a snapshot or contacts NVIDIA.

The integration does not generate an ontology from policies, execute SQL, ingest the operational database or change the agent's five MCP capabilities. The shipped terms are original **curated synthetic fixtures**, not model-generated ontology quality evidence.

## Configuration

For source development, set these alongside the existing LIVE configuration:

```text
ONTOLOGY_MODE=glossary
ONTOLOGY_REQUIRED=true
ONTOLOGY_SNAPSHOT_PATH=fixtures/ontology/glossary-live.json
ONTOLOGY_SNAPSHOT_SHA256=9a0e92f51aaa6c96e44377a185de9fb56154e334828a3039d954da974e76b898
ONTOLOGY_TIMEOUT_SECONDS=5
```

For NVIDIA, select `ONTOLOGY_MODE=auto_ontology`, use a reviewed snapshot whose `source` is `auto_ontology`, and set `AUTO_ONTOLOGY_URL` to the public gateway origin and `AUTO_ONTOLOGY_API_TOKEN` to an API token owned by a suitably restricted account. Use HTTPS, or loopback HTTP for local testing. The example `fixtures/ontology/auto-ontology-live.json` has SHA256 `e852b8a592345d928258c4f040dd80575192400df6b814d4e57b2c8283047eff`; its IDs must actually exist in your catalog with identical reviewed content. It is not a ready-made remote NVIDIA catalog.

Compose forwards these variables to API/worker. Paths inside the image start at `/app`, so its included example is `/app/fixtures/ontology/glossary-live.json`. For a separately reviewed snapshot, mount it read-only at the configured path. Tokens remain server-side and are not forwarded to the MCP subprocess. The subprocess receives only the non-secret snapshot configuration needed to recheck the application's review before creating a proposal.

All remote reads share one total wall-clock budget, including pagination and body streaming. Pages, responses and snapshot sizes are bounded; redirects are rejected. Optional failure records `unavailable_baseline_fallback` and uses the original evidence. Required failure stops before proposing and leaves the investigation retryable. No remote failure is interpreted as evidence that a reimbursement is justified.

## Snapshot review and scope

The snapshot must declare schema version 1, application `caseflow-agent`, a mode, snapshot/source revisions, an explicit application approval with reviewer, and a policy ID/version/content hash. Each term needs both certification flags and a content digest. The configured SHA256 pins the exact snapshot bytes. Remote term flags alone do not authorize a term.

Term digests use UTF-8 JSON with `sort_keys=True`, `separators=(',', ':')`, `ensure_ascii=False`, and no NaN. The hashed object contains `id`, `name`, `description`, sorted unique `synonyms`, `name_certified` and `description_certified`. Policy SHA256 hashes its exact UTF-8 text. Changing spelling, meaning, policy version or approval requires a new snapshot and review.

`ontology.project_evidence` provides a small case/movement/policy projection for an independently operated read-only catalog. It excludes sessions, users, jobs and credentials. This implementation does not automatically upload that projection. Cataloging tables alone does not extract case facts from documents.

## Proposal, approval and replay

Gathering checks that the retrieved movements, current policy and case revision agree. Before every action, the graph checks the captured case/policy revision again. A legacy checkpoint without context, or a stale checkpoint, returns to **gather → decide** before acting, including when an operator prepared a proposal in the meantime; it cannot attach current evidence to an older decision. The existing graph recursion limit still bounds execution.

Each proposal stores its policy text, reviewed definitions, captured case/movement/evidence data, case revision and context digest. The `proposal_prepared` event retains the complete context and digest for **every proposal version**, even after refreshing the current proposal. Approval records that digest. Resolution checks the current proposal version, approval version, case/policy revision and approved context digest before the existing idempotent simulator effect.

A later configured snapshot does not silently replace the evidence already reviewed. To refresh a reviewable proposal, submit the current version to `POST /api/cases/{case_id}/context/refresh` with `{"version":1}`. This reads context again, creates proposal version 2 with the same proposed amount/reason, and clears approval. Concurrent version changes are rejected. The supervisor must review the new context and approve the new version. Older open proposals lacking context after migration also require this refresh; historical resolutions remain readable/idempotent.

These controls preserve Caseflow's existing modes and analyst/supervisor roles. They do not add organization tenancy or per-case ACLs.

## Decision-only comparison with Release Lab

`scripts/semantic_benchmark_caller.py` reads one blind CallerRequest from stdin and emits one Observation JSON. It supports baseline, glossary and auto_ontology arms, uses the same `Decision` model and actual local Ollama model in every arm, and never reads goldens. Configure the model with `CASEFLOW_EVAL_MODEL` (default `qwen3.5:4b`) and loopback service with `CASEFLOW_EVAL_OLLAMA_URL` (default `http://127.0.0.1:11434`). Temperature is 0 and seed is 42 in every arm.

The caller's case context is JSON containing `mode`, `case` (ID, amount, evidence), `movements` (`movements` array), and `policy` (ID/version/text). Policy evidence ID defaults to `id@version`; a supplied `source_id` is also supported. Model output wraps a `Decision` plus explicit evidence IDs, which must belong to observed movements, policy or case evidence. Definition IDs cannot substitute for purchase evidence.

For semantic arms, `options.snapshot` contains a reviewed `path` and `sha256`; `options.snapshots[case_id]` can select a case-specific policy snapshot. `options.ontology_timeout_seconds` controls the bounded remote read budget (default 20 for a cold benchmark gateway). Provide the same source data and equivalent definition content across arms.

The emitted `tool_calls` contains a **decision projection**, `name='decision'`, with `action`, `amount` and sorted `evidence_ids`. No tool, reimbursement, approval or authorization executes. `authorization` is null and the trace declares `scope=decision_only`. A Release Lab agent expectation should set `authorization_required=false`, `allowed_roles=[]`, `action=''`, and independently specify the expected decision projection. This measures action/money/evidence decisions, not successful workflow execution or financial impact.

No configured NVIDIA gateway/token produces `skipped`, before model inference. HTTP transport tests are labeled `transport_mock`. Real calls are `live`; a live catalog seeded with curated terms still is **not an autogenerated ontology experiment**. Compare failures and no improvement as observed. No quality increase is claimed by the fixture or software test counts.

The portable descriptor is `fixtures/ontology/bench-plan.json`, with independent expectations in `bench-cases.json`: two development cases and six final cases. It includes two explicitly synthetic policy versions and the same observed inputs in all arms. The second version adds an 80 MXN cap as a control; it is a benchmark input, not the application's current policy. Do not edit expectations after measuring the model. Run the descriptor with Release Lab's `release_lab.semantic_benchmark --plan <path-to-bench-plan.json> --output-dir <new-directory> --allow-live` command from an environment with its `services/api` on `PYTHONPATH`. The descriptor uses `uv run` inside this repository. Tokens are inherited from the caller's server environment and never stored in the plan. Export artifacts into a new directory and keep their manifest/source hashes with the report.

## Validation

Run `uv run pytest -q tests/test_ontology.py tests/test_semantic_caller.py` against the isolated test PostgreSQL described in the README. Tests cover schema/certification/scope/digests, remote drift, total budgets, bounded responses, actual MCP scope enforcement, per-version context retention, refresh/approval, and legacy/stale StateGraph replay with real PostgreSQL domain operations and MCP transport.

On this Windows host, the pre-change full suite produced 63 passes, 8 failures and 1 LIVE skip: all eight failures came from psycopg async rejecting Windows ProactorEventLoop in `AsyncPostgresSaver`. The new tests avoid that pre-existing platform conflict; the Linux CI workflow verifies the original PostgreSQL checkpoint/subprocess paths. Do not infer Windows checkpoint support from the decision-only benchmark.

The 2026-11-06 local checks passed 35 new tests, with one new durable PostgreSQL replay test reserved for Linux because of that same existing platform limit. A targeted repeat also passed the existing reset/active-writer test after one full-suite run hit its five-second subprocess startup limit. Ruff, Python compilation, frontend lint/typecheck, three existing frontend unit tests and the production build passed. The actual official NVIDIA gateway also returned and verified all three curated term IDs through six authenticated GETs. These checks establish contracts/integrity; model decision results are recorded separately by Release Lab.

Upstream contracts inspected at NVIDIA Auto Ontology `c4495670947eb7b4616f0dd9900e5ced2a48ca1e`: [terms router](https://github.com/NVIDIA/auto-ontology/blob/c4495670947eb7b4616f0dd9900e5ced2a48ca1e/auto_ontology/server/terms/router.py), [authentication](https://github.com/NVIDIA/auto-ontology/blob/c4495670947eb7b4616f0dd9900e5ced2a48ca1e/docs/authentication.md). Upstream certification and RBAC are not assumed to implement the application's case scope.
