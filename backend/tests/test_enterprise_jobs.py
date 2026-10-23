from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import Principal
from app.config import Settings
from app.db import make_engine
from app.main import create_app
from app.enterprise.connectors import SyntheticFileConnector, fixture_connector
from app.enterprise.contracts import PermanentConnectorError, metadata_version_token
from app.enterprise.models import (
    DeadLetter,
    EnterpriseSource,
    SourceVersion,
    SyncCheckpoint,
    SyncJob,
)
from app.enterprise.orchestrator import (
    create_job,
    enqueue_due_sources,
    retry_job,
    run_job,
)

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 2, 1, tzinfo=timezone.utc)
ADMIN = Principal("job-test", "admin")


@pytest.fixture
def prepared(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'jobs.db'}")
    config = Settings(
        database_url=str(engine.url),
        tokens_json={"synthetic-admin-test": {"role": "admin", "subject": "job-test"}},
    )
    with TestClient(create_app(config, engine)) as client:
        yield client, engine
    engine.dispose()


def make_job(session, **kwargs):
    job = create_job(
        session,
        "informs-demo",
        ADMIN,
        window_start=START,
        window_end=END,
        query=kwargs.pop("query", {"original_ids": ["syn-replacement-001"]}),
        **kwargs,
    )
    session.commit()
    return job


def test_bounded_jobs_stage_unchanged_versions_and_checkpoint(prepared):
    _, engine = prepared
    with Session(engine, expire_on_commit=False) as session:
        job = make_job(session)
        run_job(session, job.id, ADMIN)
        assert job.status == "succeeded", job.error
        assert job.metrics["processed"] == 1
        assert session.scalar(select(func.count()).select_from(SourceVersion)) == 1
        checkpoint = session.scalar(
            select(SyncCheckpoint).where(SyncCheckpoint.job_id == job.id)
        )
        assert checkpoint and '"complete": true' in checkpoint.cursor
        replay = make_job(session, kind="incremental")
        run_job(session, replay.id, ADMIN)
        assert replay.status == "succeeded"
        assert replay.metrics["processed"] == 0
        assert replay.metrics["unchanged"] == 1
        assert session.scalar(select(func.count()).select_from(SourceVersion)) == 1


def test_partial_page_failure_rolls_back_versions_and_checkpoint_then_resumes(prepared):
    _, engine = prepared
    base = fixture_connector()

    class Failing:
        config = base.config

        def capabilities(self):
            return base.capabilities()

        def search(self, query, scope):
            return base.search(query, scope)

        def get_document(self, id, scope):
            if id == "syn-replacement-001":
                raise TimeoutError("synthetic transport outage")
            return base.get_document(id, scope)

    now = datetime(2026, 10, 22, tzinfo=timezone.utc)
    with Session(engine, expire_on_commit=False) as session:
        job = make_job(
            session, query={"original_ids": ["syn-pm-001", "syn-replacement-001"]}
        )
        run_job(session, job.id, ADMIN, connector_factory=lambda _: Failing(), now=now)
        assert job.status == "retry_wait"
        assert job.next_attempt_at == now + timedelta(seconds=2)
        assert session.scalar(select(func.count()).select_from(SourceVersion)) == 0
        assert session.scalar(select(func.count()).select_from(SyncCheckpoint)) == 0
        with pytest.raises(HTTPException) as early:
            run_job(session, job.id, ADMIN, now=now + timedelta(seconds=1))
        assert early.value.status_code == 409
        run_job(session, job.id, ADMIN, now=now + timedelta(seconds=2))
        assert job.status == "succeeded", job.error
        assert session.scalar(select(func.count()).select_from(SourceVersion)) == 2


def test_incremental_metadata_only_correction_reaches_conflict_review(prepared):
    _, engine = prepared
    base = fixture_connector("fdc-demo")
    original = base.get_document("syn-fdc-001",base.config.scope)
    corrected = original.model_copy(update={"effective_at":original.effective_at+timedelta(hours=1)})
    changed = SyntheticFileConnector(base.config,[corrected])
    from app.models import SourceConflict
    from app.enterprise.models import SensorSample

    with Session(engine,expire_on_commit=False) as session:
        first=create_job(session,"fdc-demo",ADMIN,window_start=START,window_end=END)
        session.commit()
        run_job(session,first.id,ADMIN)
        assert first.status=="succeeded",first.error
        version=session.scalar(select(SourceVersion).where(SourceVersion.source_id=="fdc-demo"))
        original_raw=version.raw_record_id
        sample_count=session.scalar(select(func.count()).select_from(SensorSample))
        incremental=create_job(session,"fdc-demo",ADMIN,kind="incremental",window_start=START,window_end=END)
        session.commit()
        run_job(session,incremental.id,ADMIN,connector_factory=lambda _:changed)
        assert incremental.status=="succeeded_with_errors",incremental.error
        assert incremental.metrics["unchanged"]==0
        assert incremental.metrics["rejected"]==1 and incremental.metrics["processed"]==0
        letter=session.scalar(select(DeadLetter).where(DeadLetter.job_id==incremental.id))
        assert letter.error_code=="metadata_conflict" and letter.resolved_at is None
        conflict=session.scalar(select(SourceConflict).where(SourceConflict.record_a_id==original_raw,SourceConflict.field=="source_metadata"))
        assert conflict is not None and conflict.status=="unresolved"
        assert version.raw_record_id==original_raw
        assert session.scalar(select(func.count()).select_from(SourceVersion))==1
        assert session.scalar(select(func.count()).select_from(SensorSample))==sample_count


def test_missing_retained_metadata_omits_cache_hint_and_retrieves(prepared):
    _, engine=prepared
    base=fixture_connector()
    from app.models import RawSourceRecord
    captured=[]

    class Capture:
        config=base.config
        def capabilities(self):return base.capabilities()
        def incremental(self,query,scope):
            captured.append(query.known_versions)
            return base.incremental(query,scope)
        def get_document(self,id,scope):return base.get_document(id,scope)

    with Session(engine,expire_on_commit=False) as session:
        job=make_job(session)
        run_job(session,job.id,ADMIN)
        version=session.scalar(select(SourceVersion))
        raw=session.get(RawSourceRecord,version.raw_record_id)
        # Emulate an incomplete historical envelope; never manufacture a body-only token.
        raw.payload={key:value for key,value in raw.payload.items() if key!="document"}
        session.commit()
        replay=make_job(session,kind="incremental")
        run_job(session,replay.id,ADMIN,connector_factory=lambda _:Capture())
        assert captured==[{}]
        assert replay.metrics["discovered"]==1 and replay.metrics["unchanged"]==0


def test_permanent_failure_dead_letters_and_authorized_retry(prepared):
    _, engine = prepared
    with Session(engine, expire_on_commit=False) as session:
        job = make_job(session)

        def fail(_):
            raise PermanentConnectorError("synthetic missing approved source")

        run_job(session, job.id, ADMIN, connector_factory=fail)
        assert job.status == "dead_letter"
        assert session.scalar(select(func.count()).select_from(DeadLetter)) == 1
        retry_job(session, job.id, ADMIN)
        session.commit()
        run_job(session, job.id, ADMIN)
        assert job.status == "succeeded", job.error


def test_run_claim_rejects_active_lease_and_uses_page_checkpoints(prepared):
    _, engine = prepared
    with Session(engine, expire_on_commit=False) as session:
        job = make_job(
            session, query={"limit": 1, "original_ids": ["syn-replacement-001"]}
        )
        now = datetime.now(timezone.utc)
        job.status, job.started_at, job.next_attempt_at = (
            "running",
            now,
            now + timedelta(seconds=120),
        )
        session.commit()
        with pytest.raises(HTTPException) as busy:
            run_job(session, job.id, ADMIN, now=now)
        assert busy.value.status_code == 409
        for _ in range(10):
            run_job(session, job.id, ADMIN, now=now + timedelta(seconds=121))
            if job.status != "pending":
                break
        assert job.status == "succeeded", job.error
        assert job.metrics["pages"] >= 2
        assert session.scalar(select(func.count()).select_from(SourceVersion)) == 1


def test_retrieval_envelope_cannot_change_equipment_or_collection(prepared):
    _, engine = prepared
    base = fixture_connector()

    class Drift:
        config = base.config

        def capabilities(self):
            return base.capabilities()

        def search(self, query, scope):
            return base.search(query, scope)

        def get_document(self, id, scope):
            return base.get_document(id, scope).model_copy(
                update={"collection": "forbidden"}
            )

    with Session(engine, expire_on_commit=False) as session:
        job = make_job(session)
        run_job(session, job.id, ADMIN, connector_factory=lambda _: Drift())
        assert job.status == "dead_letter"
        assert session.scalar(select(func.count()).select_from(SourceVersion)) == 0


def test_reprocessing_metadata_conflict_is_rejected_and_remains_unresolved(prepared):
    _, engine = prepared
    base = fixture_connector("fdc-demo")

    class Drift:
        config = base.config

        def capabilities(self):
            return base.capabilities()

        def get_document(self, id, scope):
            doc = base.get_document(id, scope)
            return doc.model_copy(
                update={"effective_at": doc.effective_at + timedelta(hours=1)}
            )

        def search(self, query, scope):
            page = base.search(query, scope)
            return page.model_copy(
                update={
                    "items": [
                        self.get_document(item.original_id, scope).metadata()
                        for item in page.items
                    ]
                }
            )

    with Session(engine, expire_on_commit=False) as session:
        first = create_job(
            session, "fdc-demo", ADMIN, window_start=START, window_end=END
        )
        session.commit()
        run_job(session, first.id, ADMIN)
        assert first.status == "succeeded"
        from app.enterprise.models import SensorSample

        sample_count = session.scalar(select(func.count()).select_from(SensorSample))
        reprocess = create_job(
            session,
            "fdc-demo",
            ADMIN,
            kind="reprocess",
            window_start=START,
            window_end=END,
        )
        session.commit()
        run_job(session, reprocess.id, ADMIN, connector_factory=lambda _: Drift())
        assert reprocess.status == "succeeded_with_errors"
        assert (
            reprocess.metrics["rejected"] == 1 and reprocess.metrics["processed"] == 0
        )
        letter = session.scalar(
            select(DeadLetter).where(DeadLetter.job_id == reprocess.id)
        )
        assert letter.error_code == "metadata_conflict" and letter.resolved_at is None
        assert (
            session.scalar(select(func.count()).select_from(SensorSample))
            == sample_count
        )
        assert session.scalar(select(func.count()).select_from(SourceVersion)) == 1


def test_connector_deduplication_metadata_obeys_query_and_actor_scope(prepared):
    _, engine = prepared
    from app.enterprise.workflow import stage_document

    base = fixture_connector()
    captured = []

    class Capture:
        config = base.config

        def capabilities(self):
            return base.capabilities()

        def incremental(self, query, scope):
            captured.append(query.known_versions)
            return base.incremental(query, scope)

        def get_document(self, id, scope):
            return base.get_document(id, scope)

    with Session(engine, expire_on_commit=False) as session:
        source = session.get(EnterpriseSource, "informs-demo")
        for id in ("syn-replacement-001", "syn-procedure-001"):
            stage_document(session, source, base.get_document(id, base.config.scope))
        session.commit()
        scoped_actor = Principal(
            "limited-editor",
            "editor",
            sources=("informs-demo",),
            equipment=("tool-1",),
            collections=("maintenance",),
        )
        job = create_job(
            session,
            "informs-demo",
            scoped_actor,
            kind="incremental",
            window_start=START,
            window_end=END,
            query={"original_ids": ["syn-replacement-001"]},
        )
        session.commit()
        run_job(session, job.id, scoped_actor, connector_factory=lambda _: Capture())
        assert job.status == "succeeded", job.error
        assert set(captured[0]) == {"syn-replacement-001"}
        retained=base.get_document("syn-replacement-001",base.config.scope).metadata()
        assert captured[0][retained.original_id]==metadata_version_token(retained)


def test_source_cannot_expand_a_narrow_job_collection(prepared):
    _, engine = prepared
    base = fixture_connector()
    from app.enterprise.contracts import DocumentPage

    class Expanded:
        config = base.config

        def capabilities(self):
            return base.capabilities()

        def search(self, query, scope):
            assert scope.collections == frozenset({"maintenance"})
            # An erroneous adapter returns a record that the user did not request.
            doc = base.get_document("syn-procedure-001", base.config.scope)
            return DocumentPage(
                items=[doc.metadata()],
                next_cursor=None,
                unchanged_count=0,
                snapshot="synthetic-expanded-scope",
            )

        def get_document(self, id, scope):
            pytest.fail("Out-of-query content must be rejected before retrieval")

    with Session(engine, expire_on_commit=False) as session:
        job = make_job(session, query={"collections": ["maintenance"]})
        run_job(session, job.id, ADMIN, connector_factory=lambda _: Expanded())
        assert job.status == "dead_letter"
        assert session.scalar(select(func.count()).select_from(SourceVersion)) == 0


def test_polling_opt_in_and_jobs_api_authorization(prepared):
    client, engine = prepared
    payload = {
        "source_id": "informs-demo",
        "window_start": START.isoformat(),
        "window_end": END.isoformat(),
    }
    assert client.post("/api/enterprise/jobs", json=payload).status_code == 403
    bad = client.post(
        "/api/enterprise/jobs",
        json={**payload, "window_end": "2028-01-01T00:00:00Z"},
        headers={"Authorization": "Bearer synthetic-admin-test"},
    )
    assert bad.status_code == 422
    with Session(engine) as session:
        assert enqueue_due_sources(session, ADMIN) == []
        assert session.scalar(select(func.count()).select_from(SyncJob)) == 0
        source = session.get(EnterpriseSource, "informs-demo")
        source.polling_allowed = True
        source.config = {
            **source.config,
            "poll_window_start": START.isoformat(),
            "poll_window_end": END.isoformat(),
        }
        session.commit()
        assert len(enqueue_due_sources(session, ADMIN)) == 1
        session.commit()
        assert enqueue_due_sources(session, ADMIN) == []
