"""Validated public read models. Extension metadata is retained for traceability."""

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime


class ReadModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class Provenance(ReadModel):
    source: str
    original_source_id: str
    recorded_at: AwareDatetime
    effective_at: AwareDatetime
    last_sync: AwareDatetime
    quality: str
    verification_status: str
    synthetic: Literal[True]


class Exposure(ReadModel):
    dimension: str
    unit: str
    hours: float | None = Field(ge=0)
    lifetime_hours: float | None = Field(ge=0)
    since_refurbishment: float | None = Field(ge=0)
    completeness: float | None = Field(ge=0, le=1)
    confidence: str
    source: str | None
    issues: list[str]


class PM(ReadModel):
    status: Literal["overdue", "upcoming", "ok", "unknown"]
    threshold: float | None
    remaining: float | None
    percent_consumed: float | None
    basis: str
    unit: str


class ComponentSummary(ReadModel):
    id: str
    name: str
    part_number: str
    serial_number: str
    revision: str
    status: str
    subsystem: str
    assembly: str
    position: str
    position_id: str
    installation_id: str
    chamber_id: str
    chamber_name: str
    tool_id: str
    tool_name: str
    installed_at: AwareDatetime
    removed_at: AwareDatetime | None
    exposure: Exposure
    pm: PM
    provenance: Provenance
    synthetic: Literal[True]


class InventoryResponse(ReadModel):
    items: list[ComponentSummary]
    synthetic: Literal[True]


class ComponentDetail(ComponentSummary):
    definition: dict[str, Any]
    identity: dict[str, Any]
    specifications: list[dict[str, Any]]
    installations: list[dict[str, Any]]
    maintenance: list[dict[str, Any]]
    replacements: list[dict[str, Any]]
    failures: list[dict[str, Any]]
    forecast: dict[str, Any]
    fdc: list[dict[str, Any]]


class FailureSummary(ReadModel):
    id: str
    title: str
    component_id: str | None
    component_name: str
    tool_name: str
    chamber_name: str
    started_at: AwareDatetime
    ended_at: AwareDatetime | None
    status: str
    mode: str
    downtime_hours: float = Field(ge=0)
    attribution_status: str
    synthetic: Literal[True]


class FailureList(ReadModel):
    items: list[FailureSummary]
    alarm_only_events: int = Field(ge=0)
    synthetic: Literal[True]


class FailureDetail(FailureSummary):
    chronology: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    hypotheses: list[dict[str, Any]]
    corrective_action: list[dict[str, Any]]
    alarms: list[dict[str, Any]]
    fdc: list[dict[str, Any]]
    review_status: str
    root_cause: str
    downtime: dict[str, Any]


class Health(ReadModel):
    status: Literal["ok"]
    dataset: Literal["synthetic-only"]
    database: Literal["connected"]
    as_of: AwareDatetime
    enterprise_connected: Literal[False]
