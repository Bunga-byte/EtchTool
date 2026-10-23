# File adapter and production integration contract

FRIP includes six working **synthetic file adapters**. They do not call Samsung or Lam services and contain no proprietary endpoint, schema, alarm code, or equipment specification. The typed interchange schema is a local design, not a claim about an internal system's interface.

| Adapter ID | Future authorized source | Required adapter-specific fields |
| --- | --- | --- |
| `maintenance` | c-TTTM / Informs | work_order_id, component_serial, action |
| `fdc` | FDC Trace | signal, value, unit, operating_state |
| `parts` | Lam UI part tracking | component_serial, part_number, position_id, installed_at |
| `alarms` | Equipment alarm/event history | event_id, event_type, code, message |
| `commissioning` | Approved commissioning records | milestone, status |
| `generic` | Additional authorized enterprise source | record_type, data |

Every record also requires `source_id`, timezone-aware `recorded_at` and `effective_at`, `equipment_id`, and `synthetic: true`. Optional `chamber_id` is source context. The external build rejects missing synthetic attestation and unknown fields; source mapping must be explicit. Part removal must be later than installation. Floating point signal values must be finite. Alarm records are observations, never automatic failure confirmations.

## Import and pagination

Use `POST /api/integrations/{adapter_id}/import` with an authorized server-configured maintenance-editor/admin bearer token. The JSON body is `{ "records": [...], "field_mapping": {}, "page_size": 100, "cursor": null }`. The application validates permissions server-side. The API accepts records, not client-controlled file paths or URLs. Fixture examples live at `fixtures/{adapter_id}.json`; `fixtures/fdc.csv` demonstrates CSV interchange. `parse_csv_records` and `parse_json_records` are strict parser entry points for approved offline file-processing jobs.

`field_mapping` maps original column names to the documented FRIP field names. Duplicate targets, collisions and unknown target fields are rejected rather than discarded. JSON input is an array of records; no invented enterprise response envelope is assumed. CSV needs unique headers, matching column counts and ISO timestamps. Optional empty cells become null; generic `data` cells contain JSON.

Pagination sorts by effective timestamp, original source ID and canonical record hash. Return the opaque `next_cursor` with the **same stable batch** until null. The composite cursor preserves distinct events sharing a timestamp. It is not an enterprise change-data-capture watermark: live adapters must supply their source's documented immutable cursor or overlap/replay strategy.

## Preservation, deduplication and conflict handling

The adapter returns canonical raw JSON strings with source, ingestion timestamp and fingerprints for each attempted record, including malformed records that can be serialized. Copies prevent later caller mutations from altering originals. The persistence boundary must store these append-only and retain invalid attempts in ingestion diagnostics. Normalized records carry original and effective timestamps, source identity, quality and synthetic verification status. Audit summaries capture accepted, rejected, duplicate and conflict counts.

Exact canonical normalized payload duplicates are idempotent. Changed payloads using the same source ID are retained and flagged, rather than replacing history. Different source records describing the same identity at the same effective time are compared field by field. Different effective dates can represent legitimate history. Production mapping must define cross-system identity and effective-time tolerances before broader reconciliation is enabled; the file engine does not infer a real part swap from unrelated maintenance text.

No source-of-truth priority exists by default. Approved authority rules explicitly map `adapter_id.field` to a source ID. Rules annotate a conflict decision without modifying either original. Human resolution and materialized equipment state require a separately authorized, audited workflow. An import alone never installs a component or confirms a hardware failure.

## Information required inside the approved corporate environment

For each adapter, internal engineers must supply the approved service owner and access path; actual schema and field semantics; equipment/chamber/part identity mapping; event time zones and clock quality; units, counter reset/rollover semantics and RF source relevance; pagination and incremental-sync guarantees; deletion/correction semantics; rate and size limits; data classification and export policy; source scopes; corporate SSO/service identity and secrets delivery; retention policy; and field-level source-of-authority rules.

Implement approved interfaces behind the adapter contract, preserving immutable raw events and cursor recovery. Test least-privilege read access and reconciliation in an isolated environment. Validate counts, timestamps, configuration applicability and physical failure adjudication before analytical use. None of the external build's synthetic fixtures or interchange schemas establish production correctness.
