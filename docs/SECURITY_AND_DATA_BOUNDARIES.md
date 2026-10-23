# Security and data boundaries

Actual Samsung/Lam information is confidential unless corporate classification says otherwise. This external repository and its demonstrations contain synthetic data only. No internal endpoint, identity, channel name, OEM specification, controlled document or real credential is assumed or supplied.

## Separate configurations

| Configuration | Permitted behavior | Required boundary |
| --- | --- | --- |
| External synthetic | Fictional connectors/fixtures, anonymous read-only viewer, configured synthetic editing tokens | No corporate records, endpoint discovery, network connector, external AI processing or equipment control. |
| Authorized internal shadow | Approved read-only source retrieval and local proposals against reviewed historical samples | Corporate SSO/service auth, equipment/collection scopes, classification/retention, approved network/queries and no unapproved promotion. |
| Authorized internal production | Only reviewed and released ingestion/promotion permitted by corporate policies | Security/engineering approval, verified mappings/limits, audit retention, operational controls and tested recovery. No automatic equipment intervention. |

`FRIP_MODE=enterprise` disables anonymous application-data access and synthetic auto-seeding; it is not a substitute for SSO or deployment approval. The local token provider must be replaced by a verified corporate identity provider with issuer/audience/signature/expiry/claims checks and approved role mapping. A status-only health endpoint may remain unauthenticated; data APIs must not.

## Authorization layers

Authenticate the caller and service account. Map a verified principal to roles on the server. Non-administrative callers need explicit source, equipment alias and collection grants for discovery, retrieval, original-evidence display, review, retry, mapping approval and canonical promotion. Bound the requested time range and page size. The bundled administrative role can manage all registered sources within each source's configured maximum equipment/collection scope; it cannot discover an arbitrary upstream source. Corporate role mapping must reserve this role for that administrative authority or implement a narrower approved policy before deployment.

Connector configuration and principal scopes must both permit the operation. Capabilities state what the interface supports; grants state what this caller may do. Neither is a replacement for the other. A source that supports attachments may still deny a particular attachment or collection.

Authentication providers receive **secret references**, not checked-in credential values. Resolve references through the approved corporate secret manager within the internal runtime. Never include token values in JSON manifests, URLs, logs, exception messages, screenshots, frontend variables or chat. Do not extract proxy-held credentials.

## Hard stops

- No approved interface, named data owner, permission, equipment/collection grant or query approval: do not retrieve or poll.
- Unsupported capability: return a supported error, without scanning, scraping, UI automation or guessing an endpoint.
- Unknown serial/slot/effective time or ambiguous identity: quarantine/review without canonical lifecycle claims.
- Unverified sensor mapping, unknown physical source/mode or undocumented PM limit: do not label exposure or PM as verified.
- Conflicting source assertions: retain both, surface review and record the authority decision.
- Scanned PDF without an approved internal OCR provider, or an unsupported document type: retain source/error and require a supported parser/provider.
- Unstructured interpretation without valid exact evidence/schema: reject or mark unverified; AI cannot self-approve.
- Corporate records sent to an external AI/OCR/telemetry service without explicit corporate authorization: stop the operation.

## Data and model controls

No writeback to Informs, Lam UI, FDC, other production systems, recipes or equipment is implemented. Review actions write FRIP's auditable canonical history only. No interlock changes, live hardware controls, automatic shutdowns or maintenance execution exist.

PDF extraction uses a document parser; scanned images require the internal OCR extension. XLSX processing reads cells without executing macros, formulas or external links. HTML is parsed into text, not trusted executable UI. Enforce parser size/page/row/text/decompression limits and source hashes. Restrict evidence display and exports to the same source/equipment/collection permission as retrieval.

Production retention is an approved policy to supply, not a guessed duration. Retain raw versions, rejected/invalid evidence, review history, checkpoints and lineage for the required audit period. Implement legal hold, deletion authorization, backup/restore, encryption, tamper evidence and centralized monitoring according to corporate standards. Do not assume an application-level “immutable” record protects against database administrator changes.

Source synchronization is read-only by default. Backfill, periodic polling and event subscriptions require individual capability and load approval. Retry transient failures with bounded backoff; do not repeatedly retry an authorization denial. Dead letters must not expose credentials or uncontrolled confidential content in operational logs.

Synthetic tests validate software behavior, not real data accuracy or model eligibility. Statistical/predictive outputs remain advisory. Production precursor claims require physical rationale, independent tool/campaign validation, calibration/false-alert/lead-time assessment and shadow-mode engineering review.
