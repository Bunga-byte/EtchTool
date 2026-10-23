"""Registered synthetic file sources exercising the enterprise connector contract.

No URLs are accepted and no network request is made. Replace this implementation
with an approved SDK/export/API transport inside the corporate environment.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from .contracts import (
    AccessDenied, AuthenticationProvider, AuthorizationContext, CapabilityUnsupported,
    ConnectionConfig, ConnectorCapabilities, DocumentPage, PermanentConnectorError,
    SearchQuery, SourceDocument, SourceScope, TransientConnectorError,
    metadata_version_token,
)


REGISTERED_SOURCES = {
    "informs-demo": ("synthetic_informs", frozenset({"maintenance", "procedures"})),
    "lam-demo": ("synthetic_lam_parts", frozenset({"parts"})),
    "fdc-demo": ("synthetic_fdc", frozenset({"telemetry"})),
}
FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "fixtures" / "enterprise"


class SyntheticAuthenticationProvider:
    def authorize(self, config: ConnectionConfig, requested_scope: SourceScope) -> AuthorizationContext:
        try:
            requested_scope.require_subset_of(config.scope)
        except PermissionError as exc:
            raise AccessDenied(str(exc)) from exc
        return AuthorizationContext(subject="synthetic-file-service", scope=requested_scope)


class SyntheticFileConnector:
    def __init__(self, config: ConnectionConfig, documents: list[SourceDocument],
                 authentication: AuthenticationProvider | None = None):
        self.config = config
        self._authentication = authentication or SyntheticAuthenticationProvider()
        self._documents = {document.original_id: document for document in documents}
        if len(self._documents) != len(documents):
            raise PermanentConnectorError("registered document IDs must be unique")
        for document in documents:
            if (not document.synthetic or not config.synthetic or
                    document.source_system != config.source_system or not config.scope.permits(document.equipment_alias, document.collection)):
                raise PermanentConnectorError("registered fixture exceeds configured source scope")

    def capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(discover_schema=True, search=True, retrieve_documents=True,
                                     retrieve_attachments=True, incremental_polling=True)

    def health(self) -> dict[str, Any]:
        return {"status": "synthetic_file_available", "source_id": self.config.id,
                "external_connection": False, "documents": len(self._documents),
                "capabilities": self.capabilities().model_dump()}

    def _authorize(self, scope: SourceScope) -> None:
        context = self._authentication.authorize(self.config, scope)
        try:
            scope.require_subset_of(context.scope)
            scope.require_subset_of(self.config.scope)
        except PermissionError as exc:
            raise AccessDenied(str(exc)) from exc

    def discover_schema(self, scope: SourceScope) -> dict[str, Any]:
        self._authorize(scope)
        return {"schema": "frip-synthetic-document-envelope-v1", "proprietary_schema_known": False,
                "fields": list(SourceDocument.model_fields), "capabilities": self.capabilities().model_dump()}

    def search(self, query: SearchQuery, scope: SourceScope) -> DocumentPage:
        self._authorize(scope)
        equipment = query.equipment_aliases or scope.equipment_aliases
        collections = query.collections or scope.collections
        if not equipment <= scope.equipment_aliases or not collections <= scope.collections:
            raise AccessDenied("search exceeds authorized equipment or collections")
        docs = []
        for item in self._documents.values():
            if item.equipment_alias not in equipment or item.collection not in collections:
                continue
            if query.chamber_alias and item.chamber_alias != query.chamber_alias:
                continue
            if query.start_at and item.recorded_at < query.start_at:
                continue
            if query.end_at and item.recorded_at >= query.end_at:
                continue
            searchable = (item.title + "\n" + item.content.decode("utf-8", errors="replace")).casefold()
            if any(term and term.casefold() not in searchable for term in (query.keyword, query.part_number, query.serial_number)):
                continue
            docs.append(item)
        docs.sort(key=lambda item: (item.recorded_at.isoformat(), item.original_id, item.revision))
        snapshot = hashlib.sha256("\n".join(metadata_version_token(doc.metadata()) for doc in docs).encode()).hexdigest()
        query_spec = query.model_dump(mode="json", exclude={"cursor", "limit", "known_versions"})
        query_spec["authorized_scope"] = scope.model_dump(mode="json")
        # Set representations must be canonical across processes.
        query_spec["equipment_aliases"] = sorted(equipment)
        query_spec["collections"] = sorted(collections)
        query_spec["authorized_scope"]["equipment_aliases"] = sorted(scope.equipment_aliases)
        query_spec["authorized_scope"]["collections"] = sorted(scope.collections)
        query_hash = hashlib.sha256(json.dumps(query_spec, sort_keys=True).encode()).hexdigest()
        after = None
        if query.cursor:
            try:
                token = json.loads(base64.b64decode(query.cursor, altchars=b"-_", validate=True))
                if token["snapshot"] != snapshot or token["query"] != query_hash:
                    raise ValueError("source snapshot or filters changed")
                after = tuple(token["last"])
                if len(after) != 3 or not all(isinstance(value, str) for value in after):
                    raise ValueError("invalid cursor key")
            except (ValueError, KeyError, TypeError, UnicodeError) as exc:
                raise PermanentConnectorError("invalid/stale connector cursor; restart bounded batch") from exc
        remaining = [doc for doc in docs if after is None or (doc.recorded_at.isoformat(), doc.original_id, doc.revision) > after]
        page = remaining[:query.limit]
        unchanged = [doc for doc in page if query.known_versions.get(doc.original_id) == metadata_version_token(doc.metadata())]
        visible = [doc.metadata() for doc in page if doc not in unchanged]
        next_cursor = None
        if len(remaining) > len(page) and page:
            last = page[-1]
            token = {"snapshot": snapshot, "query": query_hash,
                     "last": [last.recorded_at.isoformat(), last.original_id, last.revision]}
            next_cursor = base64.urlsafe_b64encode(json.dumps(token).encode()).decode()
        return DocumentPage(items=visible, next_cursor=next_cursor, unchanged_count=len(unchanged), snapshot=snapshot)

    def incremental(self, query: SearchQuery, scope: SourceScope) -> DocumentPage:
        return self.search(query, scope)

    def get_document(self, original_id: str, scope: SourceScope) -> SourceDocument:
        self._authorize(scope)
        item = self._documents.get(original_id)
        if item is None:
            raise PermanentConnectorError("registered document not found")
        if not scope.permits(item.equipment_alias, item.collection):
            raise AccessDenied("document is outside authorized equipment or collection")
        return item

    def get_attachment(self, original_id: str, attachment_id: str, scope: SourceScope) -> SourceDocument:
        parent = self.get_document(original_id, scope)
        if attachment_id not in parent.attachment_ids:
            raise AccessDenied("attachment is not linked to the authorized parent document")
        return self.get_document(attachment_id, scope)

    def list_records(self, query: SearchQuery, scope: SourceScope):
        self._authorize(scope)
        raise CapabilityUnsupported("synthetic document source does not list structured records")

    def get_record(self, original_id: str, scope: SourceScope):
        self._authorize(scope)
        raise CapabilityUnsupported("synthetic document source does not expose structured-record retrieval")

    def get_time_series(self, query: SearchQuery, scope: SourceScope):
        self._authorize(scope)
        raise CapabilityUnsupported("time-series service is not connected; registered JSON telemetry export is available as a document")

    def get_installations(self, query: SearchQuery, scope: SourceScope):
        self._authorize(scope)
        raise CapabilityUnsupported("installation service is not connected; fixture inventory is a document proposal")

    def subscribe(self, scope: SourceScope):
        self._authorize(scope)
        raise CapabilityUnsupported("synthetic file source has no event subscription")


def fixture_connector(source_id: str = "informs-demo") -> SyntheticFileConnector:
    """Only registered fixtures; callers cannot select filesystem paths or URLs."""
    if source_id not in REGISTERED_SOURCES:
        raise PermanentConnectorError("source is not a registered synthetic connector")
    system, collections = REGISTERED_SOURCES[source_id]
    config = ConnectionConfig(id=source_id, source_system=system,
                              scope=SourceScope(source_id=source_id, equipment_aliases=frozenset({"tool1a", "tool2a"}), collections=collections))
    try:
        manifest = json.loads((FIXTURE_ROOT / "index.json").read_text())
    except (OSError, ValueError) as exc:
        raise PermanentConnectorError("registered fixture index could not be read") from exc
    documents = []
    if not isinstance(manifest,list) or len(manifest)>2000:
        raise PermanentConnectorError("registered fixture index has invalid shape or size")
    try:
        for item in manifest:
            if item["source_id"] != source_id:
                continue
            path = (FIXTURE_ROOT / item["path"]).resolve()
            if (not path.is_relative_to(FIXTURE_ROOT.resolve()) or not path.is_file() or
                    path.stat().st_size > 10 * 1024 * 1024):
                raise PermanentConnectorError("registered fixture path or size is invalid")
            values = {key: value for key, value in item.items() if key not in {"source_id", "path"}}
            documents.append(SourceDocument(**values, content=path.read_bytes()))
    except (OSError,ValueError,KeyError,TypeError) as exc:
        raise PermanentConnectorError("registered fixture content could not be loaded") from exc
    return SyntheticFileConnector(config, documents)


__all__ = ["AccessDenied", "CapabilityUnsupported", "TransientConnectorError", "PermanentConnectorError",
           "SourceDocument", "SourceScope", "SearchQuery", "ConnectionConfig", "SyntheticFileConnector", "fixture_connector"]
