"""Versioned provenance, review, identity and durable ingestion records."""

from datetime import datetime
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base, UTCDateTime, pk, ref, stamp


class EnterpriseSource(Base):
    __tablename__ = "enterprise_sources"
    id: Mapped[str] = pk()
    name: Mapped[str] = mapped_column(String(160))
    connector_kind: Mapped[str] = mapped_column(String(120))
    classification: Mapped[str] = mapped_column(String(80), default="synthetic")
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    authorized_equipment: Mapped[list] = mapped_column(JSON, default=list)
    authorized_collections: Mapped[list] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    polling_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=3600)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    __table_args__ = (
        CheckConstraint("interval_seconds >= 60", name="ck_source_poll_interval"),
    )


class SourceVersion(Base):
    __tablename__ = "source_versions"
    id: Mapped[str] = pk()
    source_id: Mapped[str] = ref("enterprise_sources")
    raw_record_id: Mapped[str] = ref("raw_source_records")
    original_id: Mapped[str] = mapped_column(String(200))
    revision: Mapped[str] = mapped_column(String(80))
    content_hash: Mapped[str] = mapped_column(String(64))
    mime_type: Mapped[str] = mapped_column(String(120))
    content_b64: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(240))
    equipment_alias: Mapped[str] = mapped_column(String(160))
    collection: Mapped[str] = mapped_column(String(160))
    recorded_at: Mapped[datetime] = stamp()
    effective_at: Mapped[datetime] = stamp()
    ingested_at: Mapped[datetime] = stamp()
    parser_version: Mapped[str] = mapped_column(String(120))
    parse_status: Mapped[str] = mapped_column(String(80))
    structured_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "original_id",
            "revision",
            "content_hash",
            name="uq_source_content_version",
        ),
    )


class FactProposal(Base):
    __tablename__ = "fact_proposals"
    id: Mapped[str] = pk()
    source_version_id: Mapped[str] = ref("source_versions")
    kind: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    extraction_method: Mapped[str] = mapped_column(String(120))
    extraction_version: Mapped[str] = mapped_column(String(120))
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(80), default="pending")
    match_status: Mapped[str] = mapped_column(String(80), default="unresolved")
    matched_entities: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_errors: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = stamp()
    proposal_hash: Mapped[str] = mapped_column(String(64))
    supersedes_id: Mapped[str | None] = ref("fact_proposals", True)
    __table_args__ = (
        UniqueConstraint(
            "source_version_id",
            "extraction_version",
            "proposal_hash",
            name="uq_extracted_fact",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_proposal_confidence"
        ),
    )


class EntityAlias(Base):
    __tablename__ = "entity_aliases"
    id: Mapped[str] = pk()
    source_id: Mapped[str] = ref("enterprise_sources")
    entity_type: Mapped[str] = mapped_column(String(80))
    external_id: Mapped[str] = mapped_column(String(200))
    canonical_id: Mapped[str] = mapped_column(String(80))
    valid_from: Mapped[datetime] = stamp()
    valid_to: Mapped[datetime | None] = mapped_column(UTCDateTime())
    verification_status: Mapped[str] = mapped_column(String(80))
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    __table_args__ = (
        CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_alias_effective_interval",
        ),
        UniqueConstraint(
            "source_id",
            "entity_type",
            "external_id",
            "valid_from",
            name="uq_alias_effective_start",
        ),
        Index(
            "uq_alias_current",
            "source_id",
            "entity_type",
            "external_id",
            unique=True,
            sqlite_where=valid_to.is_(None),
            postgresql_where=valid_to.is_(None),
        ),
    )


class EngineeringReview(Base):
    __tablename__ = "engineering_reviews"
    id: Mapped[str] = pk()
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(80), index=True)
    actor: Mapped[str] = mapped_column(String(160))
    decision: Mapped[str] = mapped_column(String(80))
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = stamp()
    before_after: Mapped[dict] = mapped_column(JSON)


class SyncJob(Base):
    __tablename__ = "sync_jobs"
    id: Mapped[str] = pk()
    source_id: Mapped[str] = ref("enterprise_sources")
    kind: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(80), index=True)
    cursor: Mapped[str | None] = mapped_column(Text)
    window_start: Mapped[datetime | None] = mapped_column(UTCDateTime())
    window_end: Mapped[datetime | None] = mapped_column(UTCDateTime())
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = stamp()
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    error: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    requested_by: Mapped[str] = mapped_column(String(160))
    query: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        CheckConstraint("attempts >= 0 AND max_attempts > 0", name="ck_job_attempts"),
        CheckConstraint(
            "window_end IS NULL OR window_start IS NULL OR window_end > window_start",
            name="ck_job_window",
        ),
    )


class SyncCheckpoint(Base):
    __tablename__ = "sync_checkpoints"
    id: Mapped[str] = pk()
    source_id: Mapped[str] = ref("enterprise_sources")
    stream: Mapped[str] = mapped_column(String(120))
    cursor: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = stamp()
    job_id: Mapped[str] = ref("sync_jobs")
    __table_args__ = (
        UniqueConstraint("source_id", "stream", name="uq_source_stream_checkpoint"),
    )


class DeadLetter(Base):
    __tablename__ = "dead_letters"
    id: Mapped[str] = pk()
    job_id: Mapped[str] = ref("sync_jobs")
    source_version_id: Mapped[str | None] = ref("source_versions", True)
    stage: Mapped[str] = mapped_column(String(80))
    error_code: Mapped[str] = mapped_column(String(120))
    error_detail: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = stamp()
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class SensorChannel(Base):
    __tablename__ = "sensor_channels"
    id: Mapped[str] = pk()
    source_id: Mapped[str] = ref("enterprise_sources")
    tool_id: Mapped[str] = ref("tools")
    chamber_id: Mapped[str] = ref("chambers")
    subsystem: Mapped[str | None] = mapped_column(String(120))
    channel_key: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    signal_type: Mapped[str] = mapped_column(String(80))
    unit: Mapped[str | None] = mapped_column(String(80))
    sampling_hz: Mapped[float | None] = mapped_column(Float)
    valid_min: Mapped[float | None] = mapped_column(Float)
    valid_max: Mapped[float | None] = mapped_column(Float)
    configuration_id: Mapped[str] = ref("equipment_configurations")
    effective_from: Mapped[datetime] = stamp()
    effective_to: Mapped[datetime | None] = mapped_column(UTCDateTime())
    document_reference: Mapped[str | None] = mapped_column(Text)
    verification: Mapped[str] = mapped_column(String(80), default="proposed")
    quality: Mapped[str] = mapped_column(String(80), default="unverified")
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "channel_key",
            "chamber_id",
            "effective_from",
            name="uq_sensor_effective_key",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_sensor_effective_interval",
        ),
    )


class ComponentSensorMapping(Base):
    __tablename__ = "component_sensor_mappings"
    id: Mapped[str] = pk()
    definition_id: Mapped[str] = ref("component_definitions")
    sensor_id: Mapped[str] = ref("sensor_channels")
    relationship: Mapped[str] = mapped_column(String(80))
    physical_explanation: Mapped[str] = mapped_column(Text)
    configuration_id: Mapped[str] = ref("equipment_configurations")
    chamber_id: Mapped[str | None] = ref("chambers", True)
    part_revision: Mapped[str | None] = mapped_column(String(40))
    effective_from: Mapped[datetime] = stamp()
    effective_to: Mapped[datetime | None] = mapped_column(UTCDateTime())
    verification: Mapped[str] = mapped_column(String(80), default="proposed")
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float | None] = mapped_column(Float)
    proposed_by: Mapped[str] = mapped_column(String(160))
    approved_by: Mapped[str | None] = mapped_column(String(160))
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    __table_args__ = (
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_mapping_effective_interval",
        ),
    )


class ExposureDefinition(Base):
    __tablename__ = "exposure_definitions"
    id: Mapped[str] = pk()
    definition_id: Mapped[str] = ref("component_definitions")
    source_id: Mapped[str] = ref("enterprise_sources")
    sensor_id: Mapped[str] = ref("sensor_channels")
    configuration_id: Mapped[str] = ref("equipment_configurations")
    chamber_id: Mapped[str | None] = ref("chambers", True)
    part_revision: Mapped[str | None] = mapped_column(String(40))
    dimension: Mapped[str] = mapped_column(String(80))
    method: Mapped[str] = mapped_column(String(80))
    source_name: Mapped[str] = mapped_column(String(120))
    active_value: Mapped[str | None] = mapped_column(String(80))
    inactive_value: Mapped[str | None] = mapped_column(String(80))
    max_gap_seconds: Mapped[float] = mapped_column(Float, default=3600)
    rollover: Mapped[float | None] = mapped_column(Float)
    max_rate: Mapped[float | None] = mapped_column(Float)
    aggregation: Mapped[str] = mapped_column(String(80), default="union")
    effective_from: Mapped[datetime] = stamp()
    effective_to: Mapped[datetime | None] = mapped_column(UTCDateTime())
    verification: Mapped[str] = mapped_column(String(80), default="proposed")
    document_reference: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(String(160))
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    __table_args__ = (
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_rule_effective_interval",
        ),
        CheckConstraint("max_gap_seconds > 0", name="ck_rule_max_gap"),
    )


class SensorSample(Base):
    __tablename__ = "sensor_samples"
    id: Mapped[str] = pk()
    sensor_id: Mapped[str] = ref("sensor_channels")
    source_version_id: Mapped[str] = ref("source_versions")
    timestamp: Mapped[datetime] = stamp()
    end_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    value: Mapped[float | None] = mapped_column(Float)
    state: Mapped[str | None] = mapped_column(String(80))
    reset: Mapped[bool] = mapped_column(Boolean, default=False)
    reset_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    reset_baseline: Mapped[float | None] = mapped_column(Float)
    quality: Mapped[str] = mapped_column(String(80))
    source_location: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint(
            "sensor_id",
            "source_version_id",
            "timestamp",
            "end_at",
            name="uq_sensor_sample_version_time",
        ),
        CheckConstraint("end_at IS NULL OR end_at > timestamp", name="ck_sample_time"),
    )


class CalculationLineage(Base):
    __tablename__ = "calculation_lineage"
    id: Mapped[str] = pk()
    component_id: Mapped[str] = ref("component_instances")
    rule_id: Mapped[str] = ref("exposure_definitions")
    source_version_ids: Mapped[list] = mapped_column(JSON)
    derived_intervals: Mapped[list] = mapped_column(JSON)
    method_version: Mapped[str] = mapped_column(String(120))
    start: Mapped[datetime] = stamp()
    end: Mapped[datetime] = stamp()
    input_hash: Mapped[str] = mapped_column(String(64), unique=True)
    issues: Mapped[list] = mapped_column(JSON, default=list)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = stamp()
    __table_args__ = (CheckConstraint('"end" >= "start"', name="ck_lineage_window"),)


class EquipmentConfigurationPeriod(Base):
    __tablename__ = "equipment_configuration_periods"
    id: Mapped[str] = pk()
    tool_id: Mapped[str] = ref("tools")
    configuration_id: Mapped[str] = ref("equipment_configurations")
    effective_from: Mapped[datetime] = stamp()
    effective_to: Mapped[datetime | None] = mapped_column(UTCDateTime())
    verification: Mapped[str] = mapped_column(String(80))
    source_record_id: Mapped[str | None] = ref("raw_source_records", True)
    __table_args__ = (
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_configuration_period",
        ),
        UniqueConstraint(
            "tool_id", "effective_from", name="uq_tool_configuration_start"
        ),
    )
