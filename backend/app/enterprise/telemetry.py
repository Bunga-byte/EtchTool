"""Approved component/sensor relationships and auditable exposure projections.

Imported telemetry stays versioned and inert until an engineer approves both an
applicable sensor mapping and exposure definition. Derived records are a cache;
the source versions and method hash remain the evidence of every calculation.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from typing import Any, Mapping, Protocol, Sequence
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.auth import Principal
from app.models import (Assembly, AuditLog, Chamber, ComponentDefinition, ComponentInstance, CounterSample, EquipmentConfiguration, EquipmentEvent, ExposureInterval, Installation, ObservationCoverage, Position, RawSourceRecord, Subsystem, Tool)
from app.services.exposure import calculate_exposure, counter_intervals, merge_intervals, timestamp, union_hours
from .models import (CalculationLineage, ComponentSensorMapping, EngineeringReview, EnterpriseSource, EntityAlias, EquipmentConfigurationPeriod, ExposureDefinition, SensorChannel, SensorSample, SourceVersion)
from .telemetry_contracts import ExposureRuleInput, MappingInput, SampleInput, SensorInput, TelemetryQuery
from .security import authorize_source

METHOD_VERSION = "approved-component-exposure-v2"
GOOD = {"good", "verified", "synthetic", "complete"}
APPROVED = {"approved", "synthetic_approved"}
MAX_BATCH_RECORDS = 50000


class BoundedTelemetryConnector(Protocol):
    """Implement inside the approved network; unlimited queries are unsupported."""

    def query_samples(self, *, channel_keys: Sequence[str], start: datetime, end: datetime, limit: int, cursor: str | None = None) -> Mapping[str, Any]: ...


def _hash(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def seed_telemetry(session: Session) -> bool:
    """Registry proposals are populated by the synthetic file connector on import.

    Seeding source configuration alone must not fabricate a sensor mapping or
    change canonical RF hours before an engineer reviews actual source evidence.
    """
    return False


def _audit(session: Session, actor: Principal, action: str, kind: str, id: str, detail: dict[str, Any]):
    session.add(AuditLog(id=str(uuid4()), timestamp=_now(), actor=actor.subject, role=actor.role, action=action, entity_type=kind, entity_id=id, detail=detail))


def source_allowed(session: Session, actor: Principal, source: EnterpriseSource, *, write: bool = False, sensor: SensorChannel | None = None, at: datetime | None = None) -> bool:
    try:
        when = at or (sensor.effective_from if sensor else _now())
        scope = authorize_source(session, actor, source, write=write, collection="telemetry", at=when)
        if sensor:
            aliases: dict[str, set[str]] = {}
            for alias in session.scalars(select(EntityAlias).where(EntityAlias.source_id == source.id, EntityAlias.entity_type == "tool", EntityAlias.external_id.in_(scope.equipment_aliases), EntityAlias.verification_status == "verified", EntityAlias.valid_from <= when, (EntityAlias.valid_to.is_(None)) | (EntityAlias.valid_to > when))):
                aliases.setdefault(alias.external_id, set()).add(alias.canonical_id)
            canonical = {next(iter(values)) for values in aliases.values() if len(values) == 1}
            if sensor.tool_id not in canonical:
                return False
        return True
    except HTTPException:
        return False


def _location(session: Session, install: Installation):
    position = session.get(Position, install.position_id)
    assembly = session.get(Assembly, position.assembly_id)
    subsystem = session.get(Subsystem, assembly.subsystem_id)
    chamber = session.get(Chamber, subsystem.chamber_id)
    tool = session.get(Tool, chamber.tool_id)
    return position, chamber, tool


def _between(start: datetime, end: datetime, *effective: Any) -> tuple[datetime, datetime] | None:
    for record in effective:
        start = max(start, record.effective_from)
        if record.effective_to:
            end = min(end, record.effective_to)
    return (start, end) if start < end else None


def _configuration_segments(periods: Sequence[EquipmentConfigurationPeriod], expected: str, start: datetime, end: datetime) -> list[tuple[datetime, datetime, bool]]:
    """A configured rule cannot resolve contradictory actual equipment history."""
    boundaries = {start, end}
    for period in periods:
        if start < period.effective_from < end:
            boundaries.add(period.effective_from)
        if period.effective_to and start < period.effective_to < end:
            boundaries.add(period.effective_to)
    ordered = sorted(boundaries)
    result = []
    for begins, ends in zip(ordered, ordered[1:]):
        actual = {p.configuration_id for p in periods if p.effective_from < ends and (p.effective_to is None or p.effective_to > begins)}
        if expected in actual:
            result.append((begins, ends, len(actual) != 1))
    return result


def _sensor(session: Session, source_id: str, key: str, chamber_id: str, at: datetime) -> SensorChannel | None:
    options = session.scalars(select(SensorChannel).where(SensorChannel.source_id == source_id, SensorChannel.channel_key == key, SensorChannel.chamber_id == chamber_id, SensorChannel.effective_from <= at, (SensorChannel.effective_to.is_(None)) | (SensorChannel.effective_to > at))).all()
    if len(options) > 1:
        raise ValueError("Overlapping channel registry revisions require reconciliation")
    return options[0] if options else None


def create_mapping(session: Session, request: MappingInput, actor: Principal) -> ComponentSensorMapping:
    sensor = session.get(SensorChannel, request.sensor_id)
    definition = session.get(ComponentDefinition, request.definition_id)
    if sensor is None or definition is None:
        raise ValueError("Mapping must identify existing sensor and component definition")
    source = session.get(EnterpriseSource, sensor.source_id)
    if not source_allowed(session, actor, source, write=True, sensor=sensor, at=request.effective_from):
        raise PermissionError("Mapping proposal is outside engineering source scope")
    if request.configuration_id != sensor.configuration_id or (request.chamber_id and request.chamber_id != sensor.chamber_id):
        raise ValueError("Mapping applicability disagrees with sensor registry")
    body = request.model_dump(exclude={"method"})
    id = "map-" + _hash({"body": request.model_dump(mode="json"), "actor": actor.subject})[:40]
    existing = session.get(ComponentSensorMapping, id)
    if existing:
        return existing
    mapping = ComponentSensorMapping(id=id, **body, verification="proposed", proposed_by=("internal_ai:" if request.method == "internal_ai_proposal" else "") + actor.subject)
    session.add(mapping)
    _audit(session, actor, "sensor_mapping.proposed", "sensor_mapping", id, {"method": request.method, "requires_engineering_approval": True})
    session.flush()
    return mapping


def create_rule(session: Session, request: ExposureRuleInput, actor: Principal) -> ExposureDefinition:
    sensor = session.get(SensorChannel, request.sensor_id)
    definition = session.get(ComponentDefinition, request.definition_id)
    if sensor is None or definition is None:
        raise ValueError("Exposure rule needs an existing channel and component definition")
    source = session.get(EnterpriseSource, sensor.source_id)
    if not source_allowed(session, actor, source, write=True, sensor=sensor, at=request.effective_from):
        raise PermissionError("Exposure proposal is outside engineering source scope")
    if request.configuration_id != sensor.configuration_id or (request.chamber_id and request.chamber_id != sensor.chamber_id):
        raise ValueError("Rule applicability disagrees with sensor registry")
    if request.method != sensor.signal_type or request.dimension != definition.exposure_dimension:
        raise ValueError("Rule method or exposure dimension disagrees with physical definition")
    if request.method == "counter" and request.dimension.endswith("hours") and sensor.unit not in {"RF h", "powered h", "operating h", "h", "hours", "rf_hours", "powered_hours", "operating_hours"}:
        raise ValueError("Hour counter units must be documented hours; transform source units explicitly before import")
    id = "rule-" + _hash(request.model_dump(mode="json"))[:40]
    existing = session.get(ExposureDefinition, id)
    if existing:
        return existing
    rule = ExposureDefinition(id=id, source_id=sensor.source_id, **request.model_dump(), verification="proposed")
    session.add(rule)
    _audit(session, actor, "exposure_rule.proposed", "exposure_rule", id, {"requires_engineering_approval": True})
    session.flush()
    return rule


def review_mapping(session: Session, mapping: ComponentSensorMapping, decision: str, note: str, actor: Principal):
    if decision not in {"approve", "reject"}:
        raise ValueError("Engineering review decision must be approve or reject")
    sensor = session.get(SensorChannel, mapping.sensor_id)
    if not source_allowed(session, actor, session.get(EnterpriseSource, sensor.source_id), write=True, sensor=sensor, at=mapping.effective_from):
        raise PermissionError("Engineering review is outside source permissions")
    if mapping.verification != "proposed":
        raise ValueError("Reviewed mappings are immutable; submit a new effective-dated proposal")
    if decision == "approve" and (mapping.configuration_id != sensor.configuration_id or (mapping.chamber_id and mapping.chamber_id != sensor.chamber_id)):
        raise ValueError("Mapping does not apply to the registered channel configuration")
    before = mapping.verification
    mapping.verification = "approved" if decision == "approve" else "rejected"
    mapping.approved_by = actor.subject if decision == "approve" else None
    mapping.approved_at = _now() if decision == "approve" else None
    session.add(EngineeringReview(id=str(uuid4()), entity_type="sensor_mapping", entity_id=mapping.id, actor=actor.subject, decision=decision, note=note, created_at=_now(), before_after={"before": before, "after": mapping.verification}))
    _audit(session, actor, "sensor_mapping.reviewed", "sensor_mapping", mapping.id, {"decision": decision, "note": note})
    session.flush()
    if decision == "approve":
        rebuild_exposure(session, sensor.source_id)


def review_rule(session: Session, rule: ExposureDefinition, decision: str, note: str, actor: Principal):
    if decision not in {"approve", "reject"}:
        raise ValueError("Engineering review decision must be approve or reject")
    sensor = session.get(SensorChannel, rule.sensor_id)
    if not source_allowed(session, actor, session.get(EnterpriseSource, rule.source_id), write=True, sensor=sensor, at=rule.effective_from):
        raise PermissionError("Engineering review is outside source permissions")
    if rule.verification != "proposed":
        raise ValueError("Reviewed exposure definitions are immutable; submit a new effective-dated proposal")
    if decision == "approve":
        mappings = session.scalars(select(ComponentSensorMapping).where(ComponentSensorMapping.sensor_id == rule.sensor_id, ComponentSensorMapping.definition_id == rule.definition_id, ComponentSensorMapping.verification.in_(APPROVED), ComponentSensorMapping.relationship == "exposure_counter")).all()
        if not any(m.configuration_id == rule.configuration_id and m.part_revision == rule.part_revision and m.chamber_id == rule.chamber_id and m.effective_from <= rule.effective_from and (m.effective_to is None or (rule.effective_to is not None and m.effective_to >= rule.effective_to)) for m in mappings):
            raise ValueError("Approve an applicable operating-exposure sensor mapping covering the rule first")
        if not rule.document_reference or rule.aggregation != "union":
            raise ValueError("Exposure requires a documented union rule; unrelated RF sources cannot be summed")
    before = rule.verification
    rule.verification = "approved" if decision == "approve" else "rejected"
    rule.approved_by = actor.subject if decision == "approve" else None
    rule.approved_at = _now() if decision == "approve" else None
    session.add(EngineeringReview(id=str(uuid4()), entity_type="exposure_rule", entity_id=rule.id, actor=actor.subject, decision=decision, note=note, created_at=_now(), before_after={"before": before, "after": rule.verification}))
    _audit(session, actor, "exposure_rule.reviewed", "exposure_rule", rule.id, {"decision": decision, "note": note})
    session.flush()
    if decision == "approve":
        rebuild_exposure(session, rule.source_id)


def ingest_telemetry(session: Session, source_version: SourceVersion, parsedrows: Sequence[Mapping[str, Any]] | Mapping[str, Any], actor: Principal) -> dict[str, Any]:
    """Import typed, bounded telemetry; proposals never approve themselves.

    A caller transaction owns commit/rollback. Every row references its immutable
    source version, so replay is idempotent and changed values remain visible.
    """
    source = session.get(EnterpriseSource, source_version.source_id)
    if source is None or not source_allowed(session, actor, source, write=True, at=source_version.effective_at):
        raise PermissionError("Telemetry source is outside authorized scope")
    authorize_source(session, actor, source, write=True, equipment_alias=source_version.equipment_alias, collection=source_version.collection, at=source_version.effective_at)
    rows = parsedrows.get("records", parsedrows.get("samples", [])) if isinstance(parsedrows, Mapping) else parsedrows
    if len(rows) > MAX_BATCH_RECORDS:
        raise ValueError("Telemetry batch exceeds 50,000 records; use bounded incremental batches")
    report: dict[str, Any] = {"sensors": 0, "samples": 0, "mappings": 0, "rules": 0, "duplicates": 0, "errors": [], "lineage": 0}
    # Registry rows precede samples independent of file order. Approval remains
    # separate even for machine-generated mapping/rule rows in a trusted batch.
    ordered = sorted(enumerate(rows), key=lambda item: {"sensor": 0, "sample": 1, "mapping": 2, "exposure_rule": 3}.get(item[1].get("record_type", "sample"), 9))
    for index, original in ordered:
        body = dict(original)
        kind = body.get("record_type", "sample")
        try:
            if kind == "sensor":
                data = SensorInput.model_validate(body)
                chamber = session.get(Chamber, data.chamber_id)
                tool = session.get(Tool, data.tool_id)
                if not chamber or not tool or chamber.tool_id != tool.id or not session.get(EquipmentConfiguration, data.configuration_id):
                    raise ValueError("Sensor tool and chamber are unresolved or incompatible")
                identity = set(session.scalars(select(EntityAlias.canonical_id).where(EntityAlias.source_id == source.id, EntityAlias.entity_type == "tool", EntityAlias.external_id == source_version.equipment_alias, EntityAlias.verification_status == "verified", EntityAlias.valid_from <= data.effective_from, (EntityAlias.valid_to.is_(None)) | (EntityAlias.valid_to > data.effective_from))))
                if identity != {data.tool_id}:
                    raise ValueError("Sensor equipment is outside connector scope")
                id = "sensor-" + _hash({"source": source.id, "channel": data.channel_key, "chamber": data.chamber_id, "from": data.effective_from})[:40]
                existing = session.get(SensorChannel, id)
                if existing:
                    actual = {k: getattr(existing, k) for k in data.model_dump(exclude={"record_type"})}
                    if _hash(actual) != _hash(data.model_dump(exclude={"record_type"})):
                        existing.quality = "conflict"
                        raise ValueError("Registry revision conflicts with an existing effective channel; submit a new registry revision")
                    report["duplicates"] += 1
                    continue
                sensor = SensorChannel(id=id, source_id=source.id, **data.model_dump(exclude={"record_type"}))
                session.add(sensor)
                session.flush()
                _audit(session, actor, "sensor.registry_imported", "sensor_channel", sensor.id, {"source_version_id": source_version.id, "original_record_id": source_version.original_id, "row": index + 1})
                report["sensors"] += 1
            elif kind == "sample":
                data = SampleInput.model_validate(body)
                sensor = _sensor(session, source.id, data.channel_key, data.chamber_id, data.timestamp)
                if sensor is None:
                    raise ValueError("No unambiguous effective sensor registry entry for sample")
                if sensor.signal_type == "state" and data.state is None:
                    raise ValueError("State channel sample needs a state value")
                if sensor.signal_type != "state" and data.value is None:
                    raise ValueError("Measured channel sample needs a numeric value")
                if sensor.signal_type == "validated_interval" and data.end_at is None:
                    raise ValueError("Validated interval requires a recorded end timestamp")
                quality = data.quality
                if data.value is not None and ((sensor.valid_min is not None and data.value < sensor.valid_min) or (sensor.valid_max is not None and data.value > sensor.valid_max)):
                    quality = "bad"
                values = data.model_dump(exclude={"record_type", "channel_key", "chamber_id"})
                values["quality"] = quality
                values["source_location"] = data.source_location or {"row": index + 1}
                id = "sample-" + _hash({"sensor": sensor.id, "version": source_version.id, "body": data.model_dump(mode="json")})[:40]
                if session.get(SensorSample, id):
                    report["duplicates"] += 1
                    continue
                same_time = session.scalar(select(SensorSample).where(SensorSample.sensor_id == sensor.id, SensorSample.source_version_id == source_version.id, SensorSample.timestamp == data.timestamp, SensorSample.end_at == data.end_at))
                if same_time:
                    # The original document retains both assertions. Mark the
                    # typed projection conflicted so a partial import cannot
                    # silently select whichever value appeared first.
                    same_time.quality = "conflict"
                    raise ValueError("Conflicting duplicate timestamp within source version; canonical exposure withheld")
                session.add(SensorSample(id=id, sensor_id=sensor.id, source_version_id=source_version.id, **values))
                session.flush()
                report["samples"] += 1
            elif kind in {"mapping", "exposure_rule"}:
                body.pop("record_type", None)
                channel_key = body.pop("channel_key", None)
                if not body.get("sensor_id") and channel_key:
                    sensor = _sensor(session, source.id, channel_key, body.get("chamber_id"), timestamp(body["effective_from"]))
                    if not sensor:
                        raise ValueError("Proposal channel could not be resolved")
                    body["sensor_id"] = sensor.id
                if kind == "mapping":
                    create_mapping(session, MappingInput.model_validate(body), actor)
                    report["mappings"] += 1
                else:
                    create_rule(session, ExposureRuleInput.model_validate(body), actor)
                    report["rules"] += 1
            else:
                raise ValueError("Unsupported telemetry record_type")
        except (ValueError, TypeError, KeyError) as exc:
            report["errors"].append({"row": index + 1, "record_type": kind, "error": str(exc)[:2000], "source_version_id": source_version.id})
    report["lineage"] = rebuild_exposure(session, source.id)
    _audit(session, actor, "telemetry.ingested", "source_version", source_version.id, report)
    session.flush()
    return report


def _samples(session: Session, sensor_id: str, start: datetime, end: datetime, gap: float) -> list[SensorSample]:
    records = session.scalars(select(SensorSample).where(SensorSample.sensor_id == sensor_id, SensorSample.timestamp >= start - timedelta(seconds=gap), SensorSample.timestamp <= end + timedelta(seconds=gap)).order_by(SensorSample.timestamp, SensorSample.id).limit(MAX_BATCH_RECORDS + 1)).all()
    if len(records) > MAX_BATCH_RECORDS:
        raise ValueError("Telemetry calculation exceeds bounded batch; partition its approved window")
    return records


def derive_rule_samples(rule: ExposureDefinition, samples: Sequence[SensorSample], start: datetime, end: datetime) -> dict[str, Any]:
    """Reuse the phase-1 conservative counter engine and interval union rules."""
    issues: list[str] = []
    intervals: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    base = {"dimension": rule.dimension, "source": rule.source_name, "quality": "verified"}
    if rule.method == "counter":
        records = []
        for sample in samples:
            if sample.quality not in GOOD or sample.value is None:
                issues.append(f"Counter sample {sample.id} is invalid; adjacent intervals unavailable")
                # A conflicting same-time value prevents accidentally bridging a
                # bad sample. Counter engine rejects both adjacent increments.
                records.extend([{"id": sample.id, "at": sample.timestamp, "value": 0}, {"id": sample.id + ":invalid", "at": sample.timestamp, "value": rule.rollover / 2 if rule.rollover else 1}])
                continue
            row = {"id": sample.id, "at": sample.timestamp, "value": sample.value, "reset": sample.reset}
            if sample.reset_at:
                row.update(reset_at=sample.reset_at, reset_baseline=sample.reset_baseline)
            records.append(row)
        derived = counter_intervals(records, source=rule.source_name, dimension=rule.dimension, max_gap_hours=rule.max_gap_seconds / 3600, rollover=rule.rollover, max_rate=rule.max_rate or 1)
        intervals = derived["intervals"]
        coverage = derived["coverage_intervals"]
        issues.extend(derived["issues"])
    elif rule.method == "validated_interval":
        inactive: list[tuple[datetime, datetime]] = []
        for sample in samples:
            if sample.quality not in GOOD or sample.end_at is None:
                issues.append(f"Interval sample {sample.id} excluded: incomplete or invalid evidence")
                continue
            elapsed = (sample.end_at - sample.timestamp).total_seconds() / 3600
            if sample.value is None or sample.value < 0 or sample.value > elapsed + 1e-9:
                issues.append(f"Interval sample {sample.id}: invalid documented operating-hour increment")
                continue
            if sample.value not in {0.0, elapsed} and abs(sample.value - elapsed) > 1e-9:
                issues.append(f"Interval sample {sample.id}: aggregate operating hours do not locate active periods; unallocated")
                continue
            begins, ends = max(start, sample.timestamp), min(end, sample.end_at)
            if begins < ends:
                # Validated operating interval stores elapsed active duration,
                # not a cumulative counter increment requiring interpolation.
                if sample.value > 0:
                    intervals.append({**base, "id": sample.id, "start": begins, "end": ends})
                else:
                    inactive.append((begins, ends))
                coverage.append({"start": begins, "end": ends, "source": rule.source_name})
        active = merge_intervals((row["start"], row["end"]) for row in intervals)
        off = merge_intervals(inactive)
        conflicts: list[tuple[datetime, datetime]] = []
        i = j = 0
        while i < len(active) and j < len(off):
            begins, ends = max(active[i][0], off[j][0]), min(active[i][1], off[j][1])
            if begins < ends:
                conflicts.append((begins, ends))
            if active[i][1] <= off[j][1]:
                i += 1
            else:
                j += 1
        if conflicts:
            issues.append("Contradictory active/inactive validated intervals; overlapping exposure and coverage withheld")
            intervals = [part for row in intervals for part in _subtract_record(row, conflicts, issues)]
            coverage = [part for row in coverage for part in _subtract_record(row, conflicts, issues)]
    elif rule.method == "state":
        by_time: dict[datetime, list[SensorSample]] = {}
        for sample in samples:
            by_time.setdefault(sample.timestamp, []).append(sample)
        times = sorted(by_time)
        for previous, current in zip(times, times[1:]):
            p, c = by_time[previous], by_time[current]
            if len({(v.state, v.quality) for v in p}) != 1 or len({(v.state, v.quality) for v in c}) != 1:
                issues.append(f"Conflicting state samples near {previous.isoformat()}; interval unavailable")
                continue
            if p[0].quality not in GOOD or c[0].quality not in GOOD:
                issues.append(f"Invalid state samples near {previous.isoformat()}; interval unavailable")
                continue
            allowed_states = {rule.active_value, getattr(rule, "inactive_value", None)} - {None}
            if len(allowed_states) != 2 or p[0].state not in allowed_states or c[0].state not in allowed_states:
                issues.append(f"State semantics are undocumented or unknown near {previous.isoformat()}; interval unavailable")
                continue
            if (current - previous).total_seconds() > rule.max_gap_seconds:
                issues.append(f"State sample gap exceeds approved limit near {previous.isoformat()}")
                continue
            begins, ends = max(start, previous), min(end, current)
            if begins >= ends:
                continue
            coverage.append({"start": begins, "end": ends, "source": rule.source_name})
            if p[0].state == rule.active_value:
                intervals.append({**base, "id": p[0].id, "start": begins, "end": ends})
    else:
        raise ValueError("Unsupported approved exposure method")
    # Counter increments cannot be prorated across rule/config/installation
    # boundaries. calculate_exposure records the withheld interval explicitly.
    result = calculate_exposure(intervals, start, end, as_of=end, dimension=rule.dimension, source=rule.source_name, coverage_intervals=coverage)
    issues.extend(result["issues"])
    result["issues"] = list(dict.fromkeys(issues))
    if issues:
        result["confidence"] = "limited"
    return {"intervals": intervals, "coverage": coverage, "issues": result["issues"], "result": result, "source_version_ids": sorted({s.source_version_id for s in samples}), "sample_ids": [s.id for s in samples], "sample_signatures": [{"id": s.id, "timestamp": s.timestamp.isoformat(), "end_at": s.end_at.isoformat() if s.end_at else None, "value": s.value, "state": s.state, "quality": s.quality, "reset": s.reset, "reset_at": s.reset_at.isoformat() if s.reset_at else None, "reset_baseline": s.reset_baseline} for s in samples]}


def _rule_windows(session: Session, component: ComponentInstance, install: Installation, at: datetime):
    position, chamber, tool = _location(session, install)
    start, end = install.installed_at, min(install.removed_at or at, at)
    if start >= end:
        return []
    rules = session.scalars(select(ExposureDefinition).where(ExposureDefinition.definition_id == component.definition_id, ExposureDefinition.verification.in_(APPROVED), ExposureDefinition.source_name == position.exposure_source)).all()
    windows = []
    for rule in rules:
        sensor = session.get(SensorChannel, rule.sensor_id)
        if sensor.chamber_id != chamber.id or rule.part_revision not in {None, component.revision} or rule.chamber_id not in {None, chamber.id}:
            continue
        periods = session.scalars(select(EquipmentConfigurationPeriod).where(EquipmentConfigurationPeriod.tool_id == tool.id, EquipmentConfigurationPeriod.verification.in_({"approved", "synthetic_only", "verified", "verified_synthetic"}))).all()
        mappings = session.scalars(select(ComponentSensorMapping).where(ComponentSensorMapping.sensor_id == sensor.id, ComponentSensorMapping.definition_id == component.definition_id, ComponentSensorMapping.verification.in_(APPROVED), ComponentSensorMapping.relationship == "exposure_counter")).all()
        for mapping in mappings:
            if mapping.configuration_id != rule.configuration_id or mapping.configuration_id != sensor.configuration_id or mapping.part_revision not in {None, component.revision} or mapping.chamber_id not in {None, chamber.id}:
                continue
            for period in periods:
                if period.configuration_id != rule.configuration_id:
                    continue
                window = _between(start, end, rule, mapping, sensor, period)
                if window:
                    for begins, ends, conflict in _configuration_segments(periods, rule.configuration_id, window[0], window[1]):
                        windows.append({"start": begins, "end": ends, "rule": rule, "sensor": sensor, "chamber_id": chamber.id, "position": position, "registry_issue": sensor.quality in {"conflict", "bad"}, "configuration_conflict": conflict, "mapping_id": mapping.id, "configuration_period_id": period.id})
    # Two approved mappings to the same rule do not make two exposure sources.
    return list({(w["start"], w["end"], w["rule"].id): w for w in windows}.values())


def _lineage_hash(component: ComponentInstance, rule: ExposureDefinition, start: datetime, end: datetime, derived: dict[str, Any]):
    return _hash({"component_id": component.id, "rule_id": rule.id, "window": [start, end], "samples": derived["sample_signatures"], "issues": derived["issues"], "applicability": derived.get("applicability"), "method": METHOD_VERSION})


def _lineage(session: Session, component: ComponentInstance, rule: ExposureDefinition, start: datetime, end: datetime, derived: dict[str, Any], *, persist: bool):
    fingerprint = _lineage_hash(component, rule, start, end, derived)
    existing = session.scalar(select(CalculationLineage).where(CalculationLineage.input_hash == fingerprint))
    if existing or not persist:
        return existing
    serial_intervals = json.loads(json.dumps(derived["intervals"], default=str))
    item = CalculationLineage(id="calc-" + fingerprint[:40], component_id=component.id, rule_id=rule.id, source_version_ids=derived["source_version_ids"], derived_intervals=serial_intervals, method_version=METHOD_VERSION, start=start, end=end, input_hash=fingerprint, issues=derived["issues"], result=json.loads(json.dumps(derived["result"], default=str)), created_at=_now())
    session.add(item)
    session.flush()
    return item


def rebuild_exposure(session: Session, source_id: str, *, component_id: str | None = None) -> int:
    """Persist new immutable calculation revisions; approved raw data only.

    Materialized core rows are caches, recognized by their `ent-` ID prefix.
    Component read models select by rule applicability through the projection
    hook, never by indiscriminately summing these caches with an older source.
    """
    created = 0
    sensor_ids = session.scalars(select(SensorChannel.id).where(SensorChannel.source_id == source_id)).all()
    if not sensor_ids:
        return 0
    statement = select(Installation)
    if component_id:
        statement = statement.where(Installation.component_id == component_id)
    for install in session.scalars(statement):
        component = session.get(ComponentInstance, install.component_id)
        # The latest recorded sample closes the measured window; absence of a
        # later transition cannot manufacture continuing ON exposure.
        sample_end = session.scalar(select(SensorSample.timestamp).where(SensorSample.sensor_id.in_(sensor_ids)).order_by(SensorSample.timestamp.desc()))
        interval_end = session.scalar(select(SensorSample.end_at).where(SensorSample.sensor_id.in_(sensor_ids), SensorSample.end_at.is_not(None)).order_by(SensorSample.end_at.desc()))
        if interval_end and (sample_end is None or interval_end > sample_end):
            sample_end = interval_end
        if sample_end is None:
            continue
        for window in _rule_windows(session, component, install, sample_end):
            rule = window["rule"]
            if rule.source_id != source_id:
                continue
            start, end = window["start"], window["end"]
            samples = _samples(session, rule.sensor_id, start, end, rule.max_gap_seconds)
            derived = derive_rule_samples(rule, samples, start, end)
            derived["applicability"] = {"mapping_id": window["mapping_id"], "configuration_period_id": window["configuration_period_id"], "sensor_id": window["sensor"].id}
            derived["result"]["applicability"] = derived["applicability"]
            if window["registry_issue"] or window["configuration_conflict"]:
                issue = "Actual equipment configuration history is contradictory; exposure withheld" if window["configuration_conflict"] else "Sensor registry contains an unresolved source conflict; exposure withheld"
                derived = {**derived, "intervals": [], "coverage": [], "issues": [issue], "result": {**derived["result"], "hours": 0, "value": 0, "lifetime_hours": 0, "since_refurbishment": 0, "completeness": 0, "confidence": "unknown", "issues": [issue]}}
            before = session.scalar(select(CalculationLineage.id).where(CalculationLineage.input_hash == _lineage_hash(component, rule, start, end, derived)))
            lineage = _lineage(session, component, rule, start, end, derived, persist=True)
            if before:
                continue
            created += 1
            if not samples:
                continue
            raw_id = session.get(SourceVersion, samples[0].source_version_id).raw_record_id
            for index, interval in enumerate(derived["intervals"]):
                rs, re = timestamp(interval["start"]), timestamp(interval["end"])
                if "value" in interval and (rs < start or re > end):
                    continue
                rs, re = max(start, rs), min(end, re)
                if rs >= re:
                    continue
                id = "ent-exp-" + _hash([lineage.id, index])[:40]
                session.add(ExposureInterval(id=id, chamber_id=window["chamber_id"], source=rule.source_name, dimension=rule.dimension, start=rs, end=re, quality="verified", source_record_id=raw_id, value=interval.get("value")))
            for index, coverage in enumerate(derived["coverage"]):
                rs, re = max(start, timestamp(coverage["start"])), min(end, timestamp(coverage["end"]))
                if rs < re:
                    session.add(ObservationCoverage(id="ent-cov-" + _hash([lineage.id, index])[:40], chamber_id=window["chamber_id"], source=rule.source_name, start=rs, end=re, source_record_id=raw_id))
            if rule.method == "counter":
                for sample in samples:
                    id = "ent-count-" + sample.id
                    if sample.value is not None and not session.get(CounterSample, id):
                        version = session.get(SourceVersion, sample.source_version_id)
                        session.add(CounterSample(id=id, chamber_id=window["chamber_id"], source=rule.source_name, dimension=rule.dimension, timestamp=sample.timestamp, value=sample.value, modulus=rule.rollover, source_record_id=version.raw_record_id))
            session.flush()
    return created


def rebuild_component_exposure(session: Session, component_id: str) -> int:
    """Lifecycle transactions call this after an approved install/remove/change."""
    component = session.get(ComponentInstance, component_id)
    if component is None:
        return 0
    sources = set(session.scalars(select(ExposureDefinition.source_id).where(ExposureDefinition.definition_id == component.definition_id, ExposureDefinition.verification.in_(APPROVED))))
    return sum(rebuild_exposure(session, source_id, component_id=component_id) for source_id in sources)


def _subtract_record(record: Mapping[str, Any], windows: Sequence[tuple[datetime, datetime]], issues: list[str]) -> list[dict[str, Any]]:
    start, end = timestamp(record["start"]), timestamp(record["end"])
    segments = [(start, end)]
    for ws, we in windows:
        segments = [(a, b) for s, e in segments for a, b in ((s, min(e, ws)), (max(s, we), e)) if a < b] if any(s < we and e > ws for s, e in segments) else segments
    if record.get("value") is not None and segments != [(start, end)]:
        issues.append("Legacy counter delta crosses an approved source boundary; unallocated rather than prorated")
        return []
    return [{**record, "start": s, "end": e} for s, e in segments]


def project_component_exposure(session: Session, component: ComponentInstance, hist: Sequence[Mapping[str, Any]], at: datetime, all_intervals: Sequence[Mapping[str, Any]], coverage: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Read-only overlay; keep phase-1 sources outside approved rule windows."""
    # Persisted caches are excluded; sample/version/rule selection is authoritative.
    intervals = [dict(r) for r in all_intervals if not str(r.get("id", "")).startswith("ent-")]
    observed = [dict(r) for r in coverage if not str(r.get("id", "")).startswith("ent-")]
    result: dict[str, Any] = {"intervals": intervals, "coverage": observed, "issues": [], "lineage_ids": [], "rules": []}
    for historical in hist:
        install = session.get(Installation, historical["id"])
        if install is None:
            continue
        windows = _rule_windows(session, component, install, at)
        if not windows:
            continue
        suppressed = merge_intervals((w["start"], w["end"]) for w in windows)
        chamber_id = historical["chamber_id"]
        source = windows[0]["rule"].source_name
        result["intervals"] = [part for row in result["intervals"] for part in (_subtract_record(row, suppressed, result["issues"]) if row.get("chamber_id") == chamber_id and row.get("source") == source else [row])]
        result["coverage"] = [part for row in result["coverage"] for part in (_subtract_record(row, suppressed, result["issues"]) if row.get("chamber_id") == chamber_id and row.get("source") == source else [row])]
        boundaries = sorted({v for w in windows for v in (w["start"], w["end"])})
        for start, end in zip(boundaries, boundaries[1:]):
            active = [w for w in windows if w["start"] < end and w["end"] > start]
            if not active:
                continue
            if len({w["rule"].id for w in active}) > 1:
                result["issues"].append("Competing approved exposure definitions require engineering reconciliation; overlapping exposure withheld")
                continue
            rule = active[0]["rule"]
            if active[0]["configuration_conflict"]:
                result["issues"].append("Actual equipment configuration history is contradictory; exposure withheld")
                continue
            if active[0]["registry_issue"]:
                result["issues"].append("Sensor registry contains an unresolved source conflict; exposure withheld")
                continue
            samples = _samples(session, rule.sensor_id, start, end, rule.max_gap_seconds)
            derived = derive_rule_samples(rule, samples, start, end)
            derived["applicability"] = {"mapping_id": active[0]["mapping_id"], "configuration_period_id": active[0]["configuration_period_id"], "sensor_id": active[0]["sensor"].id}
            derived["result"]["applicability"] = derived["applicability"]
            for row in derived["intervals"]:
                result["intervals"].append({**row, "chamber_id": chamber_id})
            for row in derived["coverage"]:
                result["coverage"].append({**row, "chamber_id": chamber_id})
            result["issues"].extend(derived["issues"])
            lineage = _lineage(session, component, rule, start, end, derived, persist=False)
            if lineage:
                result["lineage_ids"].append(lineage.id)
            result["rules"].append({"id": rule.id, "sensor_id": rule.sensor_id, "mapping_id": active[0]["mapping_id"], "configuration_period_id": active[0]["configuration_period_id"], "method": rule.method, "document_reference": rule.document_reference, "approved_by": rule.approved_by, "start": start.isoformat(), "end": end.isoformat()})
    result["issues"] = list(dict.fromkeys(result["issues"]))
    result["lineage_ids"] = list(dict.fromkeys(result["lineage_ids"]))
    return result


def sensor_dict(sensor: SensorChannel) -> dict[str, Any]:
    return {key: (getattr(sensor, key).isoformat() if isinstance(getattr(sensor, key), datetime) else getattr(sensor, key)) for key in ("id", "source_id", "tool_id", "chamber_id", "subsystem", "channel_key", "description", "signal_type", "unit", "sampling_hz", "valid_min", "valid_max", "configuration_id", "effective_from", "effective_to", "document_reference", "verification", "quality")}


def mapping_dict(mapping: ComponentSensorMapping) -> dict[str, Any]:
    return {key: (getattr(mapping, key).isoformat() if isinstance(getattr(mapping, key), datetime) else getattr(mapping, key)) for key in ("id", "definition_id", "sensor_id", "relationship", "physical_explanation", "configuration_id", "chamber_id", "part_revision", "effective_from", "effective_to", "verification", "evidence", "confidence", "proposed_by", "approved_by", "approved_at")}


def rule_dict(rule: ExposureDefinition) -> dict[str, Any]:
    return {key: (getattr(rule, key).isoformat() if isinstance(getattr(rule, key), datetime) else getattr(rule, key)) for key in ("id", "definition_id", "source_id", "sensor_id", "configuration_id", "chamber_id", "part_revision", "dimension", "method", "source_name", "active_value", "inactive_value", "max_gap_seconds", "rollover", "max_rate", "aggregation", "effective_from", "effective_to", "verification", "document_reference", "approved_by", "approved_at")}


def _downsample(points: list[dict[str, Any]], max_points: int) -> list[dict[str, Any]]:
    if len(points) <= max_points:
        return points
    # Deterministic evenly spaced display points retain endpoints. Exposure and
    # quality calculations always use the original bounded records, not this UI
    # reduction. No interpolation creates artificial measurements.
    return [points[round(i * (len(points) - 1) / (max_points - 1))] for i in range(max_points)]


def component_telemetry(session: Session, component: ComponentInstance, *, start: datetime, end: datetime, state: str | None = None, max_points: int = 1000, actor: Principal | None = None) -> dict[str, Any]:
    query = TelemetryQuery(start=start, end=end, state=state, max_points=max_points)
    actor = actor or Principal("synthetic-anonymous", "viewer", anonymous_demo=True)
    issues: list[str] = []
    channels: list[dict[str, Any]] = []
    installations = session.scalars(select(Installation).where(Installation.component_id == component.id)).all()
    mappings = session.scalars(select(ComponentSensorMapping).where(ComponentSensorMapping.definition_id == component.definition_id, ComponentSensorMapping.verification.in_(APPROVED))).all()
    for mapping in mappings:
        sensor = session.get(SensorChannel, mapping.sensor_id)
        source = session.get(EnterpriseSource, sensor.source_id)
        if not source_allowed(session, actor, source, sensor=sensor, at=query.start) or mapping.part_revision not in {None, component.revision}:
            continue
        windows: list[tuple[datetime, datetime]] = []
        for install in installations:
            position, chamber, tool = _location(session, install)
            if chamber.id != sensor.chamber_id or mapping.chamber_id not in {None, chamber.id} or mapping.configuration_id != sensor.configuration_id:
                continue
            begins, ends = max(query.start, install.installed_at), min(query.end, install.removed_at or query.end)
            periods = session.scalars(select(EquipmentConfigurationPeriod).where(EquipmentConfigurationPeriod.tool_id == tool.id, EquipmentConfigurationPeriod.verification.in_({"approved", "verified", "synthetic_only", "verified_synthetic"}))).all()
            for period in periods:
                if period.configuration_id != mapping.configuration_id:
                    continue
                window = _between(begins, ends, mapping, sensor, period)
                if window:
                    windows.extend((s, e) for s, e, conflict in _configuration_segments(periods, mapping.configuration_id, window[0], window[1]) if not conflict)
        windows = merge_intervals(windows)
        if not windows:
            continue
        raw = session.scalars(select(SensorSample).where(SensorSample.sensor_id == sensor.id, SensorSample.timestamp >= windows[0][0], SensorSample.timestamp < windows[-1][1]).order_by(SensorSample.timestamp, SensorSample.id).limit(MAX_BATCH_RECORDS + 1)).all()
        if len(raw) > MAX_BATCH_RECORDS:
            raise ValueError("Telemetry response exceeds 50,000 bounded records; narrow the query window")
        eligible = [p for p in raw if any(s <= p.timestamp < e for s, e in windows)]
        selected = [p for p in eligible if query.state is None or p.state == query.state or p.source_location.get("operating_state") == query.state]
        points = [{"id": p.id, "timestamp": p.timestamp.isoformat(), "value": p.value, "state": p.state, "quality": p.quality, "source_version_id": p.source_version_id, "source_location": p.source_location, "unit": sensor.unit} for p in selected]
        deduped = list({(p["timestamp"], p["value"], p["state"], p["source_version_id"]): p for p in points}.values())
        good = sum(p.quality in GOOD for p in eligible)
        latest = max((p.timestamp for p in eligible), default=None)
        gaps = []
        if sensor.sampling_hz:
            expected = 1 / sensor.sampling_hz
            times = sorted({p.timestamp for p in eligible if p.quality in GOOD})
            gaps = [(a, b) for a, b in zip(times, times[1:]) if (b - a).total_seconds() <= expected * 2]
            completeness = min(1, union_hours(gaps) / union_hours(windows)) if union_hours(windows) else None
        else:
            completeness = None
        channels.append({**sensor_dict(sensor), "mapping_id": mapping.id, "relationship": mapping.relationship, "physical_explanation": mapping.physical_explanation, "mapping_verification": mapping.verification, "approved_by": mapping.approved_by, "evidence": mapping.evidence, "points": _downsample(deduped, max_points), "record_count": len(eligible), "displayed_count": min(len(deduped), max_points), "valid_records": good, "latest_at": latest.isoformat() if latest else None, "freshness_seconds": max(0, (query.end - latest).total_seconds()) if latest else None, "completeness": completeness, "quality": "good" if eligible and good == len(eligible) else "incomplete", "interpretation": "Diagnostic telemetry; no validated evidence of component degradation or failure probability", "downsample_method": "evenly spaced observed samples; endpoints retained", "applicable_windows": [{"start": s.isoformat(), "end": e.isoformat()} for s, e in windows]})
    if not channels:
        issues.append("No approved, configuration/revision/time-applicable sensor mapping for this component in the selected source scope")
    correlated = []
    chamber_ids = {channel["chamber_id"] for channel in channels}
    for event in session.scalars(select(EquipmentEvent).where(EquipmentEvent.chamber_id.in_(chamber_ids), EquipmentEvent.asserted_at >= query.start, EquipmentEvent.asserted_at < query.end)):
        if any(i.installed_at <= event.asserted_at < (i.removed_at or query.end) and _location(session, i)[1].id == event.chamber_id for i in installations):
            correlated.append({"id": event.id, "timestamp": event.asserted_at.isoformat(), "label": event.label, "failure_id": event.failure_id, "symptom_role": event.symptom_role, "interpretation": "Temporal association only; not proof of component causation"})
    return {"component_id": component.id, "start": query.start.isoformat(), "end": query.end.isoformat(), "state_filter": query.state, "channels": channels, "items": channels, "events": correlated, "issues": issues, "predictive_health_indicator": False, "reference_comparison": "No independently validated controlled reference population is available; channel history is diagnostic only", "max_points_per_channel": max_points}


def component_lineage(session: Session, component_id: str, actor: Principal) -> dict[str, Any]:
    items = []
    for lineage in session.scalars(select(CalculationLineage).where(CalculationLineage.component_id == component_id).order_by(CalculationLineage.created_at.desc()).limit(100)):
        rule = session.get(ExposureDefinition, lineage.rule_id)
        source = session.get(EnterpriseSource, rule.source_id)
        sensor = session.get(SensorChannel, rule.sensor_id)
        if not source_allowed(session, actor, source, sensor=sensor, at=lineage.start):
            continue
        items.append({"id": lineage.id, "component_id": lineage.component_id, "rule": rule_dict(rule), "source_version_ids": lineage.source_version_ids, "derived_intervals": lineage.derived_intervals, "method_version": lineage.method_version, "start": lineage.start.isoformat(), "end": lineage.end.isoformat(), "input_hash": lineage.input_hash, "issues": lineage.issues, "result": lineage.result, "created_at": lineage.created_at.isoformat()})
    return {"items": items, "limit": 100, "note": "Calculation revisions are retained. Latest calculation is not proof that an older source version was wrong; conflicts require review."}
