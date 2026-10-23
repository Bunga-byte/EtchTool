"""Normalized effective-dated engineering records; originals are retained separately."""

from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Timestamp must include UTC offset")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        return (
            value.replace(tzinfo=timezone.utc)
            if value is not None and value.tzinfo is None
            else value
        )


class Base(DeclarativeBase):
    pass


def pk():
    return mapped_column(String(80), primary_key=True)


def ref(table, nullable=False):
    return mapped_column(ForeignKey(table + ".id"), nullable=nullable, index=True)


def stamp():
    return mapped_column(UTCDateTime(), nullable=False)


class Site(Base):
    __tablename__ = "sites"
    id: Mapped[str] = pk()
    name: Mapped[str] = mapped_column(String(160))
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class EquipmentConfiguration(Base):
    __tablename__ = "equipment_configurations"
    id: Mapped[str] = pk()
    family: Mapped[str] = mapped_column(String(80))
    variant: Mapped[str] = mapped_column(String(120))
    revision: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text)


class Tool(Base):
    __tablename__ = "tools"
    id: Mapped[str] = pk()
    site_id: Mapped[str] = ref("sites")
    configuration_id: Mapped[str] = ref("equipment_configurations")
    name: Mapped[str] = mapped_column(String(120), unique=True)
    status: Mapped[str] = mapped_column(String(40))
    phase: Mapped[str] = mapped_column(String(80))


class Chamber(Base):
    __tablename__ = "chambers"
    id: Mapped[str] = pk()
    tool_id: Mapped[str] = ref("tools")
    name: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(40))
    __table_args__ = (UniqueConstraint("tool_id", "name"),)


class Subsystem(Base):
    __tablename__ = "subsystems"
    id: Mapped[str] = pk()
    chamber_id: Mapped[str] = ref("chambers")
    name: Mapped[str] = mapped_column(String(120))


class Assembly(Base):
    __tablename__ = "assemblies"
    id: Mapped[str] = pk()
    subsystem_id: Mapped[str] = ref("subsystems")
    name: Mapped[str] = mapped_column(String(120))


class Position(Base):
    __tablename__ = "positions"
    id: Mapped[str] = pk()
    assembly_id: Mapped[str] = ref("assemblies")
    name: Mapped[str] = mapped_column(String(120))
    exposure_source: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(
        Text, default="Configurable conceptual slot; geometry not OEM verified"
    )


class ComponentDefinition(Base):
    __tablename__ = "component_definitions"
    id: Mapped[str] = pk()
    manufacturer: Mapped[str] = mapped_column(String(160))
    part_number: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(100))
    function: Mapped[str] = mapped_column(Text)
    revision: Mapped[str] = mapped_column(String(40))
    exposure_dimension: Mapped[str] = mapped_column(String(80))
    failure_mechanisms: Mapped[list] = mapped_column(JSON, default=list)
    supersedes_id: Mapped[str | None] = ref("component_definitions", True)


class Compatibility(Base):
    __tablename__ = "component_compatibility"
    id: Mapped[str] = pk()
    definition_id: Mapped[str] = ref("component_definitions")
    configuration_id: Mapped[str] = ref("equipment_configurations")
    effective_from: Mapped[datetime] = stamp()
    effective_to: Mapped[datetime | None] = mapped_column(UTCDateTime())
    verification: Mapped[str] = mapped_column(String(80))


class ComponentInstance(Base):
    __tablename__ = "component_instances"
    id: Mapped[str] = pk()
    definition_id: Mapped[str] = ref("component_definitions")
    serial_number: Mapped[str] = mapped_column(String(120), unique=True)
    lot: Mapped[str | None] = mapped_column(String(80))
    supplier: Mapped[str] = mapped_column(String(120))
    revision: Mapped[str] = mapped_column(String(40))
    disposition: Mapped[str] = mapped_column(String(80))
    repair_cycle: Mapped[int] = mapped_column(Integer, default=0)
    refurbishment_status: Mapped[str] = mapped_column(String(80))
    traceability_status: Mapped[str] = mapped_column(String(80))
    manufactured_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class RawSourceRecord(Base):
    __tablename__ = "raw_source_records"
    id: Mapped[str] = pk()
    source: Mapped[str] = mapped_column(String(120), index=True)
    source_id: Mapped[str] = mapped_column(String(160), index=True)
    recorded_at: Mapped[datetime] = stamp()
    effective_at: Mapped[datetime] = stamp()
    ingested_at: Mapped[datetime] = stamp()
    payload: Mapped[dict] = mapped_column(JSON)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    quality: Mapped[str] = mapped_column(String(80))
    verification: Mapped[str] = mapped_column(String(80))


class Installation(Base):
    __tablename__ = "installations"
    id: Mapped[str] = pk()
    component_id: Mapped[str] = ref("component_instances")
    position_id: Mapped[str] = ref("positions")
    installed_at: Mapped[datetime] = stamp()
    removed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    reason: Mapped[str] = mapped_column(Text)
    removal_reason: Mapped[str | None] = mapped_column(Text)
    maintenance_reference: Mapped[str | None] = mapped_column(String(100))
    source_record_id: Mapped[str] = ref("raw_source_records")
    __table_args__ = (
        CheckConstraint(
            "removed_at IS NULL OR removed_at > installed_at", name="ck_install_time"
        ),
        Index(
            "uq_component_active",
            "component_id",
            unique=True,
            sqlite_where=removed_at.is_(None),
            postgresql_where=removed_at.is_(None),
        ),
        Index(
            "uq_position_active",
            "position_id",
            unique=True,
            sqlite_where=removed_at.is_(None),
            postgresql_where=removed_at.is_(None),
        ),
    )


class Specification(Base):
    __tablename__ = "specifications"
    id: Mapped[str] = pk()
    definition_id: Mapped[str] = ref("component_definitions")
    parameter: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str | None] = mapped_column(String(40))
    nominal: Mapped[float | None] = mapped_column(Float)
    minimum: Mapped[float | None] = mapped_column(Float)
    maximum: Mapped[float | None] = mapped_column(Float)
    part_revision: Mapped[str] = mapped_column(String(40))
    configuration_id: Mapped[str] = ref("equipment_configurations")
    source_document: Mapped[str] = mapped_column(Text)
    document_revision: Mapped[str] = mapped_column(String(40))
    effective_from: Mapped[datetime] = stamp()
    verification: Mapped[str] = mapped_column(String(80))


class Refurbishment(Base):
    __tablename__ = "refurbishments"
    id: Mapped[str] = pk()
    component_id: Mapped[str] = ref("component_instances")
    completed_at: Mapped[datetime] = stamp()
    qualified: Mapped[bool] = mapped_column(Boolean)
    findings: Mapped[str] = mapped_column(Text)
    source_record_id: Mapped[str] = ref("raw_source_records")


class ExposureInterval(Base):
    __tablename__ = "exposure_intervals"
    id: Mapped[str] = pk()
    chamber_id: Mapped[str] = ref("chambers")
    source: Mapped[str] = mapped_column(String(120))
    dimension: Mapped[str] = mapped_column(String(80))
    start: Mapped[datetime] = stamp()
    end: Mapped[datetime] = stamp()
    quality: Mapped[str] = mapped_column(String(80))
    source_record_id: Mapped[str] = ref("raw_source_records")
    value: Mapped[float | None] = mapped_column(Float)
    __table_args__ = (CheckConstraint('"end" > "start"', name="ck_exposure_interval"),)


class ObservationCoverage(Base):
    __tablename__ = "observation_coverage"
    id: Mapped[str] = pk()
    chamber_id: Mapped[str] = ref("chambers")
    source: Mapped[str] = mapped_column(String(120))
    start: Mapped[datetime] = stamp()
    end: Mapped[datetime] = stamp()
    source_record_id: Mapped[str] = ref("raw_source_records")


class CounterSample(Base):
    __tablename__ = "counter_samples"
    id: Mapped[str] = pk()
    chamber_id: Mapped[str] = ref("chambers")
    source: Mapped[str] = mapped_column(String(120))
    dimension: Mapped[str] = mapped_column(String(80))
    timestamp: Mapped[datetime] = stamp()
    value: Mapped[float] = mapped_column(Float)
    modulus: Mapped[float | None] = mapped_column(Float)
    source_record_id: Mapped[str] = ref("raw_source_records")


class PMPlan(Base):
    __tablename__ = "pm_plans"
    id: Mapped[str] = pk()
    definition_id: Mapped[str] = ref("component_definitions")
    dimension: Mapped[str] = mapped_column(String(80))
    threshold: Mapped[float | None] = mapped_column(Float)
    calendar_days: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(40))
    basis: Mapped[str] = mapped_column(String(120))
    source_document: Mapped[str] = mapped_column(Text)
    effective_from: Mapped[datetime] = stamp()
    effective_to: Mapped[datetime | None] = mapped_column(UTCDateTime())
    verification: Mapped[str] = mapped_column(String(80))


class PMDueEvent(Base):
    __tablename__ = "pm_due_events"
    id: Mapped[str] = pk()
    plan_id: Mapped[str] = ref("pm_plans")
    component_id: Mapped[str] = ref("component_instances")
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(40))
    completed_work_order_id: Mapped[str | None] = ref("work_orders", True)


class WorkOrder(Base):
    __tablename__ = "work_orders"
    id: Mapped[str] = pk()
    chamber_id: Mapped[str] = ref("chambers")
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(80))
    opened_at: Mapped[datetime] = stamp()
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    source_record_id: Mapped[str] = ref("raw_source_records")


class MaintenanceAction(Base):
    __tablename__ = "maintenance_actions"
    id: Mapped[str] = pk()
    work_order_id: Mapped[str] = ref("work_orders")
    component_id: Mapped[str] = ref("component_instances")
    timestamp: Mapped[datetime] = stamp()
    action: Mapped[str] = mapped_column(String(120))
    findings: Mapped[str] = mapped_column(Text)
    confirmed_failure: Mapped[bool] = mapped_column(Boolean, default=False)


class ReplacementEvent(Base):
    __tablename__ = "replacement_events"
    id: Mapped[str] = pk()
    old_component_id: Mapped[str] = ref("component_instances")
    new_component_id: Mapped[str] = ref("component_instances")
    work_order_id: Mapped[str] = ref("work_orders")
    timestamp: Mapped[datetime] = stamp()
    reason: Mapped[str] = mapped_column(Text)


class FailureMode(Base):
    __tablename__ = "failure_modes"
    id: Mapped[str] = pk()
    name: Mapped[str] = mapped_column(String(120))
    mechanism: Mapped[str] = mapped_column(Text)


class FailureEpisode(Base):
    __tablename__ = "failure_episodes"
    id: Mapped[str] = pk()
    chamber_id: Mapped[str] = ref("chambers")
    component_id: Mapped[str | None] = ref("component_instances", True)
    failure_mode_id: Mapped[str | None] = ref("failure_modes", True)
    title: Mapped[str] = mapped_column(String(200))
    started_at: Mapped[datetime] = stamp()
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(80))
    attribution_status: Mapped[str] = mapped_column(String(80))
    root_cause: Mapped[str] = mapped_column(Text)
    hypotheses: Mapped[list] = mapped_column(JSON)
    review_status: Mapped[str] = mapped_column(String(80))
    deduplication_key: Mapped[str] = mapped_column(String(160), unique=True)


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = pk()
    failure_id: Mapped[str] = ref("failure_episodes")
    timestamp: Mapped[datetime] = stamp()
    kind: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text)
    quality: Mapped[str] = mapped_column(String(80))
    source_record_id: Mapped[str] = ref("raw_source_records")


class EquipmentEvent(Base):
    __tablename__ = "equipment_events"
    id: Mapped[str] = pk()
    chamber_id: Mapped[str] = ref("chambers")
    failure_id: Mapped[str | None] = ref("failure_episodes", True)
    asserted_at: Mapped[datetime] = stamp()
    cleared_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    label: Mapped[str] = mapped_column(String(200))
    synthetic_code: Mapped[str] = mapped_column(String(80))
    symptom_role: Mapped[str] = mapped_column(String(80))
    source_record_id: Mapped[str] = ref("raw_source_records")


class FDCPoint(Base):
    __tablename__ = "fdc_points"
    id: Mapped[str] = pk()
    chamber_id: Mapped[str] = ref("chambers")
    component_id: Mapped[str] = ref("component_instances")
    timestamp: Mapped[datetime] = stamp()
    signal: Mapped[str] = mapped_column(String(120))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(80))
    cohort: Mapped[str] = mapped_column(String(80))
    source_record_id: Mapped[str] = ref("raw_source_records")


class DowntimeInterval(Base):
    __tablename__ = "downtime_intervals"
    id: Mapped[str] = pk()
    failure_id: Mapped[str | None] = ref("failure_episodes", True)
    chamber_id: Mapped[str] = ref("chambers")
    start: Mapped[datetime] = stamp()
    end: Mapped[datetime] = stamp()
    category: Mapped[str] = mapped_column(String(80))
    classification: Mapped[str] = mapped_column(String(120))
    critical_path_hours: Mapped[float | None] = mapped_column(Float)
    source_record_id: Mapped[str] = ref("raw_source_records")
    __table_args__ = (CheckConstraint('"end" > "start"', name="ck_downtime_time"),)


class DowntimeAttribution(Base):
    __tablename__ = "downtime_attributions"
    id: Mapped[str] = pk()
    downtime_id: Mapped[str] = ref("downtime_intervals")
    component_id: Mapped[str] = ref("component_instances")
    weight: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(80))
    rationale: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint("weight >= 0 AND weight <= 1", name="ck_attribution_weight"),
        UniqueConstraint("downtime_id", "component_id"),
    )


class CommissioningMilestone(Base):
    __tablename__ = "commissioning_milestones"
    id: Mapped[str] = pk()
    tool_id: Mapped[str] = ref("tools")
    name: Mapped[str] = mapped_column(String(160))
    planned_at: Mapped[datetime] = stamp()
    actual_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    failure_id: Mapped[str | None] = ref("failure_episodes", True)
    critical_path_established: Mapped[bool] = mapped_column(Boolean, default=False)


class CorrectiveAction(Base):
    __tablename__ = "corrective_actions"
    id: Mapped[str] = pk()
    failure_id: Mapped[str] = ref("failure_episodes")
    proposal: Mapped[str] = mapped_column(Text)
    validation_status: Mapped[str] = mapped_column(String(80))
    owner: Mapped[str] = mapped_column(String(120))


class SourceConflict(Base):
    __tablename__ = "source_conflicts"
    id: Mapped[str] = pk()
    component_id: Mapped[str | None] = ref("component_instances", True)
    field: Mapped[str] = mapped_column(String(120))
    record_a_id: Mapped[str] = ref("raw_source_records")
    record_b_id: Mapped[str] = ref("raw_source_records")
    value_a: Mapped[str] = mapped_column(Text)
    value_b: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(80))
    decision: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = pk()
    timestamp: Mapped[datetime] = stamp()
    actor: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(120))
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(120))
    detail: Mapped[dict] = mapped_column(JSON)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    id: Mapped[str] = pk()
    adapter_id: Mapped[str] = mapped_column(String(120))
    started_at: Mapped[datetime] = stamp()
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(80))
    record_count: Mapped[int] = mapped_column(Integer)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON)
    cursor: Mapped[str | None] = mapped_column(Text)


class IngestionOriginal(Base):
    __tablename__ = "ingestion_originals"
    id: Mapped[str] = pk()
    run_id: Mapped[str] = ref("ingestion_runs")
    source: Mapped[str] = mapped_column(String(120))
    ingested_at: Mapped[datetime] = stamp()
    original_json: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64))
    row: Mapped[int] = mapped_column(Integer)
