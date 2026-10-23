"""Integration checks exercise database, HTTP authorization and engineering read models."""

from datetime import datetime, timezone
from pathlib import Path
from copy import deepcopy
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.main import create_app
from app.config import Settings
from app.db import make_engine
from app.models import *
from app.seed import AS_OF, seed
from app import views


@pytest.fixture
def client(tmp_path):
    config = Settings(
        database_url="sqlite:///" + str(tmp_path / "test.db"),
        tokens_json={
            "editor-secret": {"role": "editor", "subject": "editor"},
            "analyst-secret": {"role": "analyst", "subject": "analyst"},
            "admin-secret": {"role": "admin", "subject": "admin"},
        },
    )
    app = create_app(config)
    with TestClient(app) as c:
        yield c


def editor():
    return {"Authorization": "Bearer editor-secret"}


def analyst():
    return {"Authorization": "Bearer analyst-secret"}


def admin():
    return {"Authorization": "Bearer admin-secret"}


def test_complete_read_workflow(client):
    fleet = client.get("/api/fleet").json()
    assert fleet["metrics"]["tools"] == 3
    assert fleet["metrics"]["chambers"] == 6
    assert fleet["metrics"]["installed_components"] == 18
    assert fleet["metrics"]["pm_due"] > 0
    inventory = client.get("/api/inventory", params={"chamber_id": "ch-1-a"}).json()[
        "items"
    ]
    assert len(inventory) == 3
    rf = next(i for i in inventory if i["id"] == "cmp-1-a-rf")
    assert rf["exposure"]["hours"] == 140
    assert rf["exposure"]["attribution_status"] == "disputed"
    detail = client.get("/api/components/" + rf["id"]).json()
    assert detail["replacements"][0]["old_component_id"] == "cmp-1-a-rf-old"
    assert detail["specifications"][0]["nominal"] is None
    assert detail["specifications"][0]["verification_status"] == "pending_verification"
    assert detail["forecast"]["eligible"] is False
    assert (
        detail["forecast"]["message"]
        == "Insufficient evidence for reliable failure prediction."
    )
    case = client.get("/api/failures/case-001").json()
    assert len(case["alarms"]) == 2 and len(case["evidence"]) == 1
    assert case["downtime_hours"] == 14
    assert len(case["hypotheses"]) == 2


def test_historical_inventory_and_replacement_boundary(client):
    before = client.get(
        "/api/inventory", params={"chamber_id": "ch-1-a", "at": "2026-01-20T23:59:59Z"}
    ).json()["items"]
    after = client.get(
        "/api/inventory", params={"chamber_id": "ch-1-a", "at": "2026-01-21T00:00:00Z"}
    ).json()["items"]
    assert "cmp-1-a-rf-old" in {i["id"] for i in before}
    old = next(i for i in before if i["id"] == "cmp-1-a-rf-old")
    assert (
        old["exposure"]["confidence"] == "complete"
    )  # Jan21 disagreement cannot contaminate Jan20 facts.
    assert "cmp-1-a-rf" not in {i["id"] for i in before}
    new = next(i for i in after if i["id"] == "cmp-1-a-rf")
    assert new["exposure"]["hours"] == 0
    assert "cmp-1-a-rf-old" not in {i["id"] for i in after}
    assert client.get("/api/inventory?at=2026-01-20T00:00:00").status_code == 422


def test_removed_serial_stops_accrual(client):
    with client.app.state.sessions() as session:
        old = session.get(ComponentInstance, "cmp-1-a-rf-old")
        before = views.exposure_for(
            session, old, datetime(2026, 1, 21, tzinfo=timezone.utc)
        )
        after = views.exposure_for(
            session, old, datetime(2026, 2, 20, tzinfo=timezone.utc)
        )
        assert before["lifetime_hours"] == after["lifetime_hours"] == 714


def test_incomplete_observations_are_visible_and_excluded_from_cohort(client):
    item = client.get("/api/components/cmp-3-b-rf").json()
    assert 0 < item["exposure"]["completeness"] < 1
    assert item["exposure"]["confidence"] == "limited"
    assert item["pm"]["status"] == "unknown"
    analysis = client.get("/api/analytics").json()
    assert analysis["rate"]["failures"] == 1
    assert analysis["rate"]["exposure_hours"] == 3846
    assert any(
        i["component_id"] == "cmp-3-b-rf" for i in analysis["excluded_components"]
    )
    assert "cmp-3-b-rf" not in {o["component_id"] for o in analysis["observations"]}
    assert analysis["weibull"]["eligible"] is False
    assert any(not o["event"] for o in analysis["observations"])


def test_pm_basis_exposure_dimensions_and_no_false_failure_from_maintenance(client):
    items = client.get("/api/pm").json()["items"]
    assert any(i["pm"]["status"] == "overdue" for i in items)
    assert any(i["pm"]["status"] == "upcoming" for i in items)
    assert any(i["exposure"]["dimension"] == "powered_hours" for i in items)
    assert all(i["pm"]["basis"] == "synthetic_engineer_recommendation" for i in items)
    details = client.get("/api/components/cmp-2-b-valve").json()
    assert details["maintenance"][0]["confirmed_failure"] is False
    assert not details["failures"]
    failures = client.get("/api/failures").json()
    assert failures["alarm_only_events"] == 1
    assert len(failures["items"]) == 4
    assert sum(i["status"] == "confirmed" for i in failures["items"]) == 3


def test_downtime_aggregation_uses_exclusive_time_and_unconfirmed_remains_unattributed(
    client,
):
    data = client.get("/api/analytics").json()["downtime"]
    assert data["total_hours"] == 27
    assert data["attributed_hours"] == 24
    assert data["unattributed_hours"] == 3
    assert sum(i["hours"] for i in data["downtime_by_subsystem"]) == 27


def test_lifecycle_authorization_and_integrity(client):
    remove = {
        "removed_at": "2026-01-30T00:00:00Z",
        "reason": "Synthetic inspection removal",
    }
    path = "/api/installations/ins-cmp-1-b-rf/remove"
    assert client.post(path, json=remove).status_code == 403
    assert (
        client.post(path, json=remove, headers={"X-Role": "admin"}).status_code == 403
    )
    assert client.post(path, json=remove, headers=analyst()).status_code == 403
    assert (
        client.post(
            path, json=remove, headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            path,
            json={**remove, "removed_at": "2025-01-01T00:00:00Z"},
            headers=editor(),
        ).status_code
        == 422
    )
    assert (
        client.post(
            path, json={**remove, "removed_at": "2026-01-30T00:00:00"}, headers=editor()
        ).status_code
        == 422
    )
    r = client.post(path, json=remove, headers=editor())
    assert r.status_code == 200 and r.json()["failure_created"] is False
    assert client.post(path, json=remove, headers=editor()).status_code == 409
    before = client.get("/api/components/cmp-1-b-rf").json()["exposure"]["hours"]
    assert before == 900  # Dec1 through Jan29 inclusive, 15 RF hours/day.
    install = {
        "component_id": "cmp-1-b-rf",
        "position_id": "pos-ch-1-b-rf",
        "installed_at": "2026-01-29T00:00:00Z",
        "reason": "Synthetic reinstallation",
    }
    assert (
        client.post("/api/installations", json=install, headers=editor()).status_code
        == 409
    )
    install["installed_at"] = "2026-01-30T00:00:00Z"
    r = client.post("/api/installations", json=install, headers=editor())
    assert r.status_code == 201
    detail = client.get("/api/components/cmp-1-b-rf").json()
    assert len(detail["installations"]) == 2
    assert detail["exposure"]["hours"] == 15
    assert detail["exposure"]["lifetime_hours"] == 915
    assert (
        detail["installations"][0]["removal_provenance"]["source"] == "synthetic_editor"
    )
    assert (
        client.post("/api/installations", json=install, headers=editor()).status_code
        == 409
    )


def test_db_active_uniqueness_prevents_bypassing_api(client):
    with client.app.state.sessions() as session:
        existing = session.get(Installation, "ins-cmp-1-b-rf")
        session.add(
            Installation(
                id="bad-overlap",
                component_id=existing.component_id,
                position_id="pos-ch-2-a-rf",
                installed_at=AS_OF,
                removed_at=None,
                reason="Invalid direct database overlap",
                source_record_id=existing.source_record_id,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_reconciliation_and_adjudication_preserve_originals_and_audit(client):
    assert (
        client.post(
            "/api/quality/conflict-001/resolve",
            json={"decision": "accept_a", "note": "Review favors maintenance record"},
        ).status_code
        == 403
    )
    with client.app.state.sessions() as session:
        before = {
            r.id: deepcopy(r.payload) for r in session.scalars(select(RawSourceRecord))
        }
    r = client.post(
        "/api/quality/conflict-001/resolve",
        json={"decision": "accept_a", "note": "Review favors maintenance record"},
        headers=editor(),
    )
    assert r.status_code == 200 and r.json()["raw_records_preserved"]
    assert (
        client.get("/api/quality").json()["items"][0]["status"]
        == "decision_recorded_pending_materialization"
    )
    assert (
        client.get("/api/components/cmp-1-a-rf").json()["exposure"][
            "attribution_status"
        ]
        == "disputed"
    )
    r = client.post(
        "/api/failures/case-003/adjudicate",
        json={
            "status": "unconfirmed",
            "note": "No physical evidence establishes hardware failure",
        },
        headers=analyst(),
    )
    assert r.status_code == 200 and r.json()["status"] == "unconfirmed"
    with client.app.state.sessions() as session:
        after = {
            r.id: deepcopy(r.payload) for r in session.scalars(select(RawSourceRecord))
        }
        assert before == after
    assert client.get("/api/audit").status_code == 403
    actions = {
        r["action"] for r in client.get("/api/audit", headers=admin()).json()["items"]
    }
    assert {"resolve_source_conflict", "adjudicate_failure"} <= actions


def test_fdc_points_match_original_and_precede_event(client):
    with client.app.state.sessions() as session:
        for p in session.scalars(select(FDCPoint)):
            original = session.get(RawSourceRecord, p.source_record_id)
            episode = session.get(FailureEpisode, original.payload["case_id"])
            assert original.payload["value"] == p.value
            assert original.payload["cohort"] == p.cohort
            assert original.effective_at == p.timestamp < episode.started_at


def test_refurbishment_preserves_lifetime_and_resets_relevant_baseline(client):
    part = client.get("/api/components/cmp-2-a-rf").json()
    assert part["exposure"]["hours"] == 976
    assert part["exposure"]["since_refurbishment"] == 480
    assert part["exposure"]["lifetime_hours"] == 976


def test_read_only_enterprise_auth_fails_closed(tmp_path):
    with pytest.raises(ValueError):
        Settings(mode="enterprise", tokens_json={})
    config = Settings(
        database_url="sqlite:///" + str(tmp_path / "enterprise.db"),
        mode="enterprise",
        tokens_json={"read-token": {"subject": "viewer", "role": "viewer"}},
    )
    app = create_app(config)
    with TestClient(app) as c:
        assert c.get("/api/hierarchy").status_code == 401
        assert c.get("/api/health").status_code == 401
        assert c.get("/healthz").status_code == 200
        assert c.get("/healthz").json() == {"status": "ok"}


def test_seed_repeatability_and_csv_export(client):
    with client.app.state.sessions() as session:
        count = session.query(ComponentInstance).count()
        assert seed(session) is False
        assert session.query(ComponentInstance).count() == count
    csv = client.get("/api/export/inventory.csv?chamber_id=ch-1-a")
    assert csv.status_code == 200 and len(csv.text.strip().splitlines()) == 4
    assert "RF h" in csv.text and "True" in csv.text


def test_invalid_ids_and_body_limits(client):
    assert client.get("/api/components/missing").status_code == 404
    assert client.get("/api/failures/missing").status_code == 404
    assert (
        client.post(
            "/api/installations", json={"component_id": "x"}, headers=editor()
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/integrations/parts/import",
            content=b"x" * 5_000_001,
            headers={
                "Authorization": "Bearer editor-secret",
                "Content-Type": "application/json",
            },
        ).status_code
        == 413
    )


def test_same_source_identity_correction_retains_both_conflicting_originals(client):
    fixture = Path(__file__).resolve().parents[2] / "fixtures" / "parts.json"
    records = json.loads(fixture.read_text())
    original = records[0]
    changed = {
        **original,
        "position_id": "SYN-ALTERNATE-POSITION",
        "component_serial": "SYN-ALTERNATE-SERIAL",
    }
    assert (
        client.post(
            "/api/integrations/parts/import",
            json={"records": [original]},
            headers=editor(),
        ).status_code
        == 200
    )
    response = client.post(
        "/api/integrations/parts/import", json={"records": [changed]}, headers=editor()
    )
    assert response.status_code == 200
    conflict = next(
        c for c in response.json()["conflicts"] if c["field"] == "position_id"
    )
    assert (
        conflict["current_source_id"]
        == conflict["incoming_source_id"]
        == original["source_id"]
    )
    with client.app.state.sessions() as session:
        conflict = session.scalar(
            select(SourceConflict).where(SourceConflict.field == "position_id")
        )
        assert conflict is not None
        previous = session.get(RawSourceRecord, conflict.record_a_id)
        incoming = session.get(RawSourceRecord, conflict.record_b_id)
        assert previous.payload["position_id"] == original["position_id"]
        assert incoming.payload["position_id"] == changed["position_id"]


@pytest.mark.parametrize("model", [ExposureInterval, DowntimeInterval])
def test_database_rejects_reversed_exposure_and_downtime_intervals(client, model):
    with client.app.state.sessions() as session:
        original = session.scalar(select(model))
        payload = {
            column.name: getattr(original, column.name)
            for column in model.__table__.columns
        }
        payload.update(
            id="invalid-reversed-time", start=original.end, end=original.start
        )
        session.add(model(**payload))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
