# Phase 2 implementation and handoff

Phase 2 extends the existing React/TypeScript and FastAPI/SQLAlchemy application. The original inventory, PM, investigations, reliability calculations and six browser workflows remain in place. No real Samsung/Lam source is connected.

## Delivered behavior

- Fourteen additive enterprise tables and migration `0002` retain immutable source versions, proposals, reviews, exact effective aliases, jobs, checkpoints, dead letters, sensors, configuration periods and calculation lineage.
- Transport-neutral, read-only connector contracts declare supported and unsupported operations. Synthetic document search, attachments, bounded backfill and incremental retrieval run through actual adapters. Full metadata signatures detect corrections even with unchanged document bytes/revision.
- Text, HTML, CSV, JSON, PDF and XLSX parsing preserves exact evidence locations. Internal OCR and AI interfaces retain uncertainty and cannot approve their own proposals. Scanned documents without approved OCR remain actionable errors.
- Engineer approve/reject/correct decisions preserve prior claims and atomically promote validated installation, replacement, maintenance or failure evidence. Missing identity/time and Lam/Informs disagreement remain blocked for review. Replacements never automatically create failures.
- Sensor registry, physical relationships and independently approved exposure rules are configuration-, revision-, chamber- and time-aware. State, counter and validated-interval methods clip to serialized installations, union overlaps, withhold ambiguous usage and retain reproducible lineage.
- Durable jobs provide page transactions, checkpoints, execution leases, retries with bounded exponential backoff, reprocessing, metrics and dead-letter retry. Polling is opt-in; no production scheduler or service identity is assumed.
- Source/equipment/collection authorization covers original evidence, jobs, aliases, proposals, canonical equipment records and calculation ancestry. Verified SSO, service credentials, secrets, retention and export extension points are available. Enterprise mode rejects the unscoped legacy file-import route.
- The existing UI adds an enterprise workspace for sources, jobs, original documents, field-mapping dry runs, review, identities and sensors. Component drawers show applicable diagnostic telemetry and calculation lineage.
- Seven required uppercase handoff guides, six strict machine-readable manifests and a Draft 2020-12 schema identify exactly what approved internal adapters must supply.

## Architecture and demonstration

```mermaid
flowchart LR
  A[Scoped read-only source] --> B[Job / checkpoint / retained original]
  B --> C[Parse / extract / exact evidence]
  C --> D[Identity / validation / engineering review]
  D --> E[Canonical serialized installation]
  E --> F[Approved sensor mapping + RF rule]
  F --> G[Clipped exposure / lineage / PM / UI]
```

From `backend/` after setup, run `../.venv/bin/python -m app.enterprise.demo`. It uses an isolated temporary database and production APIs. The approved replacement stops the old serial at 70 RF hours. The new serial receives five twelve-hour active periods, totaling 60 RF hours, with 590 hours remaining against a fictional 650-hour policy (9.23% consumed). Unapproved telemetry leaves its previous 70-hour baseline untouched. The automated browser scenario verifies the refreshed replacement page and actual lineage cards.

Actual command results, lifecycle arithmetic, A–I acceptance and deployment preservation evidence are recorded in [PHASE2_VALIDATION](PHASE2_VALIDATION.md) and [PHASE2_DEPLOYMENT_VALIDATION](PHASE2_DEPLOYMENT_VALIDATION.md).

## Internal information and implementation order

For Informs, obtain the approved record/document/attachment interface, permissions, schema/export layout, stable IDs, revisions, search behavior, timestamps, maintenance meanings and OCR policy. For FDC, obtain the channel catalog, units, physical meanings, state codes, sampling/coverage, clock behavior, reset/rollover definitions, bounded retrieval limits and configuration history. For Lam parts, obtain current/historical serialized position records, install/remove effective times, revisions, alternates, refurbishment meanings and authority relative to maintenance.

First establish approved corporate identity, service credentials, scope and data boundaries. Then implement Informs and Lam history/reconciliation, validate physical sensor mappings and RF definitions, exercise bounded backfill/incremental recovery, run the A–I acceptance suite, and complete read-only shadow reconciliation before release. [INTERNAL_AI_INSTRUCTIONS](INTERNAL_AI_INSTRUCTIONS.md) gives exact modules, adapter-dispatch gates, provider injection and commands. [SAMSUNG_HANDOFF](SAMSUNG_HANDOFF.md) links all required guides.

Actual endpoints, credentials, source schemas, approved OEM/site limits, retention durations and production prediction validity remain unknown. The external runtime accepts synthetic sources only; enterprise mode alone does not install an internal connector. The configured repository remote is GitHub (`Bunga-byte/EtchTool`); GitLab-compatible CI is included, but no GitLab deployment or push is claimed.

## Files created or modified

The following inventory covers the Phase 2 change relative to baseline commit `80ce79a9ce1deabbc5e904e300e72e910a2092a8`. Local databases, dependencies, logs, screenshots and generated builds are excluded from Git.

- [README.md](../README.md)
- [backend/Dockerfile](../backend/Dockerfile)
- [backend/app/auth.py](../backend/app/auth.py)
- [backend/app/config.py](../backend/app/config.py)
- [backend/app/enterprise/__init__.py](../backend/app/enterprise/__init__.py)
- [backend/app/enterprise/canonical_security.py](../backend/app/enterprise/canonical_security.py)
- [backend/app/enterprise/connectors.py](../backend/app/enterprise/connectors.py)
- [backend/app/enterprise/contracts.py](../backend/app/enterprise/contracts.py)
- [backend/app/enterprise/demo.py](../backend/app/enterprise/demo.py)
- [backend/app/enterprise/documents.py](../backend/app/enterprise/documents.py)
- [backend/app/enterprise/extraction.py](../backend/app/enterprise/extraction.py)
- [backend/app/enterprise/identity.py](../backend/app/enterprise/identity.py)
- [backend/app/enterprise/jobs_router.py](../backend/app/enterprise/jobs_router.py)
- [backend/app/enterprise/models.py](../backend/app/enterprise/models.py)
- [backend/app/enterprise/orchestrator.py](../backend/app/enterprise/orchestrator.py)
- [backend/app/enterprise/providers.py](../backend/app/enterprise/providers.py)
- [backend/app/enterprise/router.py](../backend/app/enterprise/router.py)
- [backend/app/enterprise/security.py](../backend/app/enterprise/security.py)
- [backend/app/enterprise/seed.py](../backend/app/enterprise/seed.py)
- [backend/app/enterprise/telemetry.py](../backend/app/enterprise/telemetry.py)
- [backend/app/enterprise/telemetry_contracts.py](../backend/app/enterprise/telemetry_contracts.py)
- [backend/app/enterprise/telemetry_router.py](../backend/app/enterprise/telemetry_router.py)
- [backend/app/enterprise/worker.py](../backend/app/enterprise/worker.py)
- [backend/app/enterprise/workflow.py](../backend/app/enterprise/workflow.py)
- [backend/app/main.py](../backend/app/main.py)
- [backend/app/seed.py](../backend/app/seed.py)
- [backend/app/views.py](../backend/app/views.py)
- [backend/migrations/env.py](../backend/migrations/env.py)
- [backend/migrations/versions/0002_enterprise_ingestion.py](../backend/migrations/versions/0002_enterprise_ingestion.py)
- [backend/requirements.lock.txt](../backend/requirements.lock.txt)
- [backend/requirements.txt](../backend/requirements.txt)
- [backend/tests/test_api.py](../backend/tests/test_api.py)
- [backend/tests/test_canonical_scopes.py](../backend/tests/test_canonical_scopes.py)
- [backend/tests/test_enterprise_acceptance.py](../backend/tests/test_enterprise_acceptance.py)
- [backend/tests/test_enterprise_documents.py](../backend/tests/test_enterprise_documents.py)
- [backend/tests/test_enterprise_jobs.py](../backend/tests/test_enterprise_jobs.py)
- [backend/tests/test_enterprise_security.py](../backend/tests/test_enterprise_security.py)
- [backend/tests/test_enterprise_telemetry.py](../backend/tests/test_enterprise_telemetry.py)
- [backend/tests/test_enterprise_workflow.py](../backend/tests/test_enterprise_workflow.py)
- [backend/tests/test_manifest_schema.py](../backend/tests/test_manifest_schema.py)
- [backend/tests/test_review_regressions.py](../backend/tests/test_review_regressions.py)
- [docs/DATA_DICTIONARY.md](../docs/DATA_DICTIONARY.md)
- [docs/INTEGRATION_MATRIX.md](../docs/INTEGRATION_MATRIX.md)
- [docs/INTERNAL_AI_INSTRUCTIONS.md](../docs/INTERNAL_AI_INSTRUCTIONS.md)
- [docs/PHASE2_DEPLOYMENT_VALIDATION.md](../docs/PHASE2_DEPLOYMENT_VALIDATION.md)
- [docs/PHASE2_GAP_ANALYSIS.md](../docs/PHASE2_GAP_ANALYSIS.md)
- [docs/PHASE2_IMPLEMENTATION.md](../docs/PHASE2_IMPLEMENTATION.md)
- [docs/PHASE2_VALIDATION.md](../docs/PHASE2_VALIDATION.md)
- [docs/RF_HOUR_VALIDATION.md](../docs/RF_HOUR_VALIDATION.md)
- [docs/SAMSUNG_HANDOFF.md](../docs/SAMSUNG_HANDOFF.md)
- [docs/SECURITY_AND_DATA_BOUNDARIES.md](../docs/SECURITY_AND_DATA_BOUNDARIES.md)
- [docs/SENSOR_MAPPING_GUIDE.md](../docs/SENSOR_MAPPING_GUIDE.md)
- [docs/architecture.md](../docs/architecture.md)
- [docs/data-dictionary.md](../docs/data-dictionary.md)
- [docs/samsung-handoff.md](../docs/samsung-handoff.md)
- [docs/scope-and-limitations.md](../docs/scope-and-limitations.md)
- [docs/security.md](../docs/security.md)
- [fixtures/enterprise/failure-evidence.txt](../fixtures/enterprise/failure-evidence.txt)
- [fixtures/enterprise/fdc-telemetry.json](../fixtures/enterprise/fdc-telemetry.json)
- [fixtures/enterprise/index.json](../fixtures/enterprise/index.json)
- [fixtures/enterprise/installation.txt](../fixtures/enterprise/installation.txt)
- [fixtures/enterprise/lam-conflict.txt](../fixtures/enterprise/lam-conflict.txt)
- [fixtures/enterprise/missing-evidence.txt](../fixtures/enterprise/missing-evidence.txt)
- [fixtures/enterprise/other-tool.txt](../fixtures/enterprise/other-tool.txt)
- [fixtures/enterprise/pm-completion.txt](../fixtures/enterprise/pm-completion.txt)
- [fixtures/enterprise/procedure.html](../fixtures/enterprise/procedure.html)
- [fixtures/enterprise/replacement.txt](../fixtures/enterprise/replacement.txt)
- [frontend/e2e/enterprise.spec.ts](../frontend/e2e/enterprise.spec.ts)
- [frontend/playwright.config.ts](../frontend/playwright.config.ts)
- [frontend/src/api.ts](../frontend/src/api.ts)
- [frontend/src/components.test.tsx](../frontend/src/components.test.tsx)
- [frontend/src/components.tsx](../frontend/src/components.tsx)
- [frontend/src/enterprise/ComponentTelemetry.tsx](../frontend/src/enterprise/ComponentTelemetry.tsx)
- [frontend/src/enterprise/DocumentsWorkspace.tsx](../frontend/src/enterprise/DocumentsWorkspace.tsx)
- [frontend/src/enterprise/EnterpriseWorkspace.tsx](../frontend/src/enterprise/EnterpriseWorkspace.tsx)
- [frontend/src/enterprise/FieldMappingPreview.tsx](../frontend/src/enterprise/FieldMappingPreview.tsx)
- [frontend/src/enterprise/IdentityWorkspace.tsx](../frontend/src/enterprise/IdentityWorkspace.tsx)
- [frontend/src/enterprise/JobsWorkspace.tsx](../frontend/src/enterprise/JobsWorkspace.tsx)
- [frontend/src/enterprise/ProposalsWorkspace.tsx](../frontend/src/enterprise/ProposalsWorkspace.tsx)
- [frontend/src/enterprise/SensorsWorkspace.tsx](../frontend/src/enterprise/SensorsWorkspace.tsx)
- [frontend/src/enterprise/SourcesWorkspace.tsx](../frontend/src/enterprise/SourcesWorkspace.tsx)
- [frontend/src/enterprise/enterprise.css](../frontend/src/enterprise/enterprise.css)
- [frontend/src/enterprise/shared.tsx](../frontend/src/enterprise/shared.tsx)
- [frontend/src/enterprise/utils.test.ts](../frontend/src/enterprise/utils.test.ts)
- [frontend/src/enterprise/utils.ts](../frontend/src/enterprise/utils.ts)
- [frontend/src/main.tsx](../frontend/src/main.tsx)
- [frontend/src/views/Integrations.tsx](../frontend/src/views/Integrations.tsx)
- [frontend/src/views/PartDrawer.tsx](../frontend/src/views/PartDrawer.tsx)
- [integration_manifests/alarms.json](../integration_manifests/alarms.json)
- [integration_manifests/commissioning.json](../integration_manifests/commissioning.json)
- [integration_manifests/fdc_trace.json](../integration_manifests/fdc_trace.json)
- [integration_manifests/generic.json](../integration_manifests/generic.json)
- [integration_manifests/informs.json](../integration_manifests/informs.json)
- [integration_manifests/lam_parts.json](../integration_manifests/lam_parts.json)
- [schemas/manifest.schema.json](../schemas/manifest.schema.json)
