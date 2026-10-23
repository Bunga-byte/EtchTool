# Validation record

Validated in the supplied cloud workspace with Python 3.12, Node 24 locally, Node 22 in the frontend build container, SQLite, PostgreSQL 16, and Chromium. All application records are fictional. The seed's engineering snapshot is 2026-01-31 UTC.

| Check | Executed result |
| --- | --- |
| `./scripts/setup.sh` | Hash-locked Python installation, frozen npm installation, migration and synthetic seed succeeded. Existing seed runs preserve records. |
| `./scripts/dev.sh` | API and frontend started from the repository root; hierarchy, inventory and calculated exposure requests succeeded. |
| `cd backend && ../.venv/bin/python -m pytest -q` | **73 passed**, one upstream Starlette/AnyIO deprecation warning. No skipped or expected-failure tests. |
| `cd frontend && npm test -- --run` | **6 passed** with Vitest 4.1.12. |
| `cd frontend && npm run build` | Strict TypeScript checks and production Vite build passed. |
| `cd frontend && npm run test:e2e` | **6 passed** in Chromium, using isolated temporary SQLite and explicitly synthetic test credentials. |
| `npm audit` | **0 vulnerabilities** after upgrading the test toolchain. This is a dependency advisory check, not a penetration test. |
| Docker Compose | Backend and frontend images built; PostgreSQL, API and nginx health checks passed. The cloud build used its supplied trusted proxy CA without disabling TLS or package hash checks. |
| PostgreSQL migration and seed | Upgrade and seed each ran twice; `alembic check` reported no new operations. Full migration DDL also parsed in a rolled-back scratch PostgreSQL schema. |
| Database parity | Component exposure matched exactly between SQLite and PostgreSQL for a representative serialized component. |
| Production browser smoke | nginx-served UI and API backed by PostgreSQL: fleet, chamber inventory and component lifecycle opened; no page errors. |
| Configuration checks | Shell syntax, Compose configuration and GitLab YAML parsed. **GitLab pipelines were not executed.** |

The browser suite verifies chamber/subsystem/assembly selection, serial search, historical replacement lookup, component history, PM filtering, statistical plots and the separate teaching forecast, failure evidence, source conflicts, CSV download, API errors, mobile navigation, authenticated adjudication, reconciliation decisions, and synthetic file ingestion. It asserts that importing staged records does not silently change physical inventory.

Backend tests exercise interval boundaries and removal, exposure/refurbishment, reset/rollover/gap/conflict cases, installation integrity, historical state, exact confidence intervals, right censoring, PM uncertainty, downtime allocation, duplicate episodes, model leakage guards, source scopes, raw-source retention, import retries/conflicts and authorization. A disputed serialized identity cannot establish an overdue PM disposition, even when provisional usage exceeds a threshold.

The final full browser run followed fixes for import-result retention and tested valid mutation contracts. Initial failures discovered and corrected during development included PostgreSQL reserved-word quoting, container file permissions, proxy-aware readiness, scope binding, ambiguous exposure allocation, and frontend/API field mismatches. These are resolved in the project source.

## What these results establish

The standalone synthetic workflow and the PostgreSQL container path run in this workspace. They do not establish real Flex equipment accuracy, SEMI certification, corporate deployment approval, production concurrency/load capacity, enterprise SSO, live Samsung connectivity, or a validated predictive model. See [scope and limitations](scope-and-limitations.md) and the [Samsung handoff](samsung-handoff.md).

File imports are validated, retained and audited in staging. Approved internal identity mappings and canonical lifecycle promotion are still required. Human source decisions remain pending materialization; a review never silently rewrites equipment history.

The cloud environment's `install_script` and `start_skill` were saved as a draft. Saving does not publish a snapshot or prove restoration in a fresh task. Review/save the environment settings and publish through the onboarding UI when ready.
