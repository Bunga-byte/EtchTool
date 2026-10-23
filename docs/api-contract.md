# FRIP application contract

All `/api` routes operate on synthetic data by default. Times are ISO 8601 UTC, interval ends are exclusive. Units and provenance travel with exposure. No thresholds are OEM specifications. JSON collection routes return `{ "items": [...] }` unless stated otherwise.

## Read routes

- `GET /api/health`: `{status, dataset, database}`.
- `GET /api/hierarchy`: `{sites:[{id,name,tools:[{id,name,variant,status,chambers:[{id,name,status}]}]}]}`.
- `GET /api/fleet`: `{metrics:{tools,chambers,installed_components,pm_due,open_investigations,downtime_hours},tools:[{id,name,variant,status,chambers:[{id,name,status}]}],downtime_by_subsystem:[{name,hours}],recent_failures:[Failure],data_quality:{completeness,issues,last_sync}}`.
- `GET /api/inventory?chamber_id=&at=&q=&status=` returns component summaries. `at` reconstructs installed state at a historical timestamp.
- `GET /api/components/{id}` returns a component summary plus `definition`, `specifications`, `installations`, `maintenance`, `failures`, `forecast`, `fdc`.
- `GET /api/pm`: component summaries with PM policy, including overdue/upcoming/ok states. Optional `status`.
- `GET /api/failures`, `GET /api/failures/{id}`: failure register and evidence packet.
- `GET /api/analytics`: `{rate:{failures,exposure_hours,rate_per_1000_hours,lower,upper},survival:[{time,survival,at_risk,failures}],revision_comparison:[{revision,failures,exposure_hours,rate_per_1000_hours}],downtime_by_subsystem:[{name,hours}],weibull:{...},forecast_policy:{...}}`.
- `GET /api/integrations`: connector metadata/status, mapping errors, counts, disconnected enterprise status.
- `GET /api/quality`: source conflicts and provenance quality.
- `GET /api/export/inventory.csv`: CSV of synthetic inventory.

## Shared response objects

Component summary: `id, name, part_number, serial_number, revision, status, subsystem, assembly, position, chamber_id, chamber_name, tool_name, installed_at, removed_at, exposure, pm, provenance`.

Exposure: `dimension, hours, lifetime_hours, since_refurbishment, completeness` (0–1), `confidence, source, issues` (strings). Non-RF parts use a relevant dimension and `unit`; never add unrelated source hours.

PM: `status` (`overdue|upcoming|ok|unknown`), `threshold, remaining, percent_consumed, basis, unit`. Policies explicitly identify synthetic engineer recommendations.

Failure: `id,title,component_id,component_name,tool_name,chamber_name,started_at,status,mode,downtime_hours,attribution_status`. Detail adds `chronology,evidence,hypotheses,corrective_action,alarms,fdc,review_status`.

Forecast: `state,label,eligible,message,model_version,horizons,limitations`; empty horizons when insufficient evidence. Synthetic demonstrations are never validated production models.

## Mutations and security

Viewer access is the default for local synthetic mode. Mutations require a server-configured bearer token mapped to an authorized role; a client cannot select a role via headers. Production mode must fail closed without enterprise authentication configuration. Keep SSO integration abstract and document its boundary.

- `POST /api/installations` with `{component_id,position_id,installed_at,reason}`; reject overlapping component or position histories.
- `POST /api/installations/{id}/remove` with `{removed_at,reason}`.
- `POST /api/failures/{id}/adjudicate` with `{status,note}`; record an audit decision.
- `POST /api/quality/{id}/resolve` with `{decision,note}`; record conflict resolution without rewriting raw records.
- File-import APIs provided by the integration module must validate typed records, enforce editor/admin authorization, retain originals, and report deduplication/errors.

OpenAPI is the authoritative field-level schema. Missing engineering evidence is returned as unknown, never synthesized as a fact.
