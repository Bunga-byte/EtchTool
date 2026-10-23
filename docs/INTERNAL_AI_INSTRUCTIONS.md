# Executable instructions for an authorized internal AI assistant

These instructions apply **inside Samsung's approved development and data-processing environment**. This external repository has synthetic data only and no internal connectivity. Do not retrieve or transfer confidential data into external AI tools. Do not scan hosts, guess endpoints, bypass authentication, scrape restricted UIs, read credential stores, or call an external OCR/AI service for corporate documents.

## 1. Inspect before changing

Read this guide, [SAMSUNG_HANDOFF](SAMSUNG_HANDOFF.md), [security boundaries](SECURITY_AND_DATA_BOUNDARIES.md), [integration matrix](INTEGRATION_MATRIX.md), and the initial gap analysis. Keep the existing UI/framework, core inventory/PM/reliability APIs, migration history and synthetic regression fixtures.

From the checkout root:

```bash
git status --short
git log -1 --oneline
rg --files backend/app backend/tests frontend/src docs schemas integration_manifests
rg '^class |^def ' backend/app/enterprise backend/app/services
./scripts/setup.sh
./scripts/test.sh
```

Inspect the configured remote host and repository identity through a sanitized parser; do not print credential-bearing URLs. This external baseline uses GitHub with a GitLab-compatible CI example. Confirm the actual internal GitLab checkout rather than assuming a previous push exists.

Read `backend/app/models.py`, `backend/app/enterprise/models.py`, migrations, `contracts.py`, `documents.py`, `extraction.py`, `identity.py`, `security.py`, `providers.py`, `telemetry_contracts.py` and `telemetry.py`. Read actual route dependencies and OpenAPI from the running approved local API. Obtain the OpenAPI JSON through the approved local authenticated path when required; never add an unauthenticated enterprise data route to simplify inspection.

Record baseline test output, dependency lock versions and relevant commit. Do not overwrite user files, reset data or change the frontend framework.

## 2. Obtain approved source contracts

For each manifest, request the named source owner, interface documentation, authentication/service account contract, approved equipment and collection scope, supported capabilities, query limits, timezone/clock behavior, correction/version semantics, retention/classification, and source authority. Missing permission or an unknown interface is a hard stop for that retrieval; continue independent code/test work instead.

Use only the approved interface to inspect capabilities and schemas. If schema discovery is unsupported, use the source owner's approved documentation or de-identified managed export. Capability discovery is not endpoint discovery. Record each supported/unsupported operation explicitly. Do not assume REST, SQL, attachment retrieval, historical parts or continuous polling.

`integration_manifests/*.json` are templates. Their `normalized_requirements` names are FRIP destinations, not source fields. Fill `actual_source_field`, approved transform references and verified source capabilities only from the approved contract; keep unobserved information null. Resolve credentials by `SecretProvider`/service-auth references within the internal runtime. Do not store secret values in the manifest.

Validate manifests against `schemas/manifest.schema.json`. Schema validity does not approve access, validate engineering meaning or enable automatic promotion. Create a reviewed versioned internal deployment configuration and retain the original synthetic templates for regression tests.

## 3. Implement a read-only connector

Implement `EnterpriseConnector` and `AuthenticationProvider` from `app.enterprise.contracts`, using the approved transport/SDK/export mechanism. Use `app.enterprise.providers` for corporate service credential and retention interfaces. Do not weaken `SourceScope` or trust client-supplied role names. Replace the local token verifier with approved corporate SSO while preserving server-side role/source/equipment/collection enforcement.

Return explicit capabilities and meaningful errors for unsupported operations. Enforce authorization before list/search/get/attachment/time-series requests; recheck every returned record against the requested scope. Bound historical windows/pages, use documented cursors and source IDs/revisions, detect unchanged content and preserve originals. Never fabricate a source revision from a local ingestion timestamp.

Use the full `metadata_version_token(DocumentMetadata)` for unchanged hints and connector snapshots. Metadata-only changes require retrieval/reconciliation even if content hash and revision did not change. Do not use a cache key that hides corrections to equipment, collection or effective timestamps, and do not disclose cached version hints outside the actor's source/query scope.

Add contract tests for denied source/equipment/collection, unsupported search/attachment/history, bad timestamps/units, pagination, source updates, duplicate content, transient failure/retry and terminal authorization denial. Use approved synthetic/de-identified fixtures rather than production credentials in tests.

Install the adapter through a reviewed server-side connector registry/factory. The external build deliberately selects `fixture_connector` in `orchestrator.py` and `jobs_router.py`, and rejects non-synthetic sources in job creation/execution and `workflow.stage_document`. Merely setting `FRIP_MODE=enterprise` cannot enable a real source. In the internal implementation, replace these synthetic-only dispatch gates with explicit approved-adapter/classification policy, preserving all scope, retrieval-envelope, evidence and review checks. Do not globally disable the guards or relabel real records as synthetic. Add approved source configuration, effective aliases and configuration periods through controlled migrations/configuration; enterprise mode does not seed them.

For user identity, inject a verified provider implementing `app.auth.PrincipalProvider` into `create_app(authentication_provider=...)` with `FRIP_AUTH_BACKEND=external_provider`. Implement service credentials separately through `providers.py`; a user's token is not automatically an upstream service credential. Replace the synthetic-only worker identity with an approved scoped service principal before enabling an enterprise worker. Keep source status/capability reporting accurate for the installed adapter rather than returning fixture health.

## 4. Map documents and facts with exact evidence

Use `parse_document` for supported text/HTML/CSV/JSON/PDF/XLSX. Preserve hashes, revisions, page/row/sheet/block/span locations and parser versions. Do not execute embedded HTML resources, formulas, macros or links. Retain unsupported, over-limit and scanned/OCR-required results as actionable errors. Plug in internal OCR only after approval.

Extend deterministic extraction/mapping for actual document fields. The supported proposal kinds are installation, replacement, maintenance, inventory and failure evidence. Keep new serial `component_serial` distinct from `old_component_serial`. Require aware install/remove times and citations for every significant promoted field.

An internal AI provider may return only schema-constrained unverified proposals with valid citations and uncertainty. Reject unsupported quotations/spans or unknown fields. AI may propose component identity or sensor relationships, but cannot verify its own output or approve canonical changes.

## 5. Resolve and review before promotion

Populate reviewed source-scoped, effective-dated equipment/chamber/slot aliases. Resolve parts by exact serial/part/revision/configuration evidence, not fuzzy descriptions. Missing serial/time, ambiguous matches or source disagreement enters review. Preserve both maintenance and parts originals; authority is an explicit approved field rule, not the most recent arrival.

Exercise the existing approval transaction rather than writing canonical installations with SQL. Confirm compatibility, no active or historical occupancy overlaps, atomic old-part removal/new-part installation, required evidence and actor/source scopes. Approve/reject/correct with a reason and audit. A replacement or technician diagnosis must not automatically confirm a failure.

## 6. Approve sensor mappings and exposure rules

Follow [SENSOR_MAPPING_GUIDE](SENSOR_MAPPING_GUIDE.md). Supply actual channel IDs, units, signal types, quality, configuration periods, range references and sample semantics. Distinguish direct measurement, upstream influence, downstream effect, diagnostic support, shared utility and exposure counter.

Propose and separately approve mapping and exposure rule applicability. Match definition/revision, chamber and configuration periods. Validate state/counter/reset/rollover/gap semantics with controlled source evidence. Follow [RF_HOUR_VALIDATION](RF_HOUR_VALIDATION.md); compare actual known histories and independent meters before promoting exposure for PM.

Use bounded telemetry retrieval and versioned lineage. Do not fill missing RF usage, add unrelated sources, treat current configuration as timeless, or prorate counter deltas across replacement boundaries.

## 7. Exercise durable synchronization and the A–I gate

Run backfill/incremental jobs through persisted checkpoints and review queues. Verify commit-before-checkpoint, unchanged-content idempotence, source revision preservation, parser-version reprocessing, bounded retries, failed-record isolation, dead letters and authorized retry. Do not enable periodic polling until capability, access and source-load policy explicitly allow it.

Run all original regressions and the automated Phase 2 acceptance tests. Confirm these outcomes with retained evidence:

| Scenario | Required assertion |
| --- | --- |
| A | Retrieved maintenance document becomes a reviewed canonical installation with exact source citations. |
| B | Replacement removes A and installs B atomically; each receives only its own eligible exposure. |
| C | Lam parts/maintenance disagreement persists with both originals and an actionable review state. |
| D | Mid-period install/remove clipping matches the hand-calculated RF overlap. |
| E | Counter reset/restart cannot create negative or inflated usage. |
| F | Multiple component-sensor relationship types respect effective configuration and show only applicable history. |
| G | Multiple maintenance/event/trace records link to one adjudicated interruption without downtime multiplication. |
| H | Missing serial or effective time cannot create unsupported inventory, PM or prediction claims. |
| I | Source document + operating trace → extraction/matching/review → canonical update → refreshed component/PM in the preserved UI. |

Commands for existing suites:

```bash
./scripts/test.sh
cd frontend
npm run test:e2e
```

Use the final test selectors and demonstration command recorded in [PHASE2_VALIDATION](PHASE2_VALIDATION.md). Report actual counts/results and unrun checks separately. Do not edit assertions, disable verification or substitute trivial checks to obtain a pass.

## 8. Shadow before release

Complete internal security, data-owner and equipment-engineering reviews. Rebuild using approved internal registries, secrets, database, TLS, logs, backups, audit retention and export policy. Run read-only shadow reconciliation on approved historical and incremental samples. Inspect false identity joins, missing history, exposure deltas and review workload.

No production prediction or precursor claim is authorized by this handoff. Before such a model, establish comparable adjudicated outcomes, censored exposure, leakage-free tool/campaign splits, calibration/uncertainty, false-alert rate, warning lead time and independent physical validation. Release only approved advisory behavior; no equipment control or production writeback is supplied.
