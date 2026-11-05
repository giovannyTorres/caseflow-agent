# Activate and verify LIVE

No keys are needed for DEMO. No paid calls were made during development. Running the smoke command below later can incur provider charges; it is explicit opt-in.

1. Copy `.env.example` to `.env` (ignored by Git).
2. Set `APP_MODE=LIVE`. Choose **one** provider:
   - `MODEL_PROVIDER=openai`, `MODEL_NAME=gpt-4.1-mini`, `OPENAI_API_KEY=<your key>`.
   - `MODEL_PROVIDER=gemini`, `MODEL_NAME=gemini-2.5-flash`, `GEMINI_API_KEY=<your key>`.
3. Set `APP_ORIGIN` to the actual browser origin; set `COOKIE_SECURE=true` for HTTPS. Restart with `docker compose up --build -d`. Missing/unsupported configuration is exposed safely by `/api/config`; an investigation returns 503 instead of falling back to fixtures.
4. Provision separate LIVE accounts from a trusted terminal; the password prompt is not echoed:
   ```sh
   docker compose exec api .venv/bin/python -m caseflow.admin analyst --role analyst
   docker compose exec api .venv/bin/python -m caseflow.admin supervisor --role supervisor
   ```
5. Sign in and investigate a LIVE synthetic case. Check the model decision, real tool results and exact-version approval. The model may request evidence instead of proposing reimbursement.
6. Execute the explicit provider smoke test with a local test PostgreSQL database and the intended provider key injected through the shell/secret manager, not committed in a file:
   ```sh
   RUN_LIVE=1 MODEL_PROVIDER=openai MODEL_NAME=gpt-4.1-mini uv run pytest tests/test_providers.py::test_live_provider_smoke -q
   # Or MODEL_PROVIDER=gemini MODEL_NAME=gemini-2.5-flash with GEMINI_API_KEY configured.
   ```
   The test uses the configured official SDK, validates the response, and never asserts model quality. Tests always isolate their storage in `caseflow_test`, even when provider smoke is opted in.

Timeout is configured by `MODEL_TIMEOUT_SECONDS`, output limit by `MODEL_MAX_TOKENS`. OpenAI has one retry (two total attempts), Gemini two total attempts, and an outer time budget of twice the request timeout. A semaphore allows at most two provider calls per process; the worker performs one investigation at a time. Cancellation propagates to the asynchronous SDK and MCP task. Provider errors are recorded as safe recoverable job failures with correlation IDs; secrets and raw provider exception bodies are not exposed.

The contracts have been verified with HTTP transport fixtures. Real service access, model availability, credentials, provider-specific quotas, real latency and output quality remain **unverified** until this procedure is run with credentials.
