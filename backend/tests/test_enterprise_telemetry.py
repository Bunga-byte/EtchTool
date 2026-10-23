"""Synthetic scenarios D/E/F: approved configuration-aware sensor exposure."""
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.auth import Principal
from app.config import Settings
from app.db import make_engine
from app.models import Base, ComponentInstance, EquipmentConfiguration, ExposureInterval, Installation, ObservationCoverage, RawSourceRecord
from app.seed import seed
from app.enterprise.models import CalculationLineage, ComponentSensorMapping, EntityAlias, EquipmentConfigurationPeriod, ExposureDefinition, SensorChannel, SensorSample, SourceVersion
from app.enterprise.seed import seed_enterprise
from app.enterprise.telemetry import component_lineage, component_telemetry, derive_rule_samples, ingest_telemetry, project_component_exposure, rebuild_exposure, review_mapping, review_rule
from app.enterprise.telemetry_router import router
from app.services.exposure import component_exposure, timestamp

START = timestamp("2026-01-26T00:00:00Z")
END = timestamp("2026-01-31T00:00:00Z")
ACTOR = Principal("synthetic-engineer", "editor", ("fdc-demo",), ("tool-1",), ("telemetry",))
FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "enterprise" / "fdc-telemetry.json"


@pytest.fixture
def session(tmp_path):
    engine = make_engine("sqlite:///" + str(tmp_path / "telemetry.db"))
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions() as s:
        seed(s)
        seed_enterprise(s)
        s.commit()
        yield s
    engine.dispose()


def version(session, payload, *, id="v1"):
    text = json.dumps(payload, sort_keys=True)
    hash = hashlib.sha256((id + text).encode()).hexdigest()
    raw = RawSourceRecord(id="raw-" + id, source="fdc-demo", source_id=id, recorded_at=START, effective_at=START, ingested_at=END, payload=payload, fingerprint=hash, quality="synthetic", verification="unverified")
    session.add(raw)
    session.flush()
    item = SourceVersion(id=id, source_id="fdc-demo", raw_record_id=raw.id, original_id="synthetic-document-" + id, revision="1", content_hash=hash, mime_type="application/json", content_b64=base64.b64encode(text.encode()).decode(), title="Synthetic telemetry", equipment_alias="tool1a", collection="telemetry", recorded_at=START, effective_at=START, ingested_at=END, parser_version="test-v1", parse_status="parsed", structured_payload=payload)
    session.add(item)
    session.flush()
    return item


def ingest_fixture(session):
    payload = json.loads(FIXTURE.read_text())
    source = version(session, payload)
    report = ingest_telemetry(session, source, payload, ACTOR)
    assert report["errors"] == []
    return source, report


def approve_all(session):
    for mapping in session.scalars(select(ComponentSensorMapping)):
        if mapping.verification == "proposed":
            review_mapping(session, mapping, "approve", "Synthetic engineering review of physical applicability", ACTOR)
    for rule in session.scalars(select(ExposureDefinition)):
        if rule.verification == "proposed":
            review_rule(session, rule, "approve", "Synthetic engineering review of exposure definition", ACTOR)
    session.flush()


def exposure(session, id, at=END, baseline=True):
    component = session.get(ComponentInstance, id)
    installs = session.scalars(select(Installation).where(Installation.component_id == id)).all()
    hist = []
    records = []
    coverage = []
    for install in installs:
        # The test fixture places every subject in this chamber and primary RF
        # slot; production projections derive location from normalized hierarchy.
        hist.append({"id": install.id, "installed_at": install.installed_at, "removed_at": install.removed_at, "chamber_id": "ch-1-a"})
    if baseline:
        records = [{"id": r.id, "start": r.start, "end": r.end, "source": r.source, "dimension": r.dimension, "chamber_id": r.chamber_id, **({"value": r.value} if r.value is not None else {})} for r in session.scalars(select(ExposureInterval).where(ExposureInterval.chamber_id == "ch-1-a", ExposureInterval.source == "rf_primary"))]
        coverage = [{"id": r.id, "start": r.start, "end": r.end, "source": r.source, "chamber_id": r.chamber_id} for r in session.scalars(select(ObservationCoverage).where(ObservationCoverage.chamber_id == "ch-1-a", ObservationCoverage.source == "rf_primary"))]
    projected = project_component_exposure(session, component, hist, at, records, coverage)
    result = component_exposure(projected["intervals"], hist, at, source="rf_primary", coverage_intervals=projected["coverage"])
    return result, projected


def test_unapproved_telemetry_never_changes_existing_rf_hours(session):
    before, _ = exposure(session, "cmp-1-a-rf")
    source, report = ingest_fixture(session)
    after, projected = exposure(session, "cmp-1-a-rf")
    assert report["sensors"] == 2 and report["samples"] > 0
    assert before["hours"] == after["hours"] == 140
    assert projected["rules"] == []
    assert session.scalars(select(CalculationLineage)).all() == []
    sensor = session.scalar(select(SensorChannel))
    assert sensor.valid_min is None and sensor.valid_max is None
    replay = ingest_telemetry(session, source, json.loads(FIXTURE.read_text()), ACTOR)
    assert replay["samples"] == 0 and replay["sensors"] == 0 and replay["duplicates"] > 0


def test_approved_fixture_overlays_legacy_source_without_double_counting(session):
    ingest_fixture(session)
    approve_all(session)
    result, projected = exposure(session, "cmp-1-a-rf")
    # Jan21–26 existing14h/day =70; Jan26–31 imported12h/day =60.
    assert result["hours"] == 130
    assert result["completeness"] == 1
    assert len(projected["rules"]) == 1
    assert projected["lineage_ids"]
    assert rebuild_exposure(session, "fdc-demo") == 0
    lineage = component_lineage(session, "cmp-1-a-rf", ACTOR)["items"]
    assert len(lineage) == 1 and lineage[0]["result"]["hours"] == 60
    assert lineage[0]["source_version_ids"] == ["v1"]
    assert lineage[0]["rule"]["approved_by"] == ACTOR.subject


def test_scenario_d_install_and_removal_clip_two_active_intervals(session):
    ingest_fixture(session)
    # A standalone, separately serialized component is installed halfway through
    # the imported ON period and removed halfway through the next one.
    install = Installation(id="scenario-d", component_id="cmp-enterprise-spare", position_id="pos-enterprise-empty", installed_at=timestamp("2026-01-26T06:00:00Z"), removed_at=timestamp("2026-01-27T06:00:00Z"), reason="Synthetic approved installation", removal_reason="Synthetic removal", source_record_id="raw-v1")
    session.add(install)
    session.flush()
    approve_all(session)
    result, projected = exposure(session, "cmp-enterprise-spare")
    assert result["hours"] == 12  # Jan26 06–12 plus Jan27 00–06.
    later, _ = exposure(session, "cmp-enterprise-spare", timestamp("2026-02-01T00:00:00Z"))
    assert later["hours"] == 12
    assert result["lifetime_hours"] == 12


def test_scenario_e_counter_restart_yields_observed_minimum_and_no_proration(session):
    rule = ExposureDefinition(id="counter", definition_id="rf-a", source_id="fdc-demo", sensor_id="unused", configuration_id="cfg-demo", dimension="rf_hours", method="counter", source_name="rf_primary", max_gap_seconds=86400, max_rate=1, aggregation="union", effective_from=START, verification="approved")
    def row(id, time, value, **kwargs):
        return SensorSample(id=id, sensor_id="unused", source_version_id="v1", timestamp=timestamp(time), value=value, quality="synthetic", reset=False, **kwargs)
    samples = [row("s1", "2026-01-26T00:00:00Z", 1), row("s2", "2026-01-26T03:00:00Z", 2, reset_at=timestamp("2026-01-26T01:00:00Z"), reset_baseline=0), row("s3", "2026-01-26T04:00:00Z", 3)]
    result = derive_rule_samples(rule, samples, START, timestamp("2026-01-26T04:00:00Z"))
    assert result["result"]["hours"] == 3
    assert result["result"]["completeness"] == .75
    assert any("before the known reset" in issue for issue in result["issues"])
    clipped = derive_rule_samples(rule, samples, timestamp("2026-01-26T02:00:00Z"), timestamp("2026-01-26T04:00:00Z"))
    assert clipped["result"]["hours"] == 1
    assert any("unallocated" in issue for issue in clipped["issues"])


def test_scenario_f_multiple_channels_preserve_physical_relationship_and_dates(session):
    ingest_fixture(session)
    before = component_telemetry(session, session.get(ComponentInstance, "cmp-1-a-rf"), start=START, end=END, actor=ACTOR)
    assert before["channels"] == []
    approve_all(session)
    result = component_telemetry(session, session.get(ComponentInstance, "cmp-1-a-rf"), start=START, end=END, actor=ACTOR)
    assert {c["relationship"] for c in result["channels"]} == {"exposure_counter", "supporting_diagnostic"}
    assert all(c["points"] for c in result["channels"])
    assert result["predictive_health_indicator"] is False
    assert all("Diagnostic" in c["interpretation"] for c in result["channels"])
    old = component_telemetry(session, session.get(ComponentInstance, "cmp-1-a-rf-old"), start=START, end=END, actor=ACTOR)
    assert old["channels"] == []  # Removed before mappings became effective.


def test_configuration_revision_and_source_scope_gate_mapping(session):
    ingest_fixture(session)
    approve_all(session)
    component = session.get(ComponentInstance, "cmp-1-a-rf")
    component.revision = "UNVERIFIED-REVISION"
    result = component_telemetry(session, component, start=START, end=END, actor=ACTOR)
    assert result["channels"] == []
    component.revision = "A"
    outsider = Principal("other-tool", "editor", ("fdc-demo",), ("tool-2",), ("telemetry",))
    assert component_telemetry(session, component, start=START, end=END, actor=outsider)["channels"] == []
    for period in session.scalars(select(EquipmentConfigurationPeriod).where(EquipmentConfigurationPeriod.tool_id == "tool-1")):
        period.effective_to = timestamp("2026-01-25T00:00:00Z")
    assert component_telemetry(session, component, start=START, end=END, actor=ACTOR)["channels"] == []
    _, projected = exposure(session, component.id)
    assert projected["rules"] == []


def test_changed_source_values_preserve_both_versions_and_flag_conflicts(session):
    _, report = ingest_fixture(session)
    approve_all(session)
    payload = {"records": [{"record_type": "sample", "channel_key": "SYN-RF-ACTIVE", "chamber_id": "ch-1-a", "timestamp": "2026-01-27T00:00:00Z", "state": "off"}]}
    changed = version(session, payload, id="v2")
    assert ingest_telemetry(session, changed, payload, ACTOR)["errors"] == []
    result, projected = exposure(session, "cmp-1-a-rf")
    assert result["hours"] < 130
    assert any("Conflicting state" in issue for issue in projected["issues"])
    assert session.get(SourceVersion, "v1") and session.get(SourceVersion, "v2")
    assert len(session.scalars(select(CalculationLineage)).all()) == 2


def test_review_requires_exposure_mapping_before_rule_and_is_immutable(session):
    ingest_fixture(session)
    rule = session.scalar(select(ExposureDefinition))
    with pytest.raises(ValueError, match="Approve an applicable"):
        review_rule(session, rule, "approve", "Cannot approve without a physical mapping", ACTOR)
    approve_all(session)
    with pytest.raises(ValueError, match="immutable"):
        review_rule(session, rule, "reject", "Must create new effective revision instead", ACTOR)


def test_bounded_http_queries_and_authorization(session):
    ingest_fixture(session)
    approve_all(session)
    session.commit()
    app = FastAPI()
    app.state.sessions = sessionmaker(session.get_bind(), expire_on_commit=False)
    app.state.config = Settings(tokens_json={"editor": {"subject": "engineering", "role": "editor", "sources": "fdc-demo", "equipment": "tool-1", "collections": "telemetry"}, "other": {"subject": "other", "role": "editor", "sources": "fdc-demo", "equipment": "tool-2", "collections": "telemetry"}})
    app.include_router(router)
    with TestClient(app) as client:
        assert client.get("/api/enterprise/sensors").status_code == 200
        assert len(client.get("/api/enterprise/sensors").json()["items"]) == 2
        assert client.get("/api/enterprise/sensors", headers={"Authorization": "Bearer other"}).json()["items"] == []
        sensor = session.scalar(select(SensorChannel))
        body = {"decision": "reject", "note": "Anonymous actor must not change approved sensor rules"}
        rule = session.scalar(select(ExposureDefinition))
        assert client.post(f"/api/enterprise/exposure-rules/{rule.id}/review", json=body).status_code == 403
        base = "/api/enterprise/components/cmp-1-a-rf/telemetry"
        assert client.get(base, params={"start": START.isoformat(), "end": END.isoformat(), "max_points": 1001}).status_code == 422
        assert client.get(base, params={"start": "2025-01-01T00:00:00Z", "end": END.isoformat()}).status_code == 422
        response = client.get(base, params={"start": START.isoformat(), "end": END.isoformat(), "state": "on"})
        assert response.status_code == 200
        state_points = next(c["points"] for c in response.json()["channels"] if c["signal_type"] == "state")
        assert all(p["state"] == "on" for p in state_points)


def test_unknown_state_is_unavailable_not_assumed_rf_off(session):
    rule = ExposureDefinition(id="state", definition_id="rf-a", source_id="fdc-demo", sensor_id="unused", configuration_id="cfg-demo", dimension="rf_hours", method="state", source_name="rf_primary", active_value="on", inactive_value="off", max_gap_seconds=86400, aggregation="union", effective_from=START, verification="approved")
    samples = [SensorSample(id="s1", timestamp=START, state="on", quality="synthetic"), SensorSample(id="s2", timestamp=START.replace(hour=12), state="undocumented_state", quality="synthetic"), SensorSample(id="s3", timestamp=START.replace(day=27), state="off", quality="synthetic")]
    derived = derive_rule_samples(rule, samples, START, START.replace(day=27))
    assert derived["result"]["hours"] == 0
    assert derived["result"]["completeness"] == 0
    assert any("semantics" in issue for issue in derived["issues"])


def test_contradictory_actual_configuration_is_withheld_even_with_one_rule(session):
    ingest_fixture(session)
    approve_all(session)
    session.add(EquipmentConfiguration(id="cfg-conflict", family="Synthetic", variant="Conflicting synthetic configuration", revision="A", description="A contradictory assertion for testing"))
    session.flush()
    session.add(EquipmentConfigurationPeriod(id="config-contradiction", tool_id="tool-1", configuration_id="cfg-conflict", effective_from=START, effective_to=END, verification="approved"))
    session.flush()
    result, projected = exposure(session, "cmp-1-a-rf")
    assert result["hours"] == 70  # Only Jan21–26 baseline is defensible.
    assert any("configuration history is contradictory" in issue for issue in projected["issues"])
    assert result["completeness"] == .5
    trace = component_telemetry(session, session.get(ComponentInstance, "cmp-1-a-rf"), start=START, end=END, actor=ACTOR)
    assert trace["channels"] == []


def test_conflicting_tool_aliases_do_not_authorize_both_canonical_tools(session):
    ingest_fixture(session)
    approve_all(session)
    session.add(EntityAlias(id="alias-contradiction", source_id="fdc-demo", entity_type="tool", external_id="tool1a", canonical_id="tool-2", valid_from=START, valid_to=END, verification_status="verified", evidence=[{"synthetic": True}]))
    session.flush()
    admin = Principal("synthetic-admin", "admin")
    trace = component_telemetry(session, session.get(ComponentInstance, "cmp-1-a-rf"), start=START, end=END, actor=admin)
    assert trace["channels"] == []
    assert trace["events"] == []


def test_enterprise_http_scope_blocks_component_events_and_lineage(session):
    app = FastAPI()
    app.state.sessions = sessionmaker(session.get_bind(), expire_on_commit=False)
    app.state.config = Settings(mode="enterprise", tokens_json={"scope1": {"subject": "tool1-reader", "role": "viewer", "sources": "fdc-demo", "equipment": "tool-1", "collections": "telemetry"}})
    app.include_router(router)
    session.commit()
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer scope1"}
        params = {"start": "2026-01-01T00:00:00Z", "end": "2026-01-31T00:00:00Z"}
        response = client.get("/api/enterprise/components/cmp-2-b-rf/telemetry", params=params, headers=headers)
        assert response.status_code == 403
        assert client.get("/api/enterprise/components/cmp-2-b-rf/lineage", headers=headers).status_code == 403


def test_validated_intervals_require_located_active_time_and_flag_contradictions(session):
    rule = ExposureDefinition(id="validated", definition_id="rf-a", source_id="fdc-demo", sensor_id="unused", configuration_id="cfg-demo", dimension="rf_hours", method="validated_interval", source_name="rf_primary", max_gap_seconds=86400, aggregation="union", effective_from=START, verification="approved")
    active = SensorSample(id="active", source_version_id="v1", timestamp=START, end_at=START.replace(hour=4), value=4, quality="synthetic")
    inactive = SensorSample(id="inactive", source_version_id="v2", timestamp=START.replace(hour=1), end_at=START.replace(hour=3), value=0, quality="synthetic")
    result = derive_rule_samples(rule, [active, inactive], START, START.replace(hour=4))
    assert result["result"]["hours"] == 2
    assert result["result"]["completeness"] == .5
    assert any("Contradictory" in issue for issue in result["issues"])
    active.value = 2
    partial = derive_rule_samples(rule, [active], START, START.replace(hour=4))
    assert partial["result"]["hours"] == 0
    assert any("do not locate active periods" in issue for issue in partial["issues"])


def test_duplicate_conflicts_within_one_version_do_not_choose_first_value(session):
    ingest_fixture(session)
    approve_all(session)
    common = {"record_type": "sample", "channel_key": "SYN-RF-ACTIVE", "chamber_id": "ch-1-a", "timestamp": "2026-01-28T00:00:00Z"}
    payload = {"records": [{**common, "state": "on"}, {**common, "state": "off"}]}
    changed = version(session, payload, id="v2")
    report = ingest_telemetry(session, changed, payload, ACTOR)
    assert len(report["errors"]) == 1
    projected_sample = session.scalar(select(SensorSample).where(SensorSample.source_version_id == "v2"))
    assert projected_sample.quality == "conflict"
    result, projected = exposure(session, "cmp-1-a-rf")
    assert result["hours"] < 130
    assert any("Conflicting state" in issue for issue in projected["issues"])
    assert changed.structured_payload == payload
