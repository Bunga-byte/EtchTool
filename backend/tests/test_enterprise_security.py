"""Source, identity-time, collection and verified-principal security regressions."""
import base64
import hashlib
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth import Principal
from app.config import Settings
from app.main import create_app
from app.models import RawSourceRecord
from app.enterprise.models import EnterpriseSource, EntityAlias, FactProposal, SourceVersion
from app.enterprise.security import authorize_source


UTC = timezone.utc


@pytest.fixture
def source_app(tmp_path):
    url = f"sqlite:///{tmp_path / 'source-security.db'}"
    prepared = create_app(Settings(_env_file=None, database_url=url))
    with TestClient(prepared):
        pass
    bindings = {
        "source-tool-1": {"subject": "scoped-source-reader", "role": "viewer", "sources": "informs-demo", "equipment": "tool-1", "collections": "maintenance"},
        "source-editor-tool-1": {"subject": "scoped-source-editor", "role": "editor", "sources": "informs-demo", "equipment": "tool-1", "collections": "maintenance"},
        "source-kind-token": {"subject": "transport-is-not-authority", "role": "viewer", "sources": "synthetic_file", "equipment": "tool-1", "collections": "maintenance"},
        "reserved-subject-token": {"subject": "synthetic-anonymous", "role": "editor", "sources": "", "equipment": "", "collections": ""},
        "source-admin": {"subject": "source-administrator", "role": "admin"},
    }
    app = create_app(Settings(_env_file=None, database_url=url, mode="enterprise", tokens_json=bindings), engine=prepared.state.engine)
    with TestClient(app) as client:
        yield app, client
    app.state.engine.dispose()


def headers(token="source-tool-1"):
    return {"Authorization": f"Bearer {token}"}


def test_authorization_resolves_alias_at_evidence_time_not_stale_or_future_rows(source_app):
    app, _ = source_app
    boundary = datetime(2026, 1, 1, tzinfo=UTC)
    actor = Principal("dated-reader", "viewer", sources=("informs-demo",), equipment=("tool-1",), collections=("maintenance",))
    with app.state.sessions() as session:
        old = session.get(EntityAlias, "alias-informs-demo-tool-tool1a")
        old.valid_to = boundary
        session.add(EntityAlias(id="source-security-current-alias", source_id="informs-demo", entity_type="tool", external_id="tool1a", canonical_id="tool-2", valid_from=boundary, valid_to=None, verification_status="verified", evidence=[{"synthetic": True, "note": "Synthetic alias reassignment"}]))
        session.commit()
        source = session.get(EnterpriseSource, "informs-demo")
        historical = authorize_source(session, actor, source, equipment_alias="tool1a", collection="maintenance", at=datetime(2025, 12, 20, tzinfo=UTC))
        assert historical.equipment_aliases == frozenset({"tool1a"})
        with pytest.raises(HTTPException) as denied:
            authorize_source(session, actor, source, equipment_alias="tool1a", collection="maintenance", at=datetime(2026, 1, 20, tzinfo=UTC))
        assert denied.value.status_code == 403


def test_ambiguous_effective_alias_cannot_broaden_canonical_equipment_grant(source_app):
    app, _ = source_app
    actor = Principal("dated-reader", "viewer", sources=("informs-demo",), equipment=("tool-1",), collections=("maintenance",))
    with app.state.sessions() as session:
        old = session.get(EntityAlias, "alias-informs-demo-tool-tool1a")
        old.valid_to = datetime(2026, 2, 1, tzinfo=UTC)
        session.add(EntityAlias(id="source-security-overlapping-alias", source_id="informs-demo", entity_type="tool", external_id="tool1a", canonical_id="tool-2", valid_from=datetime(2026, 1, 1, tzinfo=UTC), valid_to=datetime(2026, 1, 25, tzinfo=UTC), verification_status="verified", evidence=[{"synthetic": True}]))
        session.commit()
        with pytest.raises(HTTPException) as denied:
            authorize_source(session, actor, session.get(EnterpriseSource, "informs-demo"), at=datetime(2026, 1, 20, tzinfo=UTC))
        assert denied.value.status_code == 403


def test_authenticated_reserved_subject_does_not_inherit_anonymous_demo_exception(source_app):
    _, client = source_app
    result = client.get("/api/enterprise/sources/informs-demo/capabilities", headers=headers("reserved-subject-token"))
    assert result.status_code == 403
    submission = client.post("/api/enterprise/jobs", headers=headers("reserved-subject-token"), json={
        "source_id": "informs-demo", "window_start": "2026-01-01T00:00:00Z", "window_end": "2026-02-01T00:00:00Z",
    })
    assert submission.status_code == 403
    assert client.get("/api/enterprise/sources", headers=headers("reserved-subject-token")).json()["items"] == []


def test_connector_transport_kind_is_not_a_source_permission(source_app):
    _, client = source_app
    assert client.get("/api/enterprise/sources/informs-demo/capabilities", headers=headers()).status_code == 200
    assert client.get("/api/enterprise/sources/informs-demo/capabilities", headers=headers("source-kind-token")).status_code == 403
    assert client.get("/api/enterprise/sources", headers=headers("source-kind-token")).json()["items"] == []


def test_alias_catalog_does_not_leak_other_equipment_identity_within_same_source(source_app):
    app, client = source_app
    with app.state.sessions() as session:
        source = session.get(EnterpriseSource, "informs-demo")
        source.authorized_equipment = ["tool1a", "tool2a"]
        for suffix, kind, external, target in (
            ("tool", "tool", "PRIVATE-TOOL2-ALIAS", "tool-2"),
            ("chamber", "chamber", "PRIVATE-CHAMBER2-ALIAS", "ch-2-a"),
            ("component", "component", "PRIVATE-SERIAL2-ALIAS", "cmp-2-a-rf"),
        ):
            session.add(EntityAlias(id="source-security-hidden-" + suffix, source_id="informs-demo", entity_type=kind, external_id=external, canonical_id=target, valid_from=datetime(2025, 12, 1, tzinfo=UTC), valid_to=None, verification_status="verified", evidence=[{"synthetic": True, "note": "PRIVATE-TOOL2-EVIDENCE"}]))
        session.commit()
    response = client.get("/api/enterprise/aliases?source_id=informs-demo", headers=headers())
    assert response.status_code == 200, response.text
    assert response.json()["items"]
    assert "PRIVATE-" not in response.text
    assert "cmp-2-a-rf" not in response.text
    assert "ch-2-a" not in response.text
    assert "tool-2" not in response.text


def test_document_collection_scope_applies_to_original_download_and_listing(source_app):
    app, client = source_app
    at = datetime(2026, 1, 20, tzinfo=UTC)
    content = b"PRIVATE-PROCEDURE-CONTENT synthetic only"
    with app.state.sessions() as session:
        session.add(RawSourceRecord(id="source-security-procedure-raw", source="informs-demo", source_id="PRIVATE-PROCEDURE-ORIGINAL", recorded_at=at, effective_at=at, ingested_at=at, payload={"synthetic": True}, fingerprint=hashlib.sha256(content).hexdigest(), quality="synthetic", verification="synthetic_only"))
        session.flush()
        session.add(SourceVersion(id="source-security-procedure", source_id="informs-demo", raw_record_id="source-security-procedure-raw", original_id="PRIVATE-PROCEDURE-ORIGINAL", revision="SYN-1", content_hash=hashlib.sha256(content).hexdigest(), mime_type="text/plain", content_b64=base64.b64encode(content).decode(), title="PRIVATE-PROCEDURE-TITLE", equipment_alias="tool1a", collection="procedures", recorded_at=at, effective_at=at, ingested_at=at, parser_version="synthetic-security-test", parse_status="parsed", structured_payload={}))
        session.commit()
    direct = client.get("/api/enterprise/documents/source-security-procedure", headers=headers())
    assert direct.status_code == 403
    assert "PRIVATE-" not in direct.text
    listed = client.get("/api/enterprise/documents?source_id=informs-demo", headers=headers())
    assert listed.status_code == 200
    assert "PRIVATE-" not in listed.text
    admin = client.get("/api/enterprise/documents/source-security-procedure", headers=headers("source-admin"))
    assert admin.status_code == 200
    assert admin.json()["content_b64"] == base64.b64encode(content).decode()


def test_server_installed_identity_provider_enforces_equipment_and_export_claims(source_app):
    app, client = source_app

    class ApprovedInternalProvider:
        def verify_bearer(self, token):
            if token not in {"verified-reader", "verified-exporter"}:
                raise ValueError("Do not expose internal identity diagnostics")
            return Principal("verified-corporate-subject", "viewer", sources=("informs-demo",), equipment=("tool-1",), collections=("maintenance",), export_allowed=token == "verified-exporter")

    app.state.authentication_provider = ApprovedInternalProvider()
    inventory = client.get("/api/inventory", headers=headers("verified-reader"))
    assert inventory.status_code == 200
    assert {item["tool_id"] for item in inventory.json()["items"]} == {"tool-1"}
    assert client.get("/api/components/cmp-2-a-rf", headers={**headers("verified-reader"), "X-Role": "admin", "X-Equipment": "tool-2"}).status_code == 403
    assert client.get("/api/export/inventory.csv", headers=headers("verified-reader")).status_code == 403
    exported = client.get("/api/export/inventory.csv", headers=headers("verified-exporter"))
    assert exported.status_code == 200 and "SYN-FLEX-02" not in exported.text
    denied = client.get("/api/inventory", headers=headers("unknown-provider-token"))
    assert denied.status_code == 401
    assert "internal identity diagnostics" not in denied.text


def test_identity_provider_cannot_mark_authenticated_principal_as_anonymous_demo(source_app):
    app, client = source_app

    class InvalidProvider:
        def verify_bearer(self, token):
            return Principal("synthetic-anonymous", "editor", anonymous_demo=True)

    app.state.authentication_provider = InvalidProvider()
    assert client.get("/api/enterprise/sources/informs-demo/capabilities", headers=headers("any-provider-token")).status_code == 401


def test_proposal_previews_and_cached_matches_cannot_expose_foreign_canonical_identity(source_app):
    app, client = source_app
    at = datetime(2026, 1, 24, tzinfo=UTC)
    content = b"Synthetic authorized tool1 document with a subsequent human correction"
    payload = {"kind": "installation", "tool_alias": "tool1a", "chamber_alias": "ch1a", "position_alias": "rf1a", "component_serial": "SYN-02A-RF-001", "part_number": "SYN-RF-100-B", "installed_at": "2026-01-24T00:00:00Z"}
    with app.state.sessions() as session:
        session.add(RawSourceRecord(id="foreign-proposal-raw", source="informs-demo", source_id="SYN-FOREIGN-PROPOSAL", recorded_at=at, effective_at=at, ingested_at=at, payload={"synthetic": True}, fingerprint=hashlib.sha256(content).hexdigest(), quality="synthetic", verification="synthetic_only"))
        session.flush()
        session.add(SourceVersion(id="foreign-proposal-version", source_id="informs-demo", raw_record_id="foreign-proposal-raw", original_id="SYN-FOREIGN-PROPOSAL", revision="SYN-1", content_hash=hashlib.sha256(content).hexdigest(), mime_type="text/plain", content_b64=base64.b64encode(content).decode(), title="Synthetic proposal with foreign corrected serial", equipment_alias="tool1a", collection="maintenance", recorded_at=at, effective_at=at, ingested_at=at, parser_version="synthetic-security-test", parse_status="parsed", structured_payload={}))
        session.flush()
        session.add(FactProposal(id="foreign-proposal", source_version_id="foreign-proposal-version", kind="installation", payload=payload, evidence={}, extraction_method="human_correction", extraction_version="synthetic-security-test", confidence=0.8, status="pending", match_status="matched", matched_entities={"tool_id": "tool-1", "component_id": "cmp-2-a-rf", "position_id": "pos-ch-1-a-rf", "foreign_installation_id": "ins-cmp-2-a-rf"}, validation_errors=[], created_at=at, proposal_hash=hashlib.sha256(content + b"proposal").hexdigest()))
        session.commit()
    for endpoint in ("/api/enterprise/proposals/foreign-proposal", "/api/enterprise/proposals/foreign-proposal/preview"):
        response = client.get(endpoint, headers=headers("source-editor-tool-1"))
        assert response.status_code == 403, (endpoint, response.text)
        assert "cmp-2-a-rf" not in response.text
    approval = client.post("/api/enterprise/proposals/foreign-proposal/review", headers=headers("source-editor-tool-1"), json={"decision": "approve", "note": "Synthetic review attempts to use another equipment's serial"})
    assert approval.status_code == 403, approval.text
    for endpoint in ("/api/enterprise/proposals?source_id=informs-demo", "/api/enterprise/documents/foreign-proposal-version"):
        response = client.get(endpoint, headers=headers("source-editor-tool-1"))
        assert response.status_code in {200, 403}
        assert "cmp-2-a-rf" not in response.text and "ins-cmp-2-a-rf" not in response.text


def test_legacy_import_path_cannot_bypass_enterprise_equipment_and_collection_controls(source_app):
    app, client = source_app
    with app.state.sessions() as session:
        originals_before = session.query(RawSourceRecord).count()
    response = client.post("/api/integrations/parts/import", headers=headers("source-editor-tool-1"), json={"records": [{
        "source_id": "SYN-LEGACY-FOREIGN-IMPORT", "recorded_at": "2026-01-24T00:00:00Z", "effective_at": "2026-01-24T00:00:00Z",
        "equipment_id": "tool-2", "chamber_id": "ch-2-a", "synthetic": True,
        "component_serial": "SYN-02A-RF-001", "part_number": "SYN-RF-100-B", "position_id": "pos-ch-2-a-rf", "installed_at": "2026-01-24T00:00:00Z",
    }]})
    assert response.status_code == 409
    assert "enterprise" in response.json()["detail"].lower()
    with app.state.sessions() as session:
        assert session.query(RawSourceRecord).count() == originals_before
    status = client.get("/api/integrations", headers=headers())
    assert status.status_code == 200
    assert status.json()["items"] == []
    assert status.json()["legacy_imports_enabled"] is False
    assert "record_count" not in status.text and "errors" not in status.text
