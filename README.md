# Flex Reliability Intelligence Platform

FRIP is a runnable engineering foundation for chamber inventory, serialized component history, exposure-based PM, equipment investigations, and foundational reliability analysis. It uses **fictional synthetic records only**. It is not connected to Samsung, Lam equipment, or any internal service. Component names, identifiers, traces, failure findings, and demonstration PM intervals are fictional. No OEM limits or production prediction accuracy are claimed.

## Start locally

Prerequisites: Python 3.12, Node.js 22+, npm, and Bash. SQLite needs no database service. Optional `uv` speeds Python installation. From the repository root:

```bash
./scripts/setup.sh
./scripts/dev.sh
```

The UI uses port 5173; the API uses port 8000. In a local workstation browser, open the UI on that port. API schemas and interactive documentation are available at `/docs` and `/openapi.json` on the backend. The frontend proxies `/api` to the backend. Stop both services with Ctrl-C. The seed is idempotent and preserves existing records; it is not a database reset command.

The dataset has a fixed engineering reference date, **2026-01-31 UTC**, so an unchanged fixture produces repeatable PM and exposure results. Historical queries accept explicit UTC timestamps. Status is a property of this synthetic snapshot, not a live equipment feed.

The setup script installs hash-locked Python dependencies, runs Alembic migrations, seeds the local database, and installs the npm lockfile. It does not require corporate credentials or modify shell profiles. `.venv`, SQLite files, caches, build outputs, and `.env` files are ignored by Git. On Windows, use WSL or adapt the documented commands to the approved shell.

## Docker Compose with PostgreSQL

```bash
docker compose up --build -d
docker compose ps
docker compose logs backend
```

The container UI uses port 8080 and the API uses port 8000, bound to the local interface. PostgreSQL is private to the Compose network and retained in `frip-postgres`. The supplied password is explicitly for local synthetic use; configure a new secret before any shared deployment. `docker compose down` stops services and retains the database volume. Avoid `down -v` unless you deliberately want to delete that local database.

The backend waits for PostgreSQL readiness, migrates, and seeds in synthetic mode before serving requests. Enterprise mode skips seeding. The frontend waits for API health and serves the built application through nginx. Container image downloads require access to approved registries.

Cloud builders behind an approved TLS proxy can use the optional [BuildKit CA-secret instructions](docs/cloud-build.md); TLS and package verification stay enabled. The normal workstation command above is unchanged.

## Workflow

1. Select a fictional tool and chamber from the fleet or inventory navigation.
2. Filter installed inventory, choose a historical timestamp, and open a serialized component.
3. Inspect installation/removal history, relevant exposure and coverage, PM policy basis, maintenance, unknown specifications, and provenance.
4. Use the PM planner to find upcoming and overdue demonstration requirements.
5. Open a failure investigation to compare alarms, trace data, physical findings, alternative hypotheses, and attribution status.
6. Compare exposure-normalized counts, exact Poisson intervals, censored survival, revision groups, and unioned downtime in reliability analytics.
7. Inspect file connectors, ingestion quality, and unresolved source conflicts. External connectors remain disconnected.

No UI action controls equipment. A replacement is not automatically a failure; an alarm is not automatically a hardware failure. Engineering hypotheses and statistical estimates have separate labels.

## Tests

```bash
./scripts/test.sh
cd frontend
npx playwright install chromium
npm run test:e2e
```

The first script runs backend tests, frontend unit tests, TypeScript checking, and the production frontend build. The browser suite starts isolated services on ports 18000/15173 with a temporary database and synthetic test credentials. Tests cover lifecycle and historical state, exposure clipping and data-quality handling, statistics, ingestion, authorization, and the principal engineering navigation. GitLab CI examples are in `.gitlab-ci.yml`. See [validation results](docs/validation.md) for checks actually executed and their limitations.

## Configuration and access

| Variable | Purpose |
| --- | --- |
| `FRIP_DATABASE_URL` | SQLAlchemy URL; default `sqlite:///./frip.db` relative to `backend/`. PostgreSQL uses `postgresql+psycopg://…`. |
| `FRIP_MODE` | `synthetic` permits anonymous read-only access; `enterprise` requires configured authentication. |
| `FRIP_AUTH_BACKEND` | `local_tokens` for development; `external_provider` requires a server-installed verified principal provider. A setting alone does not implement SSO. |
| `FRIP_TOKENS_JSON` | Secret server-side token-to-principal bindings for the local auth boundary. Empty by default. Never commit values. |
| `FRIP_CORS_ORIGINS` | JSON array of specifically permitted browser origins. |
| `VITE_API_PROXY_TARGET` | Development proxy target; defaults to the local API. It is not a credential. |
| `FRIP_DB_PASSWORD` | Local Compose database password. |

Mutations require server-assigned roles and bearer authentication. Configure temporary local tokens through a shell or secret manager, and replace this boundary with verified corporate SSO before production. A client-supplied role header grants no permission. The UI can remain read-only while authorized API operations are exercised using the OpenAPI interface. Do not put credentials into frontend build variables. See [security](docs/security.md) for role boundaries and deployment gaps.

Phase 2 token bindings can additionally contain explicit comma-separated `sources`, `equipment` and `collections`, with `export` set to the string `true` only when authorized. Wildcard scopes are rejected. Missing equipment/collection grants cannot retrieve or review enterprise source records merely because the caller has an editing role. Corporate SSO should produce equivalent verified server principals instead of these local development bindings.

## Project map

| Location | Responsibility |
| --- | --- |
| `backend/app/models.py`, `backend/migrations/` | Normalized engineering records and migrations. |
| `backend/app/main.py` | API composition, query projections, validated and authorized mutations. |
| `backend/app/services/` | Exposure, PM, reliability, downtime, and guarded forecasts. |
| `backend/app/integrations/`, `fixtures/` | Typed synthetic file adapters and original source fixtures. |
| `backend/app/seed.py` | Deterministic synthetic equipment and lifecycle scenarios. |
| `backend/tests/` | Domain, API, authorization, and connector tests. |
| `frontend/src/`, `frontend/e2e/` | React engineering workspace and browser workflow tests. |
| `scripts/`, `compose.yaml`, `.gitlab-ci.yml` | Repeatable local setup, deployment, and CI examples. |

Read [architecture](docs/architecture.md), [data dictionary](docs/data-dictionary.md), [API contract](docs/api-contract.md), [analytics assumptions](docs/model-validation.md), and the [Samsung integration handoff](docs/samsung-handoff.md) before extending the foundation. Internal schemas, equipment ID mappings, OEM documentation, SSO, and production model validation remain outside this synthetic implementation.

## Phase 2 enterprise handoff

The integration extension preserves the existing UI/framework and adds source-neutral connector/document contracts, immutable source versions, constrained extraction and evidence, exact identity matching, engineering review, canonical promotion, durable synchronization, and configuration-aware sensor/exposure lineage. External sources remain synthetic; no real Samsung service is connected.

Begin with [SAMSUNG_HANDOFF](docs/SAMSUNG_HANDOFF.md), then use [INTEGRATION_MATRIX](docs/INTEGRATION_MATRIX.md), [DATA_DICTIONARY](docs/DATA_DICTIONARY.md), [SENSOR_MAPPING_GUIDE](docs/SENSOR_MAPPING_GUIDE.md), [RF_HOUR_VALIDATION](docs/RF_HOUR_VALIDATION.md), [SECURITY_AND_DATA_BOUNDARIES](docs/SECURITY_AND_DATA_BOUNDARIES.md), and [INTERNAL_AI_INSTRUCTIONS](docs/INTERNAL_AI_INSTRUCTIONS.md). Strict machine-readable templates are in `integration_manifests/` with `schemas/manifest.schema.json`. The [Phase 2 validation ledger](docs/PHASE2_VALIDATION.md) distinguishes executed results from pending acceptance requirements.

Run the complete synthetic source-to-PM demonstration after setup:

```bash
cd backend
../.venv/bin/python -m app.enterprise.demo
```

This creates and removes an isolated temporary database, retrieves a maintenance document, checks 14 exact evidence spans, approves its replacement proposal, imports operating traces, separately approves sensor mappings and an exposure rule, and requests refreshed component, inventory and fleet PM projections. The removed serial stops at 70 RF hours. The replacement receives 60 RF hours with 590 hours remaining against the fictional 650-hour demonstration policy. No existing application database changes. The browser suite also exercises this approval-to-component-page flow.

In the running UI, open **Data integrations → Enterprise handoff workspace** for sources, bounded ingestion jobs, original documents, review, exact identity mappings and the sensor registry. Component drawers include **Telemetry & lineage**. Anonymous synthetic access remains read-only; engineering decisions require a configured server-side editor/admin identity with the applicable source, equipment and collection grants.

The [implementation report](docs/PHASE2_IMPLEMENTATION.md) lists the changes, architecture, demonstration, remaining internal requirements and complete file inventory. Executed test and deployment evidence is in [PHASE2_VALIDATION](docs/PHASE2_VALIDATION.md) and [PHASE2_DEPLOYMENT_VALIDATION](docs/PHASE2_DEPLOYMENT_VALIDATION.md).
