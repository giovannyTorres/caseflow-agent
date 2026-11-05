# Azure Container Apps — configuration only

`main.bicep` describes one Container App containing web, API and worker against an **existing PostgreSQL database** and an **existing managed environment**. No resources have been created. Build a web image with `--build-arg API_INTERNAL_URL=http://localhost:8102` because Next rewrites are fixed at build time and containers within this app share localhost. The Compose image instead targets `http://api:8102`.

Validate locally using `az bicep build --file infra/main.bicep` or `bicep build infra/main.bicep`. Actual Azure validation (`what-if`), identity/registry pulls, networking, TLS and runtime operation require an authorized subscription and remain unverified. No provisioning command was executed.

Supply `environmentId`, `webImage`, `apiImage`, `databaseUrl`, `appOrigin`, and optionally provider/model/key as secure deployment parameters. Never commit parameter values. Private ACR images additionally require `registryServer` and an existing `registryIdentityId` with AcrPull. Supply PostgreSQL TLS requirements (`sslmode=require`) in `databaseUrl`, reachability and backups. Set the app origin after assigning the stable HTTPS hostname; deploy LIVE with secure cookies and separately provision LIVE accounts. Configure managed secret references/Key Vault through the organization's deployment workflow; the template accepts secure parameters without printing them.

The worker is a separate process/container reusing the API domain; MCP is its local child process. One replica is intentional for this portfolio configuration. PostgreSQL stores all state. Container resource declarations are configuration, not measured sizing or cost estimates. Deploying this file later can incur cost and is outside the completed local verification.
