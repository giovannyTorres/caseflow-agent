# Independent local review

Session date: 2026-11-05. All data used in these checks is original and synthetic. No model service was contacted and no cloud resource was created.

- Direct HTTP verification against the running FastAPI/PostgreSQL application: unauthenticated protected reads returned 401; authenticated reads succeeded; an explicitly hostile Origin on a mutation returned 403.
- Azure Bicep compiled successfully with CLI 0.48.1. This validates local template compilation, not Azure deployment, networking, identity, or runtime operation.
- The real Playwright screenshots in `screenshots/` were visually inspected. This is not an accessibility certification.

## Authorization and execution boundary

Reviewed domain transactions: supervisor-only approvals and resolutions, exact proposal versions, invalidation after edits, row locking and unique resolution storage. Reviewed real MCP stdio client/server flow: the process capability fixes actor and case outside model arguments; domain permissions are checked again by tools.

The repository's workflow suite exercises these behaviors with PostgreSQL and MCP. These controls are software authorization controls, not a claim that models are immune to prompt injection.
