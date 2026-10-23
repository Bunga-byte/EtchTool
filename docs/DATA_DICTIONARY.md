# Canonical schemas and effective-time semantics

This dictionary supplements the [foundation table dictionary](data-dictionary.md). SQLAlchemy models, Alembic migrations and OpenAPI remain the field-level executable schema. Source field names in manifests are unconfigured; the names below are FRIP canonical contracts and do not describe Samsung databases.

## Time, units and provenance

- All event timestamps require a timezone offset and normalize to UTC. Record source clock uncertainty separately when known. Do not silently assume a local timezone.
- Installation, alias, sensor/mapping and exposure intervals use `[start,end)` semantics. Null end means open-ended applicability, not an estimated removal date.
- `recorded_at` describes the source record time; `effective_at` describes when its asserted fact applies; `ingested_at` records arrival. These are not interchangeable.
- Units accompany measurements and thresholds. RF hours, powered hours, calendar days and cycles are different dimensions. Null specifications are unknown; zero is a measured/documented value only.
- Preserve source system/ID, original document revision and content hash, source location, parser/extractor versions, quality and human verification. Confidence is not verification.

## Source and processing entities

| Table / contract | Key relationships and fields | Semantics |
| --- | --- | --- |
| `enterprise_sources` | ID/name, connector kind, classification, capabilities/config, authorized equipment/collections, enabled/polling flags, interval and last success | Configuration and authority boundary. A source entry is not a live connection claim. |
| `source_versions` | Source/raw record, original ID/revision/hash, MIME/content, title, equipment alias/collection, recorded/effective/ingested time, parser/status | Immutable retained original content/version. Unchanged-cache identity includes the complete normalized metadata envelope, not just body hash/revision. |
| `fact_proposals` | Source version, kind/payload/evidence, extraction method/version, confidence, pending/review state, match/validation output, proposal hash and supersedes | Unverified structured claims; corrections create traceable history. |
| `entity_aliases` | Source, entity type, external and canonical IDs, valid-from/to, verification and supporting evidence | Exact source-scoped/effective-dated identity. Ambiguous matches are not silently merged. |
| `engineering_reviews` | Entity type/ID, actor, decision/note/time, before/after | Audit of approve/reject/correct decisions. Does not rewrite original evidence. |
| `sync_jobs` | Source, kind/status, cursor, bounded window, attempts/max, next attempt, requested actor, query, metrics and errors | Durable work; status and committed-page checkpoint are separate. |
| `sync_checkpoints` | Source/stream, committed cursor, job and updated time | Resume only after the associated data transaction is committed. |
| `dead_letters` | Job, optional source version, failing stage/code/detail, created/resolved time | Visible terminal failures requiring diagnosis or authorized retry. |
| `SourceScope` | Source ID, equipment aliases, collections | Intersection of connector configuration and verified principal grants. |
| `ConnectionConfig` | Connector ID/type, source system, scope, authentication provider and secret references | Source-neutral contract. No assumption of REST, SQL, SDK or file transport. The external implementation requires synthetic/read-only records. |
| `ConnectorCapabilities` | Explicit booleans for schema discovery, search, document/attachment retrieval, list/get, incremental polling, time series, installation history, subscription | Unsupported operations raise an explicit capability error. Unknown real capabilities remain null in handoff manifests until discovered. |
| `SourceDocument` | Original ID/revision/source/collection, title/MIME/content, tool/chamber aliases, timestamps, filename and attachment IDs | Authorized document or record wrapper, with SHA-256 content identity. |
| `FactProposalDraft` | Kind, typed payload, evidence, extraction metadata, confidence and review state | Schema-constrained unverified extraction output; never authoritative by itself. |

Authentication is expressed by the `AuthenticationProvider` protocol; connector operations implement `EnterpriseConnector`. Source scopes are explicit nonempty equipment/collection sets and reject wildcards. The synthetic registry currently contains `informs-demo`, `lam-demo` and `fdc-demo` document sources. The six legacy file-adapter categories and six handoff manifests remain available; they do not imply six live enterprise transports.

## Sensor, exposure and lineage entities

| Table | Fields and relationships |
| --- | --- |
| `sensor_channels` | Source/tool/chamber, channel key, subsystem/description, signal type, unit, `sampling_hz`, nullable documented ranges, configuration, effective interval, reference, verification and quality. |
| `component_sensor_mappings` | Definition/sensor, physical relationship/explanation, configuration and optional chamber/revision, effective interval, evidence/confidence, proposed/approved actor and approval time. |
| `exposure_definitions` | Definition/source/sensor, configuration/chamber/revision, dimension, state/counter/validated-interval method, source name, active value, maximum gap in seconds, optional rollover/rate, union aggregation, effective interval, documentation and approval. |
| `sensor_samples` | Sensor/source version, timestamp and optional end, value/state, reset flag/time/baseline, quality and exact source location. |
| `calculation_lineage` | Component/rule, source-version IDs, derived intervals, method version, UTC calculation window, input hash, result/issues and creation time. |
| `equipment_configuration_periods` | Tool/configuration, effective interval, verification and original-source reference. |

## Canonical maintenance proposal fields

Supported document proposal kinds are `installation`, `replacement`, `maintenance`, `inventory` and `failure_evidence`. Relevant payload fields include `tool_alias`, `chamber_alias`, `position_alias`, `part_number`, `component_serial`, `revision`, `installed_at`, `removed_at`, `old_component_serial`, `work_order_reference`, `maintenance_type`, `completed_at`, `pm_completed_at`, `findings` and `failure_id`. Required combinations depend on proposal kind and the promotion validator.

`EngineeringClaim` additionally constrains optional equipment configuration/component name, restoration time, replacement reason, symptom/reported mode, technician diagnosis, troubleshooting/root-cause text, downtime references and attachment references. Extracting such a field is not equivalent to setting a verified root cause or a proven failure in the canonical domain; review and the selected promotion kind determine its permitted use.

For replacement, `old_component_serial` identifies the removed instance and `component_serial` identifies the newly installed instance. The old removal and new installation times are distinct; a gap is not RF exposure. Missing serial or effective time blocks authoritative lifecycle promotion. A text mention of a diagnosis does not confirm a hardware failure.

Telemetry uses a separate typed ingest path. It must not be smuggled through an untyped maintenance fact. Sensor/catalog, mapping and exposure details are described in the [sensor guide](SENSOR_MAPPING_GUIDE.md) and [RF validation guide](RF_HOUR_VALIDATION.md).

## Evidence and review integrity

An extracted field is linked to an original version by hash/revision and an exact location: page for PDF, row/sheet for tabular records, or block/text-span for textual content where available. Parser and extraction method/version accompany the claim. For formats without a meaningful page, do not manufacture one; preserve the actual row/span reference.

Raw document content may contain confidential text in a future internal deployment. Retention, encryption, database access and display permissions must protect it at least as strongly as the original source. External fixtures are synthetic only.

Connector unchanged hints use `metadata_version_token(DocumentMetadata)` from `app.enterprise.contracts`, a SHA-256 token over the complete UTC-normalized metadata envelope. A changed equipment alias, collection, effective time, title or other metadata must be retrieved and reconciled even when the body and revision are unchanged. Do not replace this with a revision/content-only cache key. Source scope and bounded query authorization still apply before constructing or accepting those hints.

## Legacy ingestion compatibility

Existing `raw_source_records`, `ingestion_runs` and `ingestion_originals` preserve the original file import API. Those imports are staging records. The Phase 2 source-version/proposal/review workflow adds the explicit path to canonical promotion; receiving a source record alone never changes physical inventory. Use approved identity/evidence/review transactions rather than bypassing them with direct SQL.
