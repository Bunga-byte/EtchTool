"""Public, source-neutral schemas for synthetic file-backed adapters.

These are FRIP interchange records, not proprietary vendor API schemas.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=200)
    recorded_at: datetime
    effective_at: datetime
    equipment_id: str = Field(min_length=1, max_length=200)
    chamber_id: str | None = None
    synthetic: Literal[True]

    @field_validator("recorded_at", "effective_at")
    @classmethod
    def aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include UTC offset")
        return value.astimezone(timezone.utc)


class MaintenanceRecord(SourceRecord):
    work_order_id: str = Field(min_length=1)
    component_serial: str = Field(min_length=1)
    action: Literal["pm", "replacement", "inspection", "repair", "refurbishment"]
    completed_at: datetime | None = None
    finding: str | None = None
    replacement_serial: str | None = None

    @field_validator("completed_at")
    @classmethod
    def completed_aware(cls, value: datetime | None) -> datetime | None:
        return SourceRecord.aware_timestamp(value) if value is not None else None


class FDCRecord(SourceRecord):
    signal: str = Field(min_length=1)
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1)
    operating_state: str = Field(min_length=1)
    measurement_kind: Literal["sensor", "counter", "state"] = "sensor"
    rf_source: str | None = None


class PartRecord(SourceRecord):
    component_serial: str = Field(min_length=1)
    part_number: str = Field(min_length=1)
    position_id: str = Field(min_length=1)
    installed_at: datetime
    removed_at: datetime | None = None
    revision: str | None = None

    @field_validator("installed_at", "removed_at")
    @classmethod
    def interval_aware(cls, value: datetime | None) -> datetime | None:
        return SourceRecord.aware_timestamp(value) if value is not None else None

    @model_validator(mode="after")
    def interval_valid(self) -> "PartRecord":
        if self.removed_at is not None and self.removed_at <= self.installed_at:
            raise ValueError("removed_at must be after installed_at")
        return self


class AlarmRecord(SourceRecord):
    event_id: str = Field(min_length=1)
    event_type: Literal[
        "alarm_asserted", "alarm_cleared", "state_transition", "information"
    ]
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    episode_reference: str | None = None


class CommissioningRecord(SourceRecord):
    milestone: str = Field(min_length=1)
    status: Literal["pending", "passed", "failed", "waived"]
    configuration: str | None = None
    document_reference: str | None = None


class GenericRecord(SourceRecord):
    record_type: str = Field(min_length=1)
    data: dict[str, Any] = Field(min_length=1)


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    records: list[dict[str, Any]] = Field(max_length=10000)
    field_mapping: dict[str, str] = Field(default_factory=dict)
    cursor: str | None = None
    page_size: int = Field(default=100, ge=1, le=1000)


class RawOriginal(BaseModel):
    """Canonical immutable string; callers get copies when decoding it."""

    model_config = ConfigDict(frozen=True)
    source: str
    row: int
    ingested_at: datetime
    original_json: str
    fingerprint: str


class NormalizedRecord(BaseModel):
    source: str
    source_id: str
    recorded_at: datetime
    effective_at: datetime
    ingested_at: datetime
    payload: dict[str, Any]
    fingerprint: str
    quality: str = "valid"
    verification: str = "synthetic_unverified"
    original_json: str


class RowError(BaseModel):
    row: int
    code: str
    message: str
    source_id: str | None = None


class DataConflict(BaseModel):
    subject: str
    field: str
    current_value: Any
    incoming_value: Any
    current_source: str
    incoming_source: str
    current_source_id: str | None = None
    incoming_source_id: str | None = None
    status: Literal["unresolved", "authority_rule_applied"]
    authoritative_source: str | None = None


class IngestionResult(BaseModel):
    source: str
    records: list[NormalizedRecord] = Field(default_factory=list)
    originals: list[RawOriginal] = Field(default_factory=list)
    duplicates: int = 0
    errors: list[RowError] = Field(default_factory=list)
    conflicts: list[DataConflict] = Field(default_factory=list)
    audit: list[dict[str, Any]] = Field(default_factory=list)
    next_cursor: str | None = None
    processed: int = 0
