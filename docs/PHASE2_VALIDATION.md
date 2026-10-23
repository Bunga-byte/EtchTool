# Phase 2 validation ledger

These results were executed against the completed synthetic implementation. No real Samsung/Lam source was available or connected.

## Regression and deployment

| Check | Result |
| --- | --- |
| `./scripts/test.sh`: backend unit/integration suite | **166 passed**, one Starlette/AnyIO `BlockingPortal` deprecation warning; no failures or skipped tests. |
| Frontend Vitest | **13 passed** across three test files. |
| TypeScript and Vite production build | Passed; 1,605 modules transformed and production assets generated. |
| `cd frontend && npm run test:e2e` | **9 passed**: six preserved foundation workflows followed by three enterprise workflows. |
| Migration `0002`, SQLite | Fresh migration and additive/idempotent seed passed; model/migration comparison reported no drift. |
| PostgreSQL preserved upgrade | `0001 → 0002`, repeated upgrade/seed and clean `alembic check`; all 19 original component identities and 19 complete installation histories unchanged. Two intended spares and three sources added. |
| PostgreSQL fresh install | Repeated migration/seed/check passed in a separate database; six API probes and all six manifest validations passed. |
| Docker build/runtime | Both images built; all three services healthy; UI assets and five nginx-proxied API probes passed. See [deployment evidence](PHASE2_DEPLOYMENT_VALIDATION.md) for image/source checks and command details. |
| Manifest schema | Draft 2020-12 schema self-check and all six source manifests passed in the automated suite and built image. |
| `cd backend && ../.venv/bin/python -m app.enterprise.demo` | Passed using an isolated temporary database: 14 exact evidence spans, approved replacement, 60 new-part RF hours, 590 PM hours remaining and one retained calculation lineage record. |
| Repository whitespace | `git diff --check` passed. |

The final backend run includes four additional full-envelope metadata-conflict regressions after the earlier 162-test result recorded in deployment evidence. The final browser run exercised the complete approved replacement/RF/PM workflow. Logs, temporary databases and generated build output are local execution artifacts and are not committed as application source.

## Synthetic acceptance scenarios

| Scenario | Executed evidence and result |
| --- | --- |
| A: installation | Retrieved maintenance fixture resolves a known uninstalled spare and empty physical slot; approval creates the canonical installation. Source staging alone changes no inventory. |
| B: replacement | Atomic removal/installation at `2026-01-26T00:00:00Z`; the old serial stops at 70 RF hours. Approval replay and unchanged ingestion create no duplicate lifecycle or failure records. |
| C: inventory disagreement | Lam observation disagrees with approved maintenance replacement; both originals remain retained, approval is blocked, and the current serial is not overwritten. |
| D: interval clipping | Installed Jan 26 06:00 and removed Jan 27 06:00; only Jan 26 06:00–12:00 plus Jan 27 00:00–06:00 accrue: **12 RF hours**. Later as-of time does not increase the removed part. |
| E: counter reset | Known controller restart yields **3 observed RF hours** with 75% coverage and an explicit missing pre-reset interval. A narrower interval crossing the reset boundary receives only one attributable hour, with no proration or negative/inflated increment. |
| F: sensor mapping | Two channels retain exposure-counter and supporting-diagnostic relationships. Approval, actual configuration, revision, chamber and effective periods gate traces and exposure; ambiguous configuration and conflicting samples are withheld. |
| G: failure evidence | New maintenance evidence associates with one existing episode; four failure episodes, nine equipment events and the episode's 14 downtime hours do not multiply. Replacement/PM approval creates no automatic hardware failure. |
| H: missing evidence | Missing serial and effective time cannot promote. Engineer correction creates a new linked proposal and preserves the original claim and decision history. |
| I: import-to-UI | Automatic API and browser workflows retrieve/stage a document, verify exact evidence, approve a matched replacement, import traces, separately approve mappings/rule, then verify refreshed inventory, lifecycle, component RF/PM and lineage cards. |

## Scenario I reference arithmetic

The original part receives Jan 21–26 baseline usage: `5 × 14 = 70 RF h`. The new part initially has 70 baseline RF hours; unapproved telemetry does not change this. After the applicable mapping and state rule are approved, five observed twelve-hour ON periods give `5 × 12 = 60 RF h`, replacing the baseline inside that window. Full ON/OFF observations provide complete coverage.

The fictional 650-hour demonstration PM policy therefore gives `650 − 60 = 590 RF h` remaining and `100 × 60 / 650 = 9.23%` consumed. The existing UI rounds the display percentage to 9%; the API retains two decimals. No OEM or actual site-approved limit is claimed.

## Additional safety and recovery coverage

Tests exercise explicit source/equipment/collection scopes, historical/ambiguous aliases, forged role/subject claims, verified identity-provider/export boundaries, foreign canonical identities and audit snapshots, original evidence permissions, legacy import isolation in enterprise mode, metadata-only source corrections, scoped cache hints, retrieval-envelope/query-window enforcement, active worker leases, partial-page rollback, resumed checkpoints, unchanged-content deduplication, exponential retry backoff, permanent dead letters and opt-in polling.

Parser tests cover text/HTML/CSV/JSON/PDF/XLSX, resource limits, scanned-PDF/OCR handling, confidence retention, HTML inline/entity identity preservation and exact AI evidence validation. Exposure tests include unknown states, contradictory intervals/configurations, invalid same-time samples, reset/rollover/gaps and unavailable attribution.

## Limits

Passing these synthetic cases establishes executable software behavior. It does not establish internal credentials, schemas, source connectivity, physical sensor validity, OEM limits, production failure probabilities, SEMI E10 certification or permission to poll. Real adapters, corporate identity/service authentication, approved scope/load, retention and meter reconciliation remain internal implementation and release work described in [SAMSUNG_HANDOFF](SAMSUNG_HANDOFF.md).
