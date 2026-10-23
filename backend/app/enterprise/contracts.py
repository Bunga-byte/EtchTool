"""Transport-neutral enterprise source contracts; no internal endpoint assumptions."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceScope(StrictModel):
    source_id: str = Field(min_length=1)
    equipment_aliases: frozenset[str]
    collections: frozenset[str]

    @model_validator(mode="after")
    def nonempty(self):
        if not self.equipment_aliases or not self.collections:
            raise ValueError("equipment and collection scopes must be explicit and nonempty")
        if "*" in self.equipment_aliases or "*" in self.collections:
            raise ValueError("wildcard source scope is not supported")
        return self

    def permits(self, equipment_alias: str, collection: str) -> bool:
        return equipment_alias in self.equipment_aliases and collection in self.collections

    def require_subset_of(self, maximum: "SourceScope") -> None:
        if (self.source_id != maximum.source_id or
                not self.equipment_aliases <= maximum.equipment_aliases or
                not self.collections <= maximum.collections):
            raise PermissionError("requested source scope exceeds authorized equipment or collections")


class ConnectionConfig(StrictModel):
    id: str
    source_system: str
    connector_type: str = "synthetic_file"
    scope: SourceScope
    auth_provider: str = "synthetic_none"
    secret_references: tuple[str, ...] = ()
    read_only: Literal[True] = True
    synthetic: bool = True


class AuthorizationContext(StrictModel):
    subject: str
    scope: SourceScope


@runtime_checkable
class AuthenticationProvider(Protocol):
    """Resolve corporate service identity internally; never return credentials to UI."""

    def authorize(self, config: ConnectionConfig, requested_scope: SourceScope) -> AuthorizationContext: ...


class ConnectorCapabilities(StrictModel):
    discover_schema: bool = False
    search: bool = False
    retrieve_documents: bool = False
    retrieve_attachments: bool = False
    list_records: bool = False
    get_record: bool = False
    incremental_polling: bool = False
    time_series: bool = False
    installation_records: bool = False
    subscribe_updates: bool = False


class SearchQuery(StrictModel):
    equipment_aliases: frozenset[str] = frozenset()
    collections: frozenset[str] = frozenset()
    chamber_alias: str | None = None
    keyword: str | None = Field(default=None, max_length=200)
    part_number: str | None = Field(default=None, max_length=200)
    serial_number: str | None = Field(default=None, max_length=200)
    start_at: datetime | None = None
    end_at: datetime | None = None
    cursor: str | None = Field(default=None, max_length=4096)
    limit: int = Field(default=100, ge=1, le=200)
    known_versions: dict[str, str] = Field(default_factory=dict)

    @field_validator("start_at", "end_at")
    @classmethod
    def aware(cls, value: datetime | None):
        if value is not None:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("query timestamps must include UTC offset")
            return value.astimezone(timezone.utc)
        return value

    @model_validator(mode="after")
    def ordered(self):
        if self.start_at and self.end_at and self.start_at >= self.end_at:
            raise ValueError("end_at must be after start_at")
        return self


class DocumentMetadata(StrictModel):
    original_id: str
    revision: str
    source_system: str
    collection: str
    title: str
    mime_type: str
    equipment_alias: str
    chamber_alias: str | None = None
    recorded_at: datetime
    effective_at: datetime
    filename: str | None = None
    attachment_ids: tuple[str, ...] = ()
    content_hash: str
    synthetic: bool = True

    @field_validator("recorded_at", "effective_at")
    @classmethod
    def aware(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("source timestamps must include UTC offset")
        return value.astimezone(timezone.utc)


def metadata_version_token(metadata: DocumentMetadata) -> str:
    """Cache the complete source envelope, not merely its body revision/hash.

    Validated timestamps are UTC normalized. Metadata corrections must be
    retrieved and reconciled even when content bytes and revision are unchanged.
    """
    canonical = json.dumps(metadata.model_dump(mode="json"),sort_keys=True,
                           separators=(",",":"),ensure_ascii=False,allow_nan=False)
    return "metadata-sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SourceDocument(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    original_id: str
    revision: str
    source_system: str
    collection: str
    title: str
    mime_type: str
    content: bytes
    equipment_alias: str
    chamber_alias: str | None = None
    recorded_at: datetime
    effective_at: datetime
    filename: str | None = None
    attachment_ids: tuple[str, ...] = ()
    synthetic: bool = True

    @field_validator("recorded_at", "effective_at")
    @classmethod
    def aware(cls, value: datetime):
        return DocumentMetadata.aware(value)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content).hexdigest()

    def metadata(self) -> DocumentMetadata:
        return DocumentMetadata(**self.model_dump(exclude={"content"}), content_hash=self.content_hash)


class DocumentPage(StrictModel):
    items: list[DocumentMetadata]
    next_cursor: str | None = None
    unchanged_count: int = 0
    snapshot: str


class SourceTextSegment(StrictModel):
    """Mapping from parsed characters to a contiguous original source fragment."""
    start: int
    end: int
    source_start: int
    source_end: int


class TextBlock(StrictModel):
    id: str
    text: str
    start: int
    end: int
    page: int | None = None
    row: int | None = None
    sheet: str | None = None
    source_start: int | None = None
    source_end: int | None = None
    locator: str
    source_segments: list[SourceTextSegment] = Field(default_factory=list)
    text_extraction_method: str | None = None
    text_extraction_confidence: float | None = Field(default=None,ge=0,le=1,allow_inf_nan=False)
    text_extraction_provider_version: str | None = None


class ParsedDocument(StrictModel):
    source_system: str
    original_id: str
    revision: str
    content_hash: str
    parser_version: str
    source_timestamp: datetime
    effective_at: datetime
    ingested_at: datetime
    equipment_alias: str
    chamber_alias: str | None = None
    collection: str
    text: str
    blocks: list[TextBlock]
    status: Literal["parsed", "ocr_required", "unsupported", "error"]
    issues: list[str] = Field(default_factory=list)

    @field_validator("source_timestamp", "effective_at", "ingested_at")
    @classmethod
    def aware(cls, value: datetime):
        return DocumentMetadata.aware(value)


class EvidenceSpan(StrictModel):
    source_system: str
    original_id: str
    revision: str
    content_hash: str
    block_id: str
    quote: str
    start: int
    end: int
    page: int | None = None
    row: int | None = None
    sheet: str | None = None
    source_start: int | None = None
    source_end: int | None = None
    locator: str
    parser_version: str
    extraction_version: str
    text_extraction_method: str | None = None
    text_extraction_confidence: float | None = Field(default=None,ge=0,le=1,allow_inf_nan=False)
    text_extraction_provider_version: str | None = None


class FactProposalDraft(StrictModel):
    kind: Literal["installation", "replacement", "maintenance", "inventory", "failure_evidence"]
    payload: dict[str, Any]
    evidence: dict[str, list[EvidenceSpan]]
    confidence: dict[str, float]
    verification: Literal["unverified"] = "unverified"
    method: str
    extraction_version: str
    issues: list[str] = Field(default_factory=list)
    requires_review: Literal[True] = True


class CapabilityUnsupported(NotImplementedError):
    pass


class AccessDenied(PermissionError):
    pass


class TransientConnectorError(RuntimeError):
    """Retryable transport/source failure, classified by the approved adapter."""


class PermanentConnectorError(RuntimeError):
    """Nonretryable schema/configuration/retrieval failure."""


@runtime_checkable
class EnterpriseConnector(Protocol):
    config: ConnectionConfig

    def capabilities(self) -> ConnectorCapabilities: ...
    def health(self) -> dict[str, Any]: ...
    def discover_schema(self, scope: SourceScope) -> dict[str, Any]: ...
    def search(self, query: SearchQuery, scope: SourceScope) -> DocumentPage: ...
    def get_document(self, original_id: str, scope: SourceScope) -> SourceDocument: ...
    def get_attachment(self, original_id: str, attachment_id: str, scope: SourceScope) -> SourceDocument: ...
    def incremental(self, query: SearchQuery, scope: SourceScope) -> DocumentPage: ...
    def list_records(self, query: SearchQuery, scope: SourceScope) -> Any: ...
    def get_record(self, original_id: str, scope: SourceScope) -> Any: ...
    def get_time_series(self, query: SearchQuery, scope: SourceScope) -> Any: ...
    def get_installations(self, query: SearchQuery, scope: SourceScope) -> Any: ...
    def subscribe(self, scope: SourceScope) -> Any: ...
