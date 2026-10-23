# Security boundary and production gaps

The current source/equipment/collection and document-review boundaries are in [SECURITY_AND_DATA_BOUNDARIES](SECURITY_AND_DATA_BOUNDARIES.md). This document retains the foundation deployment requirements.

## Local operation

The default `FRIP_MODE=synthetic` allows anonymous **viewer** requests against a fictional dataset. State-changing routes require bearer credentials mapped to a principal by the server. `FRIP_TOKENS_JSON` is a local-development credential mechanism, not corporate SSO. Token values are secrets; store them outside Git in an approved secret manager or local environment. Never put them in `VITE_` variables or source fixtures. A browser-provided role name is not trusted.

Roles are `viewer`, `analyst`, `editor`, and `admin`. Read APIs are available to an authenticated viewer in enterprise mode. Lifecycle and maintenance-data changes require the editing roles authorized by each endpoint. Ingestion and reconciliation use explicit server authorization. Consult OpenAPI and `backend/app/auth.py` / route dependencies for exact permissions. Endpoint audit decisions record actor, server-assigned role, affected entity, and rationale.

`FRIP_MODE=enterprise` rejects startup without configured authentication and removes anonymous read access. This fail-closed setting is an integration guard, not evidence that the application is production-ready. Replace local token verification with a corporate-approved OIDC/SAML gateway or verified identity adapter before processing proprietary information. Verify issuer, audience, signature, expiry, claims mapping, revocation and tenant/source boundaries. Do not rely on frontend navigation restrictions.

The synthetic inventory CSV export is available to a viewer. Enterprise export requires explicit server-side export permission (or administrative authority) and canonical equipment scope. Corporate classification, purpose approval, field policy and audit retention still require deployment review before enabling confidential datasets. Do not place real internal data into the external version.

## Deployment checklist that remains work

- Terminate TLS through the approved internal ingress; configure trusted proxy behavior and explicit origins.
- Use approved image/package registries, vulnerability scanning, signed release artifacts, SBOMs, and deployment controls.
- Supply database and service credentials through corporate secret management, with rotation and least privilege. The Compose password is solely a local synthetic convenience.
- Validate the implemented source/equipment/collection and canonical-history scopes against corporate roles before multi-team use; add any required tenant or finer field policy.
- Add workload rate limits, request-size limits at ingress, centralized security audit retention, alerting, monitoring, and tested backup/restore.
- Protect logs and evidence attachments against sensitive-data leakage. No real proprietary attachment pipeline is implemented.
- Review historical-write concurrency and database privileges. Raw originals are application-immutable; a database administrator can still modify them. Tamper-evident storage and retention enforcement require deployment controls.
- Perform threat modeling, dependency/license review, penetration testing, disaster recovery and data-governance approval.

There are no recipe write paths, live equipment control paths, interlock controls, automatic shutdowns, or automated maintenance execution. Predictions and corrective actions are advisory records only.
