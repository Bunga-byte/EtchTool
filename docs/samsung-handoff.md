# Authorized Samsung integration handoff

## Current boundary

Every external dataset and result shipped here is synthetic. No Samsung service is connected. No internal endpoint, schema, alarm code, credentials, controlled OEM specification, production recipe or real equipment identifier is embedded. File-backed adapters exercise ingestion contracts; their names express potential roles only. No claim is made about the precise capabilities of c-TTTM, Informs, FDC Trace or Lam UI.

Transfer the repository, dependency locks and documentation through the approved internal GitLab process. Rebuild in the authorized VS Code/development environment using internal package and image registries. Do not copy proprietary data or credentials back into this external workspace.

## Information each adapter needs

| Adapter category | Engineers must supply through approved channels |
| --- | --- |
| Maintenance: c-TTTM / Informs | Authorized API or batch contract; work-order and action IDs; replacement and serial semantics; status vocabulary; opened/completed timestamps; repair findings; correction/update behavior; timezone; access scopes and retention. |
| FDC Trace | Authorized trace retrieval contract; signal dictionary, units and physical meaning; setpoint versus measured values; operating-state labels; RF source identity; cumulative counter rollover/reset behavior; timestamp resolution, clock synchronization, coverage and quality flags; trace retention. |
| Lam UI part tracker | Approved parts export/API; position and configuration mapping; component serial/revision identity; installation versus planned state; effective installation/removal times; refurbishment qualification; correction semantics and authoritative fields. |
| Equipment events | Authorized history contract; original event ID; controlled alarm/event dictionary; asserted/cleared semantics; equipment clocks; event/state correlation keys; update and deduplication rules. A code alone does not identify failed hardware. |
| Commissioning | Approved milestone and qualification schema; configuration baselines; planned/actual checkpoints; acceptance evidence; known issues; defensible critical-path attribution. |
| Additional sources | Named owner, documented interface, legal/data classification, field schemas and units, authentication, pagination/cursors, source authority, quality expectations and operational SLA. |

For every source, specify hostname and network approval, service identity, least-privilege permissions, rate limits, pagination, idempotent identifiers, deletion/correction policy, event and ingestion timestamps, incremental watermark, failure retry policy, lineage and audit requirements. Implement contract tests against approved de-identified fixtures before enabling live synchronization. Do not infer endpoints or discover them by scanning.

The current import API stages validated raw records and preserves original import attempts, audit runs, and conflicts. It does not automatically update domain inventory, installations, failures, or exposure. Supplied file fixtures use separate fictional IDs and dates from the seeded fleet. Internal engineers must implement and validate the explicit mapping and promotion transaction that converts authorized staged records into canonical effective-dated entities after source-authority review.

## Equipment and source authority mapping

Create a reviewed mapping from approved real fab/tool/chamber IDs to FRIP's stable internal IDs. Add configuration-specific subsystem/assembly/position catalogs and effective dates. Keep display names separate from physical identity. Validate duplicate aliases, retired tools, chamber moves, serial reuse, and hardware revisions.

Declare field-level authority, for example which approved source establishes physical installation versus a planned replacement. Preserve conflicting originals and require recorded reconciliation decisions. Never let “latest ingestion wins” become an undocumented authority rule. First validate a maintenance-record/part-tracker disagreement end to end.

## OEM and controlled documents required

Authorized engineers must supply exact variants, compatible part/configuration relationships, position catalogs, real part numbers and revisions, applicable RF sources, physical exposure mechanisms, approved parameter units and limits, document IDs/revisions/effective dates, OEM PM requirements and approved site policies. The bundled null specification values remain unknown until verified; fictional demonstration thresholds must not migrate as production limits.

## Authentication and deployment replacement

Replace the local bearer-token provider with corporate SSO verification and approved group-to-role mapping. Define source/equipment/field access boundaries, enterprise export rules, audit retention, emergency access and credential rotation. `FRIP_MODE=enterprise` is a fail-closed guard and does not itself implement SSO. Do not permit anonymous reads against real records.

Use approved internal PostgreSQL, ingress TLS, secret management, observability, backups, controlled migrations, internal package registries and GitLab CI runners. Review dependency licenses, images, supply-chain attestations, ingress limits, database privileges, transactional overlap enforcement and raw-record retention. Define separate environments and explicit release gates.

## Recommended completion order

1. Obtain data owner, security, equipment engineering and corporate deployment approval; establish SSO, least-privilege read-only access, real identity mappings and controlled configuration catalogs.
2. Integrate part history and maintenance records together. Validate installation/removal, replacement identity and reconciliation against an approved historical sample before displaying current physical truth.
3. Integrate operating-state/RF exposure with documented source/counter semantics, independent meter checks, completeness and replacement-boundary validation. Approve PM policies separately from OEM specifications.
4. Integrate alarm and downtime histories. Have engineers adjudicate episodes and attribution; establish delay definitions and avoid double counting. Add commissioning records and critical-path evidence where relevant.
5. Integrate approved FDC traces with state normalization and unaffected controls. Use engineering investigation first; an anomaly is a correlation until physically supported.
6. Build a versioned, authorized historical cohort for statistical models; validate censoring, revisions, mechanisms and denominators. Evaluate held-out tools/campaigns and calibrated uncertainty.
7. Run any precursor predictor in shadow mode. Promote advisory recommendations only after independent engineering validation, false-alert/lead-time assessment, governance approval and production security review.

## What has only synthetic validation

Installation integrity, interval arithmetic, counter edge cases, PM thresholds, source conflict examples, deduplication, downtime attribution, statistical formulas, prediction eligibility/leakage guards and UI workflows are tested with synthetic fixtures. These tests establish software behavior, not actual Flex failure rates, OEM compliance, diagnostic accuracy, production data completeness, real source permissions or operational benefit. See [scope and limitations](scope-and-limitations.md).
