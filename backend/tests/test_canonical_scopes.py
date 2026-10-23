"""Canonical projections must not bypass enterprise equipment/evidence grants."""
from datetime import datetime, timezone
import base64
import hashlib

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import (
    DowntimeAttribution, DowntimeInterval, Evidence, Installation, Position,
    RawSourceRecord, SourceConflict,
)
from app.enterprise.models import CalculationLineage, EnterpriseSource, ExposureDefinition, SensorChannel, SourceVersion


UTC = timezone.utc


@pytest.fixture
def enterprise_client(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'canonical-scope.db'}"
    preparation = create_app(Settings(_env_file=None, database_url=database_url))
    with TestClient(preparation):
        pass
    bindings = {
        "scope-tool-1": {"subject": "equipment-viewer", "role": "viewer", "sources": "maintenance,parts,fdc", "equipment": "tool-1", "collections": "maintenance,parts,telemetry"},
        "scope-tool-1-export": {"subject": "equipment-exporter", "role": "viewer", "sources": "maintenance,parts,fdc", "equipment": "tool-1", "collections": "maintenance,parts,telemetry", "export": "true"},
        "scope-tool-2": {"subject": "second-equipment-viewer", "role": "viewer", "sources": "maintenance,parts,fdc", "equipment": "tool-2", "collections": "maintenance,parts,telemetry"},
        "scope-no-equipment": {"subject": "no-equipment-viewer", "role": "viewer", "sources": "maintenance", "collections": "maintenance"},
        "scope-admin": {"subject": "equipment-admin", "role": "admin"},
    }
    app = create_app(Settings(_env_file=None, database_url=database_url, mode="enterprise", tokens_json=bindings), engine=preparation.state.engine)
    with TestClient(app) as client:
        yield app, client
    app.state.engine.dispose()


def auth(value="scope-tool-1"):
    return {"Authorization": f"Bearer {value}"}


def test_enterprise_inventory_hierarchy_and_fleet_are_equipment_scoped(enterprise_client):
    _, client = enterprise_client
    inventory = client.get("/api/inventory", headers=auth())
    assert inventory.status_code == 200, inventory.text
    assert inventory.json()["items"]
    assert {item["tool_id"] for item in inventory.json()["items"]} == {"tool-1"}
    assert "SYN-02" not in inventory.text and "SYN-03" not in inventory.text
    tree = client.get("/api/hierarchy", headers=auth()).json()
    assert {tool["id"] for site in tree["sites"] for tool in site["tools"]} == {"tool-1"}
    fleet = client.get("/api/fleet", headers=auth()).json()
    assert fleet["metrics"]["tools"] == 1
    assert fleet["metrics"]["chambers"] == 2
    assert fleet["metrics"]["installed_components"] == 6
    assert fleet["metrics"]["downtime_hours"] == 14
    assert {case["id"] for case in fleet["recent_failures"]} == {"case-001"}


def test_direct_foreign_component_failure_and_chamber_reads_are_denied(enterprise_client):
    _, client = enterprise_client
    for path in ("/api/components/cmp-2-a-rf", "/api/failures/case-002", "/api/inventory?chamber_id=ch-2-a"):
        response = client.get(path, headers=auth())
        assert response.status_code == 403, (path, response.text)
        assert "SYN-02A" not in response.text
    assert client.get("/api/components/cmp-1-b-rf", headers=auth()).status_code == 200


def test_failure_register_rates_and_denominators_only_use_authorized_tools(enterprise_client):
    _, client = enterprise_client
    cases = client.get("/api/failures", headers=auth()).json()
    assert {item["id"] for item in cases["items"]} == {"case-001"}
    assert cases["alarm_only_events"] == 0
    analysis_response = client.get("/api/analytics", headers=auth())
    assert analysis_response.status_code == 200, analysis_response.text
    analysis = analysis_response.json()
    assert analysis["rate"]["failures"] == 0
    assert analysis["rate"]["exposure_hours"] == 915
    assert analysis["downtime"]["total_hours"] == 14
    assert set(analysis["downtime"]["by_tool"]) == {"tool-1"}
    assert all(item["component_id"].startswith("cmp-1-") for item in analysis["observations"] + analysis["excluded_components"])
    assert "cmp-2-" not in analysis_response.text and "cmp-3-" not in analysis_response.text
    pm = client.get("/api/pm", headers=auth()).json()
    assert {item["tool_id"] for item in pm["items"]} == {"tool-1"}
    assert pm["compliance"]["recorded_due_events"] == 0


def test_source_conflict_queue_hides_foreign_originals_and_coverage(enterprise_client):
    app, client = enterprise_client
    with app.state.sessions() as session:
        session.add(SourceConflict(id="foreign-scope-conflict", component_id="cmp-2-a-rf", field="installed_component",
            record_a_id="raw-install-cmp-2-a-rf", record_b_id="raw-count-ch-2-a-0", value_a="HIDDEN-TOOL-2-CLAIM-A", value_b="HIDDEN-TOOL-2-CLAIM-B", status="unresolved"))
        session.commit()
    response = client.get("/api/quality", headers=auth())
    assert response.status_code == 200
    assert "HIDDEN-TOOL-2" not in response.text
    assert "raw-install-cmp-2-a-rf" not in response.text
    assert "ch-3-b" not in response.text
    assert {item["id"] for item in response.json()["items"]} == {"conflict-001"}
    second = client.get("/api/quality", headers=auth("scope-tool-2"))
    assert "conflict-001" not in second.text
    assert "foreign-scope-conflict" in second.text


def test_exports_require_grant_and_export_only_authorized_inventory(enterprise_client):
    _, client = enterprise_client
    assert client.get("/api/export/inventory.csv", headers=auth()).status_code == 403
    response = client.get("/api/export/inventory.csv", headers=auth("scope-tool-1-export"))
    assert response.status_code == 200, response.text
    assert "SYN-FLEX-01" in response.text
    assert "SYN-FLEX-02" not in response.text and "SYN-FLEX-03" not in response.text
    assert len(response.text.strip().splitlines()) == 7
    assert client.get("/api/export/inventory.csv?chamber_id=ch-2-a", headers=auth("scope-tool-1-export")).status_code == 403


def test_missing_equipment_grant_fails_closed_and_admin_retains_configured_fleet(enterprise_client):
    _, client = enterprise_client
    for path in ("/api/inventory", "/api/fleet", "/api/hierarchy", "/api/analytics", "/api/pm", "/api/quality"):
        assert client.get(path, headers=auth("scope-no-equipment")).status_code == 403
    admin = client.get("/api/fleet", headers=auth("scope-admin"))
    assert admin.status_code == 200
    assert admin.json()["metrics"]["tools"] == 3
    assert client.get("/api/components/cmp-2-a-rf", headers=auth("scope-admin")).status_code == 200


def test_serial_with_hidden_history_is_withheld_instead_of_leaking_partial_lifetime(enterprise_client):
    app, client = enterprise_client
    with app.state.sessions() as session:
        existing = session.get(Installation, "ins-cmp-1-b-rf")
        existing.removed_at = datetime(2026, 1, 15, tzinfo=UTC)
        session.add(Position(id="scope-hidden-position", assembly_id="ass-ch-2-a-rf", name="Synthetic hidden history slot", exposure_source="rf_primary"))
        session.flush()
        session.add(Installation(id="scope-hidden-history", component_id="cmp-1-b-rf", position_id="scope-hidden-position", installed_at=datetime(2026, 1, 16, tzinfo=UTC), removed_at=datetime(2026, 1, 17, tzinfo=UTC), reason="Synthetic transfer history", source_record_id=existing.source_record_id))
        session.add(Installation(id="scope-return-history", component_id="cmp-1-b-rf", position_id=existing.position_id, installed_at=datetime(2026, 1, 18, tzinfo=UTC), removed_at=None, reason="Synthetic return to allowed tool", source_record_id=existing.source_record_id))
        session.add(DowntimeInterval(id="scope-moved-downtime", failure_id=None, chamber_id="ch-1-b", start=datetime(2026, 1, 26, tzinfo=UTC), end=datetime(2026, 1, 26, 1, tzinfo=UTC), category="active_repair", classification="Synthetic test", source_record_id=existing.source_record_id))
        session.flush()
        session.add(DowntimeAttribution(id="scope-moved-attribution", downtime_id="scope-moved-downtime", component_id="cmp-1-b-rf", weight=1, status="confirmed", rationale="Synthetic test allocation"))
        session.commit()
    assert client.get("/api/components/cmp-1-b-rf", headers=auth()).status_code == 403
    inventory = client.get("/api/inventory", headers=auth())
    assert "cmp-1-b-rf" not in inventory.text
    assert "scope-hidden-history" not in inventory.text
    analysis = client.get("/api/analytics", headers=auth())
    assert analysis.status_code == 200, analysis.text
    assert "cmp-1-b-rf" not in analysis.text
    assert analysis.json()["downtime"]["total_hours"] == 15
    assert analysis.json()["rate"] is None


def test_legacy_failure_detail_does_not_bypass_source_evidence_permissions(enterprise_client):
    app, client = enterprise_client
    at = datetime(2026, 1, 20, 10, tzinfo=UTC)
    content = b"Synthetic restricted collection evidence"
    with app.state.sessions() as session:
        session.add(EnterpriseSource(id="scope-private-source", name="Synthetic restricted evidence source", connector_kind="synthetic_file", classification="synthetic", capabilities={}, config={}, authorized_equipment=["tool1a"], authorized_collections=["restricted-evidence"], enabled=True, polling_allowed=False, interval_seconds=3600))
        session.add(RawSourceRecord(id="scope-private-raw", source="scope-private-source", source_id="HIDDEN-RESTRICTED-DOCUMENT", recorded_at=at, effective_at=at, ingested_at=at, payload={"synthetic": True}, fingerprint=hashlib.sha256(content).hexdigest(), quality="synthetic", verification="synthetic_only"))
        session.flush()
        session.add(SourceVersion(id="scope-private-version", source_id="scope-private-source", raw_record_id="scope-private-raw", original_id="HIDDEN-RESTRICTED-DOCUMENT", revision="SYN-1", content_hash=hashlib.sha256(content).hexdigest(), mime_type="text/plain", content_b64=base64.b64encode(content).decode(), title="Synthetic restricted evidence", equipment_alias="tool1a", collection="restricted-evidence", recorded_at=at, effective_at=at, ingested_at=at, parser_version="test-v1", parse_status="parsed", structured_payload={}))
        session.add(Evidence(id="scope-private-evidence", failure_id="case-001", timestamp=at, kind="synthetic_note", description="HIDDEN-RESTRICTED-EVIDENCE-TEXT", quality="synthetic_only", source_record_id="scope-private-raw"))
        session.commit()
    response = client.get("/api/failures/case-001", headers=auth())
    assert response.status_code == 403
    assert "HIDDEN-RESTRICTED" not in response.text
    assert client.get("/api/failures/case-001", headers=auth("scope-admin")).status_code == 200


def test_calculation_ancestry_obeys_source_grants_while_canonical_values_remain_visible(enterprise_client):
    app, client = enterprise_client
    at = datetime(2026, 1, 20, tzinfo=UTC)
    content = b"Synthetic private telemetry lineage"
    with app.state.sessions() as session:
        session.add(EnterpriseSource(id="private-telemetry-source", name="Synthetic private telemetry source", connector_kind="synthetic_file", classification="synthetic", capabilities={}, config={}, authorized_equipment=["tool1a"], authorized_collections=["telemetry"], enabled=True, polling_allowed=False, interval_seconds=3600))
        session.add(RawSourceRecord(id="private-telemetry-raw", source="private-telemetry-source", source_id="PRIVATE-TRACE-ORIGINAL", recorded_at=at, effective_at=at, ingested_at=at, payload={"synthetic": True}, fingerprint=hashlib.sha256(content).hexdigest(), quality="synthetic", verification="synthetic_only"))
        session.flush()
        session.add(SourceVersion(id="private-telemetry-version", source_id="private-telemetry-source", raw_record_id="private-telemetry-raw", original_id="PRIVATE-TRACE-ORIGINAL", revision="SYN-1", content_hash=hashlib.sha256(content).hexdigest(), mime_type="text/plain", content_b64=base64.b64encode(content).decode(), title="Synthetic private telemetry", equipment_alias="tool1a", collection="telemetry", recorded_at=at, effective_at=at, ingested_at=at, parser_version="test-v1", parse_status="parsed", structured_payload={}))
        session.add(SensorChannel(id="private-telemetry-sensor", source_id="private-telemetry-source", tool_id="tool-1", chamber_id="ch-1-b", channel_key="PRIVATE-CHANNEL", description="Synthetic private telemetry channel", signal_type="state", unit="state", configuration_id="cfg-demo", effective_from=at, verification="synthetic_only", quality="good"))
        session.flush()
        session.add(ExposureDefinition(id="private-telemetry-rule", definition_id="rf-a", source_id="private-telemetry-source", sensor_id="private-telemetry-sensor", configuration_id="cfg-demo", chamber_id="ch-1-b", dimension="rf_hours", method="state", source_name="rf_primary", active_value="ON", max_gap_seconds=3600, max_rate=1, aggregation="union", effective_from=at, verification="proposed", document_reference="PRIVATE-RULE-DOCUMENT"))
        session.flush()
        session.add(CalculationLineage(id="private-telemetry-calculation", component_id="cmp-1-b-rf", rule_id="private-telemetry-rule", source_version_ids=["private-telemetry-version"], derived_intervals=[], method_version="synthetic-test-v1", start=at, end=at, input_hash=hashlib.sha256(content + b"calculation").hexdigest(), issues=[], result={"hours": 0}, created_at=at))
        session.commit()
    inventory = client.get("/api/inventory?chamber_id=ch-1-b", headers=auth())
    assert inventory.status_code == 200, inventory.text
    item = next(item for item in inventory.json()["items"] if item["id"] == "cmp-1-b-rf")
    assert item["exposure"]["hours"] == 915
    assert item["evidence_access"] == "Restricted; approved canonical fields only"
    assert "PRIVATE-" not in inventory.text and "private-telemetry" not in inventory.text
    assert "derivation" not in item["exposure"]
    assert client.get("/api/components/cmp-1-b-rf", headers=auth()).status_code == 403
