"""Independent transport regressions for scoped, auditable synthetic ingestion."""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.main import create_app
from app.models import IngestionOriginal, RawSourceRecord, SourceConflict


@pytest.fixture
def review_app(tmp_path):
    # Deliberately share subject and role: authorization must retain the binding
    # of the actual matched token rather than recover a binding by username.
    bindings = {
        "review-parts-token": {"subject": "same-editor", "role": "editor", "sources": "parts"},
        "review-fdc-token": {"subject": "same-editor", "role": "editor", "sources": "fdc"},
        "review-viewer-token": {"subject": "review-viewer", "role": "viewer", "equipment": "tool-1"},
        "review-admin-token": {"subject": "review-admin", "role": "admin"},
    }
    app = create_app(Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'review.db'}", tokens_json=bindings))
    with TestClient(app) as client:
        yield app, client, bindings
    app.state.engine.dispose()


def token(value):
    return {"Authorization": f"Bearer {value}"}


def part_row(**updates):
    return {
        "source_id": "review-part-row",
        "recorded_at": "2026-01-20T12:00:00Z",
        "effective_at": "2026-01-20T12:00:00Z",
        "equipment_id": "SYN-REVIEW-TOOL",
        "chamber_id": "SYN-REVIEW-CHAMBER",
        "synthetic": True,
        "component_serial": "SYN-REVIEW-SERIAL-A",
        "part_number": "SYN-REVIEW-PART",
        "position_id": "SYN-REVIEW-POSITION",
        "installed_at": "2026-01-01T00:00:00Z",
        **updates,
    }


def fdc_row():
    return {
        "source_id": "review-fdc-row",
        "recorded_at": "2026-01-20T12:00:00Z",
        "effective_at": "2026-01-20T12:00:00Z",
        "equipment_id": "SYN-REVIEW-TOOL",
        "chamber_id": "SYN-REVIEW-CHAMBER",
        "synthetic": True,
        "signal": "SYN-REVIEW-SIGNAL",
        "value": 1.5,
        "unit": "synthetic units",
        "operating_state": "synthetic_process",
    }


def test_matched_token_keeps_source_scope_for_same_subject_role(review_app):
    _, client, _ = review_app
    fdc = {"records": [fdc_row()]}
    assert client.post("/api/integrations/fdc/import", json=fdc, headers=token("review-parts-token")).status_code == 403
    allowed = client.post("/api/integrations/fdc/import", json=fdc, headers=token("review-fdc-token"))
    assert allowed.status_code == 200, allowed.text
    assert len(allowed.json()["records"]) == 1
    assert client.post("/api/integrations/parts/import", json={"records": [part_row()]}, headers=token("review-fdc-token")).status_code == 403


def test_original_mapping_retained_and_reimport_deduplicated(review_app):
    app, client, _ = review_app
    row = part_row()
    row["external_serial"] = row.pop("component_serial")
    body = {"records": [row], "field_mapping": {"external_serial": "component_serial"}}
    first = client.post("/api/integrations/parts/import", json=body, headers=token("review-parts-token"))
    assert first.status_code == 200, first.text
    assert first.json()["records"][0]["payload"]["component_serial"] == "SYN-REVIEW-SERIAL-A"
    second = client.post("/api/integrations/parts/import", json=body, headers=token("review-parts-token"))
    assert second.status_code == 200, second.text
    assert second.json()["duplicates"] == 1
    assert second.json()["records"] == []
    with app.state.sessions() as session:
        normalized = session.scalars(select(RawSourceRecord).where(RawSourceRecord.source_id == "review-part-row")).all()
        assert len(normalized) == 1
        assert normalized[0].payload["component_serial"] == "SYN-REVIEW-SERIAL-A"
        originals = session.scalars(select(IngestionOriginal)).all()
        assert len(originals) == 2
        for original in originals:
            stored = json.loads(original.original_json)
            assert stored["external_serial"] == "SYN-REVIEW-SERIAL-A"
            assert "component_serial" not in stored


def test_invalid_row_is_retained_as_original_not_canonical_record(review_app):
    app, client, _ = review_app
    row = part_row(recorded_at="2026-01-20T12:00:00")  # timezone missing
    response = client.post("/api/integrations/parts/import", json={"records": [row]}, headers=token("review-parts-token"))
    assert response.status_code == 200, response.text
    assert response.json()["records"] == []
    assert len(response.json()["errors"]) == 1
    with app.state.sessions() as session:
        assert not session.scalars(select(RawSourceRecord).where(RawSourceRecord.source_id == "review-part-row")).all()
        originals = session.scalars(select(IngestionOriginal)).all()
        assert len(originals) == 1
        assert json.loads(originals[0].original_json)["recorded_at"] == "2026-01-20T12:00:00"


def test_source_conflict_persists_for_reconciliation_without_overwriting(review_app):
    app, client, _ = review_app
    for serial in ("SYN-REVIEW-SERIAL-A", "SYN-REVIEW-SERIAL-B"):
        response = client.post("/api/integrations/parts/import", json={"records": [part_row(component_serial=serial)]}, headers=token("review-parts-token"))
        assert response.status_code == 200, response.text
    assert response.json()["conflicts"]
    with app.state.sessions() as session:
        originals = session.scalars(select(RawSourceRecord).where(RawSourceRecord.source_id == "review-part-row")).all()
        assert {record.payload["component_serial"] for record in originals} == {"SYN-REVIEW-SERIAL-A", "SYN-REVIEW-SERIAL-B"}
        conflicts = session.scalars(select(SourceConflict).where(SourceConflict.field == "component_serial")).all()
        assert conflicts, "An accepted source disagreement must remain in the persisted reconciliation queue"
        conflict = conflicts[0]
        assert conflict.status == "unresolved"
        assert {conflict.record_a_id, conflict.record_b_id} == {record.id for record in originals}
    queue = client.get("/api/quality").json()["items"]
    assert any(item["id"] == conflict.id for item in queue)


def test_import_mutations_reject_viewer_and_spoofed_role(review_app):
    _, client, _ = review_app
    body = {"records": [part_row()]}
    assert client.post("/api/integrations/parts/import", json=body, headers={"X-Role": "admin"}).status_code == 403
    assert client.post("/api/integrations/parts/import", json=body, headers=token("review-viewer-token")).status_code == 403
    assert client.post("/api/integrations/parts/import", json=body, headers=token("not-a-configured-token")).status_code == 401


def test_enterprise_read_api_requires_configured_identity(review_app):
    seeded_app, _, bindings = review_app
    app = create_app(Settings(_env_file=None, mode="enterprise", database_url="sqlite://", tokens_json=bindings), engine=seeded_app.state.engine)
    with TestClient(app) as client:
        assert client.get("/api/inventory").status_code == 401
        assert client.get("/api/inventory", headers={"X-Role": "admin"}).status_code == 401
        assert client.get("/api/inventory", headers=token("not-a-configured-token")).status_code == 401
        response = client.get("/api/inventory", headers=token("review-viewer-token"))
        assert response.status_code == 200
        assert response.json()["items"]


def test_invalid_cursor_does_not_create_ingestion_records(review_app):
    app, client, _ = review_app
    response = client.post("/api/integrations/parts/import", json={"records": [part_row()], "cursor": "invalid-cursor"}, headers=token("review-parts-token"))
    assert response.status_code == 422
    with app.state.sessions() as session:
        assert not session.scalars(select(IngestionOriginal)).all()


def test_import_staging_does_not_silently_replace_physical_inventory(review_app):
    _, client, _ = review_app
    before = client.get("/api/inventory").json()["items"]
    response = client.post("/api/integrations/parts/import", json={"records": [part_row()]}, headers=token("review-parts-token"))
    assert response.status_code == 200
    assert "staged" in response.json()["materialization"].lower()
    after = client.get("/api/inventory").json()["items"]
    assert {(item["id"], item["serial_number"], item["position_id"]) for item in before} == {(item["id"], item["serial_number"], item["position_id"]) for item in after}


def test_recording_source_decision_preserves_contested_state_until_materialized(review_app):
    _, client, _ = review_app
    before = client.get("/api/components/cmp-1-a-rf").json()
    assert before["exposure"]["attribution_status"] == "disputed"
    response = client.post("/api/quality/conflict-001/resolve", headers=token("review-parts-token"), json={
        "decision": "accept_b", "note": "Synthetic review chooses tracker claim; physical correction still needs review."
    })
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "decision_recorded_pending_materialization"
    after = client.get("/api/components/cmp-1-a-rf").json()
    assert after["serial_number"] == before["serial_number"]
    assert after["exposure"]["attribution_status"] == "disputed"
    exclusions = client.get("/api/analytics").json()["excluded_components"]
    assert any(item["component_id"] == "cmp-1-a-rf" and item["analysis"] == "rate" for item in exclusions)
