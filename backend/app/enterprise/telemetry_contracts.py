"""Public, synthetic-first sensor and exposure contracts.

These describe canonical engineering concepts, never proprietary channel names.
All applicability and state timestamps require an explicit timezone.
"""
from __future__ import annotations

from typing import Any, Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Relationship = Literal["direct_measurement", "upstream_influence", "downstream_effect", "supporting_diagnostic", "shared_utility", "exposure_counter"]
SignalType = Literal["measured", "state", "counter", "validated_interval"]
ExposureMethod = Literal["state", "counter", "validated_interval"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class EffectiveContract(Contract):
    effective_from: AwareDatetime
    effective_to: AwareDatetime | None = None

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must follow effective_from")
        return self


class SensorInput(EffectiveContract):
    record_type: Literal["sensor"] = "sensor"
    channel_key: str = Field(min_length=1, max_length=160)
    tool_id: str = Field(min_length=1, max_length=80)
    chamber_id: str = Field(min_length=1, max_length=80)
    subsystem: str | None = Field(default=None, max_length=120)
    description: str = Field(min_length=5, max_length=2000)
    signal_type: SignalType
    unit: str | None = Field(default=None, max_length=40)
    sampling_hz: float | None = Field(default=None, gt=0)
    valid_min: float | None = None
    valid_max: float | None = None
    configuration_id: str = Field(min_length=1, max_length=80)
    document_reference: str | None = Field(default=None, max_length=2000)
    verification: Literal["synthetic_only", "pending_verification"] = "pending_verification"
    quality: str = Field(default="unknown", max_length=80)

    @model_validator(mode="after")
    def verified_ranges(self):
        if self.valid_min is not None and self.valid_max is not None and self.valid_min > self.valid_max:
            raise ValueError("Documented sensor range is reversed")
        if (self.valid_min is not None or self.valid_max is not None) and not self.document_reference:
            raise ValueError("A documented range requires its source reference")
        return self


class SampleInput(Contract):
    record_type: Literal["sample"] = "sample"
    channel_key: str = Field(min_length=1, max_length=160)
    chamber_id: str = Field(min_length=1, max_length=80)
    timestamp: AwareDatetime
    end_at: AwareDatetime | None = None
    value: float | None = None
    state: str | None = Field(default=None, max_length=80)
    quality: Literal["good", "verified", "synthetic", "bad", "missing", "conflict"] = "synthetic"
    reset: bool = False
    reset_at: AwareDatetime | None = None
    reset_baseline: float | None = Field(default=None, ge=0)
    source_location: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_value(self):
        if self.value is None and self.state is None:
            raise ValueError("A sample requires a measured value or state")
        if self.end_at is not None and self.end_at <= self.timestamp:
            raise ValueError("An interval sample must have positive duration")
        if self.reset_at is not None and self.reset_at > self.timestamp:
            raise ValueError("Reset timestamp cannot follow its sample")
        return self


class MappingInput(EffectiveContract):
    definition_id: str = Field(min_length=1, max_length=80)
    sensor_id: str = Field(min_length=1, max_length=80)
    relationship: Relationship
    physical_explanation: str = Field(min_length=10, max_length=4000)
    configuration_id: str = Field(min_length=1, max_length=80)
    chamber_id: str | None = Field(default=None, max_length=80)
    part_revision: str | None = Field(default=None, max_length=40)
    evidence: list[dict[str, Any]] = Field(min_length=1, max_length=50)
    confidence: float | None = Field(default=None, ge=0, le=1)
    method: Literal["engineer_proposal", "internal_ai_proposal"] = "engineer_proposal"


class ExposureRuleInput(EffectiveContract):
    definition_id: str = Field(min_length=1, max_length=80)
    sensor_id: str = Field(min_length=1, max_length=80)
    configuration_id: str = Field(min_length=1, max_length=80)
    chamber_id: str | None = Field(default=None, max_length=80)
    part_revision: str | None = Field(default=None, max_length=40)
    dimension: str = Field(min_length=1, max_length=80)
    source_name: str = Field(min_length=1, max_length=120)
    method: ExposureMethod
    active_value: str | None = Field(default=None, max_length=80)
    inactive_value: str | None = Field(default=None, max_length=80)
    max_gap_seconds: float = Field(gt=0, le=604800)
    rollover: float | None = Field(default=None, gt=0)
    max_rate: float = Field(default=1, gt=0)
    aggregation: Literal["union"] = "union"
    document_reference: str = Field(min_length=5, max_length=2000)

    @model_validator(mode="after")
    def state_definition(self):
        if self.method == "state" and (self.active_value is None or self.inactive_value is None or self.active_value == self.inactive_value):
            raise ValueError("State exposure requires distinct explicitly approved active and inactive values")
        return self


class EngineeringReview(Contract):
    decision: Literal["approve", "reject"]
    note: str = Field(min_length=10, max_length=4000)


class TelemetryQuery(Contract):
    start: AwareDatetime
    end: AwareDatetime
    state: str | None = Field(default=None, max_length=80)
    max_points: int = Field(default=1000, ge=10, le=1000)

    @model_validator(mode="after")
    def bounded(self):
        duration = (self.end - self.start).total_seconds()
        if duration <= 0 or duration > 31 * 86400:
            raise ValueError("Telemetry query must be positive and at most 31 days")
        return self
