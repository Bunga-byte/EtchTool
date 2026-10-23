# Feature-to-source integration matrix

Actual source schemas and capabilities are unknown. “Needed records” below means FRIP's normalized information requirement; it does not assert that a named service contains or exposes it. Each interface must enforce source, equipment and collection access before retrieval and again before review/promotion.

| Application feature | Needed normalized records | Intended source category | Required approved capability / permission | Canonical result and review boundary |
| --- | --- | --- | --- | --- |
| Maintenance history | Work reference, type, aware completion time, component identity, findings and source revision | Informs / additional maintenance source | Read permitted records/documents; bounded search only if supported | Work orders/actions after entity and evidence review. Replacement does not imply failure. |
| Document discovery | Original ID/revision, equipment/collection, content hash, title, MIME and attachment references | Informs / commissioning / supplier records | Approved list/search/retrieve and attachment grant separately | Immutable source versions; unsupported search fails explicitly. |
| Engineering extraction | Tool/chamber/slot aliases, serial/part/revision, install/remove/repair/restore findings with exact citations | Informs and authorized exports | Permitted document parsing; internal OCR/AI only when approved | Unverified proposals; human approval required for lifecycle and diagnosis. |
| Current and historical inventory | Serial, definition/revision, physical position, effective install/remove times | Lam parts and maintenance corroboration | Approved installation-history/current inventory access | Reviewed lifecycle; preserve conflicting old/new serial assertions. |
| Identity resolution | Scoped aliases, canonical IDs, effective dates and evidence | All categories plus approved equipment catalog | Identity catalog read; engineer alias-review rights | Exact alias/serial/position resolution; no description-only merge. |
| Sensor catalog | Source/channel ID, function, units, sample cadence, quality, configuration and effective interval | FDC / authorized equipment dictionary | Approved schema/catalog access; no channel-name invention | Registry records and unknown ranges pending controlled documentation. |
| Component sensor context | Component function, sensor relationship type, revision/chamber/configuration and evidence | OEM/control docs + FDC catalog | Approved engineering documents and mapping-review role | Many-to-many verified mappings. Diagnostic context is not predictive health. |
| RF exposure | RF/state intervals or validated counter samples; source/mode, coverage, resets and installation boundaries | FDC / equipment states / approved hour exports | Bounded time-series or export read; query limits and clock semantics approved | Eligible interval/counter derivation with lineage and uncertainty; no unrelated-source sum. |
| PM status | Applicable policy, dimension/unit/threshold, approval basis, completion/reset and eligible usage | Controlled OEM/site policy + maintenance + exposure | Controlled-document read and policy engineering approval | Existing PM planner uses correct approved rule; estimated life is never an OEM PM interval. |
| Failure investigation | Adjudicated episode reference, evidence, alarms, traces, findings and hypotheses | Maintenance + events + FDC | Separate read grants; approved evidence association | One case may contain multiple alarms; preserve alternatives and unknown cause. |
| Downtime | Chamber stoppage intervals, restoration and delay classes, reviewed attribution | Maintenance/events/approved downtime records | Approved history; defined delay classification and attribution authority | Union per chamber; weighted component attribution; critical path needs independent evidence. |
| Commissioning impact | Configuration baseline, milestone planned/actual, acceptance evidence and known issues | Commissioning source | Approved checkpoint/doc retrieval | Milestones; do not equate a delay with proven critical-path impact. |
| Synchronization | Stable source identity/version/hash, reliable cursor, bounded query, permission scope and limits | Every connected source | Approved backfill/incremental/periodic/event capability individually | Durable jobs, checkpoints, retries, dead letters and metrics. Polling is disabled absent explicit approval. |
| Forecast input | Comparable lifetime exposure, serial/revision, censored outcomes and validated precursor evidence | Reviewed canonical history | Authorized history and model-governance approval | Statistical eligibility gates retained; no production-validated predictor supplied. |

## Source manifest matrix

| Manifest | Legacy binding | Actual transport/auth/schema | Internal completion focus |
| --- | --- | --- | --- |
| `integration_manifests/informs.json` | `maintenance` | Unknown/unconfigured | Structured maintenance, attachments, deterministic extraction, exact evidence and reviewed lifecycle. |
| `integration_manifests/fdc_trace.json` | `fdc` | Unknown/unconfigured | Catalog, bounded telemetry, physically eligible source definitions and quality. |
| `integration_manifests/lam_parts.json` | `parts` | Unknown/unconfigured | Effective installed identity and replacement reconciliation. |
| `integration_manifests/alarms.json` | `alarms` | Unknown/unconfigured | Controlled event dictionary, timestamps and failure-evidence association. |
| `integration_manifests/commissioning.json` | `commissioning` | Unknown/unconfigured | Qualification/milestones, revisions and acceptance evidence. |
| `integration_manifests/generic.json` | `generic` | Unknown/unconfigured | Explicit approved future source contract; no generic unrestricted query access. |

The external manifests intentionally contain null `actual_source_field` and `actual_source_capabilities`, empty approved queries/authority rules, no endpoints, no secret values, disabled periodic polling, and disabled automatic promotion. Internal owners must create reviewed versioned deployment configuration rather than treating these templates as a connected production setup.

The enterprise synthetic document registry contains `informs-demo`, `lam-demo` and `fdc-demo`. Its capabilities are discovered from the implementation, not inferred from the six manifest expectations. The legacy six typed file adapters still cover alarms, commissioning and generic records. A manifest's expected workflow capability does not claim that the synthetic connector or actual source implements every listed operation; unsupported operations must remain explicit.
