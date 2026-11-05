# Caseflow web

Next.js 16.4.5, React 19.3.1 and TypeScript 5.9.3. All browser API requests use the current origin and are rewritten to the FastAPI service. Credentials stay in HttpOnly session cookies; no model credentials are used in this package.

From this directory:

```sh
npm ci
npm run dev
npm run lint
npm run typecheck
npm test
npm run build
npm start
npm run test:e2e
```

The default web address is `http://localhost:3102`. The server must allow that exact public origin. `API_INTERNAL_URL` selects the API origin at build time (default `http://127.0.0.1:8102` in a host build; `http://api:8102` in the Dockerfile). The root Compose command starts the complete application.

Playwright tests exercise the real API and worker, including analyst investigation, a separate supervisor session, exact-version approval and resolution. Run them against synthetic DEMO data. On a fresh seed, the first test executes the complete flow; on an already resolved seed it checks the persisted result. Tests also cover a supervisor rejection without a reimbursement proposal, insufficient evidence, tool outage recovery, interruption recovery, invalid credentials, keyboard focus, empty search and mobile overflow. These checks are not a WCAG certification.

The tests use `/usr/bin/chromium` when present, `CHROMIUM_PATH` when explicitly set, or Playwright's installed Chromium otherwise. Install the latter with `npx playwright install --with-deps chromium` in CI. Real screenshots are saved in `../../docs/screenshots`.

DM Sans and Manrope are bundled locally under the SIL Open Font License; their license texts are in `public/fonts`. The browser makes no font-service requests. The design uses original layout and visual identity for a fictional organization.

ESLint 9.39.5 is selected because the Next.js React/import/accessibility plugins declare ESLint 9 compatibility. The scoped `@typescript-eslint/typescript-estree` minimatch override pins the patched 11.0.4 release. Vitest 5.1.0 avoids vulnerabilities in earlier test-worker and mock-server packages. `npm audit` reported zero known vulnerabilities during validation; this is a point-in-time dependency check, not a security guarantee.

Official references consulted: [Next.js installation](https://nextjs.org/docs/app/getting-started/installation), [Next.js deployment](https://nextjs.org/docs/app/getting-started/deploying), [Playwright test configuration](https://playwright.dev/docs/test-configuration). Package versions were resolved from the official npm registry and committed to `package-lock.json`.
