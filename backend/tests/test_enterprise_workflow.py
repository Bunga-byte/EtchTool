"""Reviewed source-to-domain acceptance scenarios A/B/C/G/H/I."""

from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.auth import Principal
from app.config import Settings
from app.main import create_app
from app.models import (
    Installation,
    ComponentInstance,
    FailureEpisode,
    EquipmentEvent,
    MaintenanceAction,
    Evidence,
    PMDueEvent,
    RawSourceRecord,
    SourceConflict,
)
from app.enterprise.models import (
    EnterpriseSource,
    SourceVersion,
    FactProposal,
    EngineeringReview,
    EntityAlias,
)
from app.enterprise.connectors import fixture_connector
from app.enterprise.workflow import stage_document
from app.enterprise.identity import resolve_alias, match_payload, aware
from app.enterprise.telemetry import ingest_telemetry, review_mapping, review_rule
from app.enterprise.models import ComponentSensorMapping, ExposureDefinition

HEADERS = {"Authorization": "Bearer synthetic-workflow-admin"}
ACTOR = Principal("workflow-admin", "admin")


@pytest.fixture
def client(tmp_path):
    config = Settings(
        database_url="sqlite:///" + str(tmp_path / "workflow.db"),
        tokens_json={
            "synthetic-workflow-admin": {"role": "admin", "subject": "workflow-admin"},
            "synthetic-workflow-viewer": {
                "role": "viewer",
                "subject": "workflow-viewer",
                "sources": "maintenance,parts,fdc",
                "equipment": "tool-1",
                "collections": "maintenance,parts,telemetry",
            },
            "synthetic-workflow-scoped-editor": {
                "role": "editor",
                "subject": "tool1-editor",
                "sources": "maintenance",
                "equipment": "tool-1",
                "collections": "maintenance",
            },
            "synthetic-workflow-wrong-equipment": {
                "role": "editor",
                "subject": "other-tool",
                "sources": "maintenance",
                "equipment": "tool-2",
                "collections": "maintenance",
            },
        },
    )
    app = create_app(config)
    with TestClient(app) as c:
        yield c


def stage(client, source_id, original_id, document=None, **kwargs):
    connector = fixture_connector(source_id)
    document = document or connector.get_document(original_id, connector.config.scope)
    with client.app.state.sessions() as session:
        result = stage_document(
            session, session.get(EnterpriseSource, source_id), document, **kwargs
        )
        session.commit()
        return result


def approve(client, id):
    return client.post(
        f"/api/enterprise/proposals/{id}/review",
        json={
            "decision": "approve",
            "note": "Synthetic engineering acceptance review with source evidence",
        },
        headers=HEADERS,
    )


def test_raw_parse_match_staging_never_writes_unapproved_inventory(client):
    result = stage(client, "informs-demo", "syn-replacement-001")
    assert result["status"] == "parsed" and len(result["proposal_ids"]) == 1
    inventory = client.get("/api/inventory?chamber_id=ch-1-a").json()["items"]
    assert "SYN-01A-RF-002" in {i["serial_number"] for i in inventory}
    assert "SYN-01A-RF-003" not in {i["serial_number"] for i in inventory}
    preview = client.get(
        "/api/enterprise/proposals/" + result["proposal_ids"][0] + "/preview"
    ).json()
    assert (
        preview["can_approve"]
        and preview["matched_entities"]["component_id"] == "cmp-enterprise-spare"
    )
    document = preview["document"]
    for spans in preview["proposal"]["evidence"].values():
        for span in spans:
            assert document["text"][span["start"] : span["end"]] == span["quote"]
    assert document["content_b64"] and document["blocks"]


def test_approved_replacement_closes_old_exposure_and_is_idempotent(client):
    result = stage(client, "informs-demo", "syn-replacement-001")
    id = result["proposal_ids"][0]
    response = approve(client, id)
    assert (
        response.status_code == 200
        and response.json()["canonical"]["failure_created"] is False
    )
    old = client.get("/api/components/cmp-1-a-rf").json()
    new = client.get("/api/components/cmp-enterprise-spare").json()
    assert old["removed_at"] == "2026-01-26T00:00:00Z"
    assert old["exposure"]["hours"] == 70 and new["exposure"]["hours"] == 70
    assert new["exposure"]["since_refurbishment"] == 70
    assert new["provenance"]["source"] == "enterprise:informs-demo"
    assert "Synthetic planned exchange" in new["installations"][0]["reason"]
    assert "Synthetic planned exchange" in old["installations"][0]["removal_reason"]
    with client.app.state.sessions() as session:
        before = (
            session.query(Installation).count(),
            session.query(FailureEpisode).count(),
            session.query(MaintenanceAction).count(),
        )
    assert approve(client, id).json()["idempotent"] is True
    replay = stage(client, "informs-demo", "syn-replacement-001")
    assert replay["duplicate"] is True
    with client.app.state.sessions() as session:
        assert before == (
            session.query(Installation).count(),
            session.query(FailureEpisode).count(),
            session.query(MaintenanceAction).count(),
        )
        old_install = session.get(Installation, "ins-cmp-1-a-rf")
        assert old_install.removed_at == aware("2026-01-26T00:00:00Z")


def test_scenario_a_new_installation_uses_known_spare_and_empty_physical_slot(client):
    result = stage(client, "informs-demo", "syn-installation-001")
    response = approve(client, result["proposal_ids"][0])
    assert response.status_code == 200
    detail = client.get("/api/components/cmp-enterprise-install-spare").json()
    assert detail["serial_number"] == "SYN-ENT-INSTALL-001"
    assert detail["position_id"] == "pos-enterprise-empty"
    assert detail["maintenance"][0]["confirmed_failure"] is False
    assert detail["pm"]["basis"] == "synthetic_engineer_recommendation"
    assert detail["exposure"]["hours"] > 0


def test_scenario_c_lam_disagreement_is_preserved_without_overwrite(client):
    replacement = stage(client, "informs-demo", "syn-replacement-001")
    assert approve(client, replacement["proposal_ids"][0]).status_code == 200
    observation = stage(client, "lam-demo", "syn-lam-conflict-001")
    id = observation["proposal_ids"][0]
    preview = client.get(f"/api/enterprise/proposals/{id}/preview").json()
    assert not preview["can_approve"]
    assert any(c["code"] == "inventory_disagreement" for c in preview["conflicts"])
    assert approve(client, id).status_code == 409
    items = client.get("/api/inventory?chamber_id=ch-1-a").json()["items"]
    assert "SYN-01A-RF-003" in {i["serial_number"] for i in items}
    with client.app.state.sessions() as session:
        assert session.get(SourceVersion, replacement["source_version_id"])
        assert session.get(SourceVersion, observation["source_version_id"])


def test_pm_completion_records_history_without_resetting_life_or_inventing_failure(
    client,
):
    result = stage(client, "informs-demo", "syn-pm-001")
    id = result["proposal_ids"][0]
    before = client.get("/api/components/cmp-1-a-valve").json()["exposure"]["hours"]
    response = approve(client, id)
    assert response.status_code == 200
    after = client.get("/api/components/cmp-1-a-valve").json()
    assert before == after["exposure"]["hours"]
    assert after["maintenance"][-1]["action"] == "Reviewed pm"
    assert after["maintenance"][-1]["confirmed_failure"] is False
    with client.app.state.sessions() as session:
        assert session.query(FailureEpisode).count() == 4
        assert session.query(PMDueEvent).count() == 2


def test_scenario_g_evidence_associates_one_existing_episode(client):
    before = client.get("/api/failures/case-001").json()
    result = stage(client, "informs-demo", "syn-failure-evidence-001")
    id = result["proposal_ids"][0]
    response = approve(client, id)
    assert response.status_code == 200
    after = client.get("/api/failures/case-001").json()
    assert len(after["evidence"]) == len(before["evidence"]) + 1
    assert (
        after["status"] == before["status"]
        and after["downtime_hours"] == before["downtime_hours"] == 14
    )
    with client.app.state.sessions() as session:
        assert (
            session.query(FailureEpisode).count() == 4
            and session.query(EquipmentEvent).count() == 9
        )


def test_scenario_h_missing_evidence_requires_correction_and_preserves_original_claim(
    client,
):
    result = stage(client, "informs-demo", "syn-missing-evidence-001")
    id = result["proposal_ids"][0]
    original = client.get(f"/api/enterprise/proposals/{id}").json()["payload"]
    assert approve(client, id).status_code == 409
    corrections = {
        "component_serial": "SYN-01A-RF-003",
        "part_number": "SYN-RF-100-A",
        "installed_at": "2026-01-26T00:00:00Z",
        "removed_at": "2026-01-26T00:00:00Z",
    }
    response = client.post(
        f"/api/enterprise/proposals/{id}/review",
        json={
            "decision": "correct",
            "note": "Synthetic engineer independently verifies missing identity and timestamps",
            "corrections": corrections,
        },
        headers=HEADERS,
    )
    assert response.status_code == 200
    corrected = response.json()["proposal"]
    assert corrected["id"] != id and corrected["supersedes_id"] == id
    assert (
        corrected["status"] == "pending"
        and corrected["extraction_method"] == "human_correction"
    )
    old = client.get(f"/api/enterprise/proposals/{id}").json()
    assert old["payload"] == original and old["status"] == "superseded"
    with client.app.state.sessions() as session:
        assert (
            session.query(Installation)
            .filter(Installation.component_id == "cmp-enterprise-spare")
            .count()
            == 0
        )
        assert (
            session.query(EngineeringReview)
            .filter(EngineeringReview.entity_id == id)
            .count()
            == 1
        )


def test_versioned_originals_reprocessing_and_metadata_disagreements(client):
    connector = fixture_connector("informs-demo")
    doc = connector.get_document("syn-replacement-001", connector.config.scope)
    first = stage(client, "informs-demo", doc.original_id, doc)
    reprocessed = stage(
        client, "informs-demo", doc.original_id, doc, force_reprocess=True
    )
    assert (
        reprocessed["source_version_id"] == first["source_version_id"]
        and reprocessed["proposal_ids"] == first["proposal_ids"]
    )
    revised = doc.model_copy(
        update={"revision": "2", "recorded_at": doc.recorded_at + timedelta(hours=1)}
    )
    second = stage(client, "informs-demo", doc.original_id, revised)
    assert second["source_version_id"] != first["source_version_id"]
    conflict = doc.model_copy(
        update={"effective_at": doc.effective_at + timedelta(hours=1)}
    )
    flagged = stage(client, "informs-demo", doc.original_id, conflict)
    assert flagged["status"] == "metadata_conflict"
    with client.app.state.sessions() as session:
        assert session.query(SourceVersion).count() == 2
        assert (
            session.query(SourceConflict)
            .filter(SourceConflict.field == "source_metadata")
            .count()
            == 1
        )
        assert (
            session.get(SourceVersion, first["source_version_id"]).effective_at
            == doc.effective_at
        )


@pytest.mark.parametrize("field,value", [
    ("chamber_alias", "different-chamber"),
    ("title", "Revised source title without a new revision"),
    ("filename", "renamed-source.txt"),
    ("attachment_ids", ("different-attachment",)),
])
def test_all_metadata_changes_preserve_conflicting_originals(client, field, value):
    connector = fixture_connector("informs-demo")
    original = connector.get_document("syn-replacement-001", connector.config.scope)
    first = stage(client, "informs-demo", original.original_id, original)
    changed = original.model_copy(update={field: value})
    result = stage(client, "informs-demo", changed.original_id, changed)
    assert result["status"] == "metadata_conflict"
    assert result["source_version_id"] == first["source_version_id"]
    with client.app.state.sessions() as session:
        conflicts = session.query(SourceConflict).filter(SourceConflict.field == "source_metadata").all()
        assert len(conflicts) == 1
        assert session.get(SourceVersion, first["source_version_id"]).title == original.title


def test_review_permissions_and_external_data_boundary_fail_closed(client):
    result = stage(client, "informs-demo", "syn-replacement-001")
    id = result["proposal_ids"][0]
    body = {
        "decision": "approve",
        "note": "Engineering review source authorization test",
    }
    assert (
        client.post(f"/api/enterprise/proposals/{id}/review", json=body).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/enterprise/proposals/{id}/review",
            json=body,
            headers={"Authorization": "Bearer synthetic-workflow-viewer"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/enterprise/proposals/{id}/review",
            json=body,
            headers={"Authorization": "Bearer synthetic-workflow-wrong-equipment"},
        ).status_code
        == 403
    )
    connector = fixture_connector("informs-demo")
    doc = connector.get_document(
        "syn-replacement-001", connector.config.scope
    ).model_copy(update={"synthetic": False})
    with pytest.raises(ValueError, match="synthetic"):
        stage(client, "informs-demo", doc.original_id, doc)


def test_conflicting_exact_aliases_never_fall_back_to_canonical_serial(client):
    at = aware("2026-01-26T00:00:00Z")
    with client.app.state.sessions() as session:
        session.add(
            EntityAlias(
                id="ambiguous-rf-component",
                source_id="informs-demo",
                entity_type="component",
                external_id="SYN-01A-RF-003",
                canonical_id="cmp-1-a-rf",
                valid_from=at - timedelta(hours=1),
                valid_to=at + timedelta(hours=1),
                verification_status="verified",
                evidence=[{"test": "ambiguous source association"}],
            )
        )
        session.flush()
        matched, errors = match_payload(
            session, "informs-demo", {"component_serial": "SYN-01A-RF-003"}, at
        )
        assert "component_id" not in matched
        assert errors[0]["code"] == "ambiguous"


def test_scoped_engineer_can_review_uninstalled_spare_but_cannot_correct_to_foreign_serial(
    client,
):
    result = stage(client, "informs-demo", "syn-replacement-001")
    id = result["proposal_ids"][0]
    scoped = {"Authorization": "Bearer synthetic-workflow-scoped-editor"}
    preview = client.get(f"/api/enterprise/proposals/{id}/preview", headers=scoped)
    assert preview.status_code == 200 and preview.json()["can_approve"]
    # Remove the foreign serial first so a bare overlap check would allow reuse.
    # Equipment history authorization must still deny the cross-tool identity.
    with client.app.state.sessions() as session:
        installation = session.get(Installation, "ins-cmp-2-a-rf")
        installation.removed_at = aware("2026-01-24T00:00:00Z")
        session.get(
            ComponentInstance, "cmp-2-a-rf"
        ).disposition = "removed_pending_review"
        session.commit()
    corrections = {
        "component_serial": "SYN-02A-RF-001",
        "part_number": "SYN-RF-100-B",
        "revision": "B",
    }
    response = client.post(
        f"/api/enterprise/proposals/{id}/review",
        json={
            "decision": "correct",
            "note": "Synthetic regression attempt to reuse a foreign tool serial",
            "corrections": corrections,
        },
        headers=scoped,
    )
    assert response.status_code == 403
    with client.app.state.sessions() as session:
        assert session.get(FactProposal, id).status == "pending"
        assert session.query(FactProposal).count() == 1
    approved = client.post(
        f"/api/enterprise/proposals/{id}/review",
        json={
            "decision": "approve",
            "note": "Synthetic approved target-tool spare installation",
        },
        headers=scoped,
    )
    assert approved.status_code == 200
    assert (
        client.get("/api/components/cmp-enterprise-spare").json()["serial_number"]
        == "SYN-01A-RF-003"
    )
