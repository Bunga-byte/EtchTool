# Data dictionary

All identifiers and records in the bundled dataset are fictional. UTC-aware timestamps are required. `[start, end)` means an inclusive start and exclusive end. Null engineering specifications mean unknown, not zero. Foreign keys use stable application IDs rather than tool display names. JSON is reserved for source payloads or variable evidence metadata; core relationships use relational keys.

| Table | Meaning and key fields |
| --- | --- |
| `sites` | Fictional fab/site: `id`, `name`, `synthetic`. |
| `equipment_configurations` | Equipment family, fictional variant and hardware revision; does not claim exact Lam configuration. |
| `tools` | Tool identity, site/configuration links, status and lifecycle phase. |
| `chambers` | Chamber identity scoped to tool; unique tool/name. |
| `subsystems` | Configurable chamber subsystem grouping. |
| `assemblies` | Assembly within a subsystem. |
| `positions` | Physical inventory slot within an assembly; relevant exposure source and conceptual description. |
| `component_definitions` | Fictional part number, manufacturer, category, engineering function, hardware revision, relevant exposure dimension, mechanisms and superseding definition. |
| `component_compatibility` | Effective-dated definition/configuration compatibility and verification status. |
| `component_instances` | Serialized physical part: definition, unique serial, lot, supplier, revision, disposition, repair cycle, refurbishment and traceability state. |
| `raw_source_records` | Original source and ID, recorded/effective/ingestion timestamps, canonical payload, content fingerprint, quality and verification. No public rewrite endpoint. |
| `installations` | Effective-dated instance/position assignment, installation/removal reasons, work reference and source. `removed_at = null` denotes the current installation. |
| `specifications` | Parameter, units, nullable nominal/min/max, applicable part revision/configuration, reference document/revision, effective date and verification. OEM values are pending verification in the demo. |
| `refurbishments` | Completion time, qualification flag, findings and provenance. Only a qualified event changes the qualified-refurbishment exposure boundary. |
| `exposure_intervals` | Chamber, source, physical dimension, `[start,end)`, quality, original-source reference, optional quantity for non-duration counters. |
| `observation_coverage` | Time windows in which a source is known to be observed, including RF-off periods. Coverage is not inferred merely from RF-on hours. |
| `counter_samples` | Timestamped cumulative measurement, unit/dimension, optional documented rollover modulus and original source. |
| `pm_plans` | Definition-level dimension/threshold and optional calendar interval, unit, policy basis/reference, effective dates and verification. |
| `pm_due_events` | Recorded component due/completion state and optional completed work-order link. |
| `work_orders` | Maintenance scope, title/kind/status, opened/completed times and source. |
| `maintenance_actions` | Component-specific action and findings under a work order; `confirmed_failure` is explicit and defaults false. |
| `replacement_events` | Old/new serialized instances, work order, timestamp and reason. Not proof that the old part failed. |
| `failure_modes` | Engineering mode and proposed physical mechanism vocabulary. |
| `failure_episodes` | Deduplicated episode, optional implicated component/mode, time, adjudication/attribution, hypotheses and review status. Unknown attribution is permitted. |
| `evidence` | Time, kind, description, quality and original source associated with a case. |
| `equipment_events` | Asserted/cleared symptoms with optional failure link, fictional event labels/codes and primary/secondary role. Standalone alarms are allowed. |
| `fdc_points` | Small demonstration traces: chamber/component, timestamp, signal, value/unit, operating state, comparison cohort and source. |
| `downtime_intervals` | Chamber stoppage window, optional case, delay category, configured classification, optional established critical-path hours and source. |
| `downtime_attributions` | Component contribution weight, adjudication status and rationale per downtime record. Weights must remain within zero and one. |
| `commissioning_milestones` | Planned/actual tool milestone, optional impacting case and explicit critical-path-established flag. |
| `corrective_actions` | Case-specific proposal, owner and validation state. A proposal does not execute maintenance. |
| `source_conflicts` | Two preserved assertions, conflicting field/values, optional component, resolution decision/note/time and state. |
| `audit_logs` | Actor, server-assigned role, timestamp, action/entity and decision metadata. |
| `ingestion_runs` | Adapter, start/completion times, status, records, duplicate counts, errors and incremental cursor. |
| `ingestion_originals` | Immutable original import attempts retained under a run, including invalid attempts; separate from validated raw staging and canonical domain records. |

## Derived API fields

`exposure.hours` is the current selected installation's eligible observed usage, not assumed total calendar time. `lifetime_hours` aggregates eligible installation histories; `since_refurbishment` uses the latest qualified refurbishment boundary. Always read `dimension`, `unit`, `confidence`, `completeness`, and `issues` with the value.

`pm.remaining` and `percent_consumed` derive from the matching policy and observed exposure. A threshold is not a failure probability. A null/unknown result means a policy or adequate supporting measurement is absent.

Fleet downtime uses unions of intervals per chamber, then sums across chambers; this is **chamber-hours**, which can exceed elapsed fleet wall time. Component attribution must not be interpreted as full tool downtime for every associated part. Categories and critical-path impact are separate dimensions.

Failure rates use confirmed failure outcomes and compatible operating-exposure denominators. Distinct revisions or mechanisms should not be pooled without engineering justification. Survival observations pair an observed failure event with its appropriate exposure or a right-censored lifetime.

Field provenance includes source, original source ID, recorded and effective time, verification, quality and synchronization information where present. Missing source metadata is a quality issue; it must not be silently filled as verified truth.

File-backed imports retain staged source records and quality/conflict information. They do not automatically create canonical installations or operating exposure. Entity mapping and approved promotion from staging remain an integration step. The import fixtures use separate fictional IDs from the seeded fleet so an unreviewed example cannot silently alter the synthetic engineering baseline.
