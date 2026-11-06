# Decision-only comparison — 2026-11-06

This run did **not demonstrate an improvement** from the reviewed glossary or NVIDIA Auto Ontology. Release Lab classified the comparison as **inconclusive** because some caller outputs were rejected and therefore could not be evaluated. The integration remains off by default.

## Fixed inputs and execution

- Caseflow source: `027e2dd3b206637db1bf24805530f8a1668a1f24`.
- Release Lab source: `06aca3fce8780e569acd1a7b5376811b8a439ae5`.
- Model: `qwen3.5:4b`, Q4_K_M; local catalog digest `d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04`.
- Same profile in all arms: temperature 0, seed 42, `think=false`, `num_predict=1600`, structured `Decision` plus `evidence_ids`; terminal status and model identity validated.
- Eight original synthetic cases per arm: two development and six final cases, including two policy versions, duplicate settled charges, authorization holds, legitimate purchases and missing evidence.
- [Cases and independent expectations](../fixtures/ontology/bench-cases.json) and [portable plan](../fixtures/ontology/bench-plan.json) were fixed before the first measurement. No expectations, prompts or functional code were changed during the run.
- Arms ran sequentially: baseline, local reviewed glossary, then the official NVIDIA public REST API with the same reviewed definition content. Scope was **decision_only**; no MCP effects, authorizations, approvals, reimbursements or resolutions executed.

The NVIDIA catalog contained manually curated synthetic terms. This measured consumption of reviewed terms through the real API, **not automatic ontology generation**.

## Observed results

Every arm had eight caller invocations. Counts below use that common denominator; an error is unevaluated, so its action, amount and evidence correctness remain **unknown**.

| Result | Baseline | Glossary | Auto Ontology |
|---|---:|---:|---:|
| Valid completed outputs | 7/8 | 2/8 | 2/8 |
| Rejected/error outputs, unevaluated | 1/8 | 6/8 | 6/8 |
| Observed correct actions | 6/8 | 2/8 | 2/8 |
| Observed correct amounts | 7/8 | 2/8 | 2/8 |
| Exact expected evidence inventory | 1/8 | 0/8 | 0/8 |
| Complete strict argument contract | 1/8 | 0/8 | 0/8 |

Among valid outputs, the corresponding action counts were 6/7, 2/2 and 2/2; amount counts were 7/7, 2/2 and 2/2. These conditional counts must not hide the different completion rates. The evidence contract explicitly required the policy reference and all supplied movement/receipt IDs. Exact inventory compliance is narrower than a semantic judgment of whether an explanation is true.

The baseline error envelope recorded `ValidationError`. Each semantic arm recorded five `ValueError` envelopes and one `ValidationError`. The safe error envelopes retain exception type rather than rejected model content or stage-specific diagnostics. They do **not** establish a specific failure cause, and no action or amount has been reconstructed for those cases.

At least **12 authenticated GET requests** are directly retained in the two completed Auto Ontology traces. An additional, separate integration check verified the three curated terms through six GET requests. Error envelopes discard partial context, so this report does not infer the total API request count for the eight-case arm.

## Command latency

| Wall-clock command latency | Baseline | Glossary | Auto Ontology |
|---|---:|---:|---:|
| P50 | 6.93 s | 7.44 s | 8.20 s |
| P95 | 21.44 s | 9.72 s | 11.35 s |

Each column has eight latency observations, including errors. Measurements include process startup, HTTP work and model inference; the baseline also contains the first invocation of the run. Arms were not randomized or repeated. These figures are not isolated model latency or causal estimates of API overhead. Token totals were incomplete because rejected outputs did not retain usage; no monetary cost was estimated.

## Interpretation and reproduction

The semantic arms produced fewer valid outputs in this small run and no increase in complete contract passes. The result does not show that NVIDIA caused the errors, that an automatically generated ontology would behave the same way, or that either semantic approach improves production decisions. A future diagnostic experiment should preserve these results and distinguish model/schema, evidence-reference and service failures before drawing a quality conclusion.

The original generated plan, input snapshots, per-arm `trace.json` and `import.jsonl`, `report.json`, `manifest.json` and `manifest.sha256` were retained locally. Release Lab's manifest verification passed. Derived metrics were computed from those saved outputs without changing the artifacts or expectations.

With sibling Caseflow and Release Lab checkouts, a configured local Ollama service and a reviewed catalog/token in the server environment, a new run can use relative paths:

```sh
cd ../genai-release-lab
PYTHONPATH=services/api CASEFLOW_EVAL_MODEL=qwen3.5:4b uv run python -m release_lab.semantic_benchmark \
  --plan ../caseflow-agent/fixtures/ontology/bench-plan.json \
  --output-dir ../verification/caseflow-decision-new \
  --allow-live
```

Use a new output directory and record the actual source revisions and model digest in the generated plan. Keep credentials in environment variables; the portable plan contains none. A missing NVIDIA configuration is recorded as skipped rather than counted as a successful semantic execution. See [integration configuration and contract](ontology.md).
