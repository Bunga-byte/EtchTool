"""HTTP transport. Bundled records are synthetic; no equipment control endpoints."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from io import StringIO
import csv, hashlib, json, logging, time
from uuid import uuid4
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime
from sqlalchemy import select, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from .auth import Principal, principal, require_roles, require_export
from .enterprise.canonical_security import (
    canonical_scope,
    scoped_inventory,
    scoped_hierarchy,
    scoped_component_detail,
    scoped_failures,
    scoped_failure_detail,
    scoped_pm,
    scoped_analytics,
    scoped_fleet,
    scoped_quality,
    require_canonical_export,
    require_conflict,
)
from .config import Settings, settings
from .db import make_engine, migrate, get_session
from .models import *
from .seed import seed, AS_OF
from . import views as v
from .schemas import (
    ComponentDetail,
    InventoryResponse,
    FailureList,
    FailureDetail,
    Health,
)
from .integrations import ADAPTERS, ImportRequest, adapter_descriptions, ingest_records

log = logging.getLogger("frip")
log.setLevel(logging.INFO)
if not log.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(handler)
log.propagate = False


class InstallInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    component_id: str = Field(min_length=1, max_length=80)
    position_id: str = Field(min_length=1, max_length=80)
    installed_at: AwareDatetime
    reason: str = Field(min_length=5, max_length=2000)


class RemoveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    removed_at: AwareDatetime
    reason: str = Field(min_length=5, max_length=2000)


class AdjudicateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(pattern="^(confirmed|unconfirmed|investigating|rejected)$")
    note: str = Field(min_length=10, max_length=4000)


class ResolveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str = Field(pattern="^(accept_a|accept_b|defer)$")
    note: str = Field(min_length=10, max_length=4000)


def audit(session, actor, action, kind, id, detail):
    session.add(
        AuditLog(
            id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            actor=actor.subject,
            role=actor.role,
            action=action,
            entity_type=kind,
            entity_id=id,
            detail=detail,
        )
    )


def required(session, model, id):
    obj = session.get(model, id)
    if obj is None:
        raise HTTPException(404, f"{model.__name__} not found")
    return obj


def raw_change(session, payload, at):
    id = str(uuid4())
    encoded = json.dumps(payload, sort_keys=True, default=str)
    session.add(
        RawSourceRecord(
            id=id,
            source="synthetic_editor",
            source_id=id,
            recorded_at=datetime.now(timezone.utc),
            effective_at=at,
            ingested_at=datetime.now(timezone.utc),
            payload={"synthetic": True, **json.loads(encoded)},
            fingerprint=hashlib.sha256((id + encoded).encode()).hexdigest(),
            quality="complete",
            verification="human_entered_synthetic",
        )
    )
    session.flush()
    return id


def quality(session):
    items = []
    for c in v.rows(session, SourceConflict):
        a = session.get(RawSourceRecord, c.record_a_id)
        b = session.get(RawSourceRecord, c.record_b_id)
        items.append(
            {
                "id": c.id,
                "component_id": c.component_id,
                "field": c.field,
                "value_a": c.value_a,
                "value_b": c.value_b,
                "source_a": a.source,
                "source_b": b.source,
                "record_a": v.provenance(a),
                "record_b": v.provenance(b),
                "status": c.status,
                "decision": c.decision,
                "note": c.note,
                "resolved_at": v.iso(c.resolved_at),
            }
        )
    return {
        "items": items,
        "issues": [
            {
                "code": "coverage_gap",
                "chamber_id": "ch-3-b",
                "message": "Seven days of missing monitoring coverage; no exposure extrapolation",
            },
            {
                "code": "unknown_oem_limits",
                "message": "All OEM specifications pending authorized documentation",
            },
        ],
        "synthetic": True,
        "source_priority_policy": "No automatic authority rule approved; disagreements require an audited decision",
        "as_of": v.iso(AS_OF),
    }


def create_app(
    config: Settings | None = None, engine=None, authentication_provider=None
):
    config = config or settings()
    if config.auth_backend == "external_provider" and authentication_provider is None:
        raise ValueError(
            "External authentication backend requires a verified principal provider"
        )
    dbengine = engine or make_engine(config.database_url)

    @asynccontextmanager
    async def lifespan(application):
        if config.mode == "synthetic":
            migrate(dbengine)
            with Session(dbengine) as session:
                seed(session)
        yield

    application = FastAPI(
        title="FRIP — Synthetic Engineering Foundation",
        version="0.1.0",
        description="Synthetic-only reliability workspace. No Samsung or Lam systems connected.",
        lifespan=lifespan,
    )
    application.state.authentication_provider = authentication_provider
    application.state.config = config
    application.state.engine = dbengine
    application.state.sessions = sessionmaker(dbengine, expire_on_commit=False)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @application.middleware("http")
    async def boundary(request: Request, call_next):
        start = time.monotonic()
        if request.method in {"POST", "PUT", "PATCH"}:
            chunks = []
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 5_000_000:
                    return JSONResponse(
                        {"detail": "Request body exceeds 5 MB import limit"},
                        status_code=413,
                    )
                chunks.append(chunk)
            request._body = b"".join(chunks)
        response = await call_next(request)
        log.info(
            json.dumps(
                {
                    "event": "http_request",
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.monotonic() - start) * 1000, 2),
                }
            )
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @application.get("/healthz", include_in_schema=False)
    def healthz():
        try:
            with dbengine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception:
            raise HTTPException(503, "Not ready")
        return {"status": "ok"}

    router = APIRouter(prefix="/api", dependencies=[Depends(principal)])

    @router.get("/health", response_model=Health)
    def health(session: Session = Depends(get_session)):
        session.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "dataset": "synthetic-only",
            "database": "connected",
            "as_of": v.iso(AS_OF),
            "enterprise_connected": False,
        }

    @router.get("/hierarchy")
    def hierarchy(
        session: Session = Depends(get_session), actor: Principal = Depends(principal)
    ):
        return scoped_hierarchy(session, canonical_scope(session, actor, config.mode))

    @router.get("/inventory", response_model=InventoryResponse)
    def inventory(
        chamber_id: str | None = None,
        at: AwareDatetime | None = None,
        q: str | None = Query(default=None, max_length=200),
        status: str | None = None,
        session: Session = Depends(get_session),
        actor: Principal = Depends(principal),
    ):
        return {
            "items": scoped_inventory(
                session,
                canonical_scope(session, actor, config.mode),
                chamber_id,
                at or AS_OF,
                q,
                status,
            ),
            "as_of": v.iso(at or AS_OF),
            "synthetic": True,
        }

    @router.get("/components/{id}", response_model=ComponentDetail)
    def component(
        id: str,
        session: Session = Depends(get_session),
        actor: Principal = Depends(principal),
    ):
        obj = required(session, ComponentInstance, id)
        if not v.history(session, obj):
            raise HTTPException(404, "Component has no installation history")
        return scoped_component_detail(
            session, canonical_scope(session, actor, config.mode), id
        )

    @router.get("/pm", response_model=InventoryResponse)
    def pm(
        status: str | None = None,
        session: Session = Depends(get_session),
        actor: Principal = Depends(principal),
    ):
        return scoped_pm(session, canonical_scope(session, actor, config.mode), status)

    @router.get("/failures", response_model=FailureList)
    def failures(
        session: Session = Depends(get_session), actor: Principal = Depends(principal)
    ):
        return scoped_failures(session, canonical_scope(session, actor, config.mode))

    @router.get("/failures/{id}", response_model=FailureDetail)
    def failure(
        id: str,
        session: Session = Depends(get_session),
        actor: Principal = Depends(principal),
    ):
        return scoped_failure_detail(
            session, canonical_scope(session, actor, config.mode), id
        )

    @router.get("/analytics")
    def analytics(
        session: Session = Depends(get_session), actor: Principal = Depends(principal)
    ):
        return scoped_analytics(session, canonical_scope(session, actor, config.mode))

    @router.get("/forecast/demo")
    def demo_forecast():
        from .services.forecast import synthetic_demo_forecast

        return synthetic_demo_forecast()

    @router.get("/fleet")
    def fleet(
        session: Session = Depends(get_session), actor: Principal = Depends(principal)
    ):
        return scoped_fleet(
            session, canonical_scope(session, actor, config.mode), quality(session)
        )

    @router.get("/integrations")
    def integrations(session: Session = Depends(get_session)):
        if config.mode != "synthetic":
            return {
                "items": [],
                "enterprise_connected": False,
                "legacy_imports_enabled": False,
                "message": "Use the enterprise integration workspace for scoped source status and synchronization.",
            }
        items = adapter_descriptions()
        for item in items:
            id = item.get("id", item.get("adapter_id"))
            run = session.scalar(
                select(IngestionRun)
                .where(IngestionRun.adapter_id == id)
                .order_by(IngestionRun.started_at.desc())
            )
            item.update(
                {
                    "id": id,
                    "last_sync": v.iso(run.completed_at) if run else None,
                    "record_count": run.record_count if run else 0,
                    "errors": run.errors if run else [],
                    "status": "synthetic_fixture_loaded" if run else "not_connected",
                    "enterprise_connected": False,
                }
            )
        return {
            "items": items,
            "enterprise_connected": False,
            "synthetic": True,
            "as_of": v.iso(AS_OF),
        }

    @router.get("/quality")
    def get_quality(
        session: Session = Depends(get_session), actor: Principal = Depends(principal)
    ):
        return scoped_quality(
            session, canonical_scope(session, actor, config.mode), quality(session)
        )

    @router.get("/export/inventory.csv")
    def export(
        chamber_id: str | None = None,
        session: Session = Depends(get_session),
        actor: Principal = Depends(require_export),
    ):
        scope = canonical_scope(session, actor, config.mode)
        require_canonical_export(scope)
        fields = [
            "tool_name",
            "chamber_name",
            "subsystem",
            "name",
            "part_number",
            "serial_number",
            "revision",
            "installed_at",
            "rf_hours",
            "exposure_dimension",
            "exposure_unit",
            "pm_status",
            "synthetic",
        ]
        stream = StringIO()
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()

        def safe(value):
            value = "" if value is None else str(value)
            return (
                "'" + value
                if value.lstrip().startswith(("=", "+", "-", "@"))
                else value
            )

        for i in scoped_inventory(session, scope, chamber_id):
            row = {k: i.get(k) for k in fields}
            row.update(
                {
                    "rf_hours": i["exposure"]["hours"]
                    if i["exposure"]["dimension"] == "rf_hours"
                    else None,
                    "exposure_dimension": i["exposure"]["dimension"],
                    "exposure_unit": i["exposure"]["unit"],
                    "pm_status": i["pm"]["status"],
                    "synthetic": True,
                }
            )
            writer.writerow({k: safe(value) for k, value in row.items()})
        return Response(
            stream.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="frip-synthetic-inventory.csv"'
            },
        )

    @router.post("/installations", status_code=201)
    def install(
        data: InstallInput,
        session: Session = Depends(get_session),
        actor: Principal = Depends(require_roles("editor", "admin")),
    ):
        scope = canonical_scope(session, actor, config.mode)
        scope.require_component(session, data.component_id)
        position_for_scope = required(session, Position, data.position_id)
        assembly_for_scope = session.get(Assembly, position_for_scope.assembly_id)
        sub_for_scope = session.get(Subsystem, assembly_for_scope.subsystem_id)
        scope.require_chamber(session, sub_for_scope.chamber_id)
        component = session.scalar(
            select(ComponentInstance)
            .where(ComponentInstance.id == data.component_id)
            .with_for_update()
        )
        position = session.scalar(
            select(Position).where(Position.id == data.position_id).with_for_update()
        )
        if not component or not position:
            raise HTTPException(404, "Component or position not found")
        if data.installed_at > AS_OF:
            raise HTTPException(
                422,
                "Choose a timestamp no later than the frozen synthetic as_of snapshot",
            )
        overlap = session.scalar(
            select(Installation).where(
                or_(
                    Installation.component_id == component.id,
                    Installation.position_id == position.id,
                ),
                or_(
                    Installation.removed_at.is_(None),
                    Installation.removed_at > data.installed_at,
                ),
            )
        )
        if overlap:
            raise HTTPException(
                409,
                "Serialized component or physical position has an overlapping installation",
            )
        ass = session.get(Assembly, position.assembly_id)
        sub = session.get(Subsystem, ass.subsystem_id)
        ch = session.get(Chamber, sub.chamber_id)
        tool = session.get(Tool, ch.tool_id)
        compat = session.scalar(
            select(Compatibility).where(
                Compatibility.definition_id == component.definition_id,
                Compatibility.configuration_id == tool.configuration_id,
                Compatibility.effective_from <= data.installed_at,
                or_(
                    Compatibility.effective_to.is_(None),
                    Compatibility.effective_to > data.installed_at,
                ),
            )
        )
        if not compat:
            raise HTTPException(
                409, "Component configuration compatibility not established"
            )
        definition = session.get(ComponentDefinition, component.definition_id)
        if definition.category != sub.name:
            raise HTTPException(
                409,
                "Component category is incompatible with this physical position subsystem",
            )
        id = str(uuid4())
        raw_id = raw_change(session, data.model_dump(), data.installed_at)
        session.add(
            Installation(
                id=id,
                component_id=component.id,
                position_id=position.id,
                installed_at=data.installed_at,
                removed_at=None,
                reason=data.reason,
                removal_reason=None,
                source_record_id=raw_id,
            )
        )
        component.disposition = "installed"
        session.flush()
        from .enterprise.telemetry import rebuild_component_exposure

        rebuild_component_exposure(session, component.id)
        audit(
            session, actor, "install", "installation", id, data.model_dump(mode="json")
        )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise HTTPException(
                409,
                "Concurrent installation conflicts with active component or position",
            )
        return {"id": id, "status": "installed", "synthetic": True}

    @router.post("/installations/{id}/remove")
    def remove(
        id: str,
        data: RemoveInput,
        session: Session = Depends(get_session),
        actor: Principal = Depends(require_roles("editor", "admin")),
    ):
        canonical_scope(session, actor, config.mode).require_installation(session, id)
        installation = session.scalar(
            select(Installation).where(Installation.id == id).with_for_update()
        )
        if installation is None:
            raise HTTPException(404, "Installation not found")
        if installation.removed_at is not None:
            raise HTTPException(
                409,
                "Installation already closed; historical corrections require a separate audited workflow",
            )
        if data.removed_at <= installation.installed_at or data.removed_at > AS_OF:
            raise HTTPException(
                422, "Removal must follow installation and not exceed snapshot"
            )
        installation.removed_at = data.removed_at
        installation.removal_reason = data.reason
        session.get(
            ComponentInstance, installation.component_id
        ).disposition = "removed_pending_review"
        session.flush()
        from .enterprise.telemetry import rebuild_component_exposure

        rebuild_component_exposure(session, installation.component_id)
        removal_raw = raw_change(
            session,
            {"installation_id": id, **data.model_dump(mode="json")},
            data.removed_at,
        )
        audit(
            session,
            actor,
            "remove",
            "installation",
            id,
            {**data.model_dump(mode="json"), "raw_record_id": removal_raw},
        )
        session.commit()
        return {
            "id": id,
            "status": "removed",
            "removed_at": v.iso(installation.removed_at),
            "failure_created": False,
        }

    @router.post("/failures/{id}/adjudicate")
    def adjudicate(
        id: str,
        data: AdjudicateInput,
        session: Session = Depends(get_session),
        actor: Principal = Depends(require_roles("analyst", "editor", "admin")),
    ):
        canonical_scope(session, actor, config.mode).require_failure(
            session, id, evidence=True
        )
        episode = required(session, FailureEpisode, id)
        previous = episode.status
        if data.status == "confirmed" and not session.scalar(
            select(Evidence).where(Evidence.failure_id == id)
        ):
            raise HTTPException(409, "Confirmed failure requires retained evidence")
        episode.status = data.status
        episode.review_status = "reviewed_synthetic"
        episode.attribution_status = (
            "confirmed" if data.status == "confirmed" else "unconfirmed"
        )
        audit(
            session,
            actor,
            "adjudicate_failure",
            "failure",
            id,
            {"previous_status": previous, **data.model_dump()},
        )
        session.commit()
        return v.failure_detail(session, episode)

    @router.post("/quality/{id}/resolve")
    def resolve(
        id: str,
        data: ResolveInput,
        session: Session = Depends(get_session),
        actor: Principal = Depends(require_roles("editor", "admin")),
    ):
        require_conflict(session, canonical_scope(session, actor, config.mode), id)
        conflict = required(session, SourceConflict, id)
        conflict.decision = data.decision
        conflict.note = data.note
        conflict.status = (
            "unresolved"
            if data.decision == "defer"
            else "decision_recorded_pending_materialization"
        )
        conflict.resolved_at = None
        audit(
            session,
            actor,
            "resolve_source_conflict",
            "source_conflict",
            id,
            data.model_dump(),
        )
        session.commit()
        return {
            "id": id,
            "status": conflict.status,
            "decision": conflict.decision,
            "raw_records_preserved": True,
            "note": "Decision recorded; physical state remains contested until approved lifecycle correction is applied",
        }

    @router.post("/integrations/{adapter_id}/import")
    def import_records(
        adapter_id: str,
        data: ImportRequest,
        session: Session = Depends(get_session),
        actor: Principal = Depends(require_roles("editor", "admin")),
    ):
        if config.mode != "synthetic":
            raise HTTPException(
                409,
                "Legacy file imports are available only in synthetic mode; use authorized enterprise synchronization jobs.",
            )
        if adapter_id not in ADAPTERS:
            raise HTTPException(404, "Unknown adapter")
        scopes = set(ADAPTERS) if actor.role == "admin" else set(actor.sources)
        if adapter_id not in scopes:
            raise HTTPException(403, "Token not authorized for this source")
        existing = [
            {
                "source": r.source,
                "source_id": r.source_id,
                "payload": r.payload,
                "fingerprint": r.fingerprint,
                "effective_at": v.iso(r.effective_at),
            }
            for r in v.rows(session, RawSourceRecord)
        ]
        try:
            result = ingest_records(
                adapter_id,
                data.records,
                authorized_sources=scopes,
                existing=existing,
                cursor=data.cursor,
                page_size=data.page_size,
                field_mapping=data.field_mapping,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        now = datetime.now(timezone.utc)
        run_id = str(uuid4())
        session.add(
            IngestionRun(
                id=run_id,
                adapter_id=adapter_id,
                started_at=now,
                completed_at=now,
                status="completed_with_errors" if result.errors else "completed",
                record_count=len(result.records),
                duplicate_count=result.duplicates,
                errors=[e.model_dump() for e in result.errors],
                cursor=result.next_cursor,
            )
        )
        session.flush()
        for original in result.originals:
            session.add(
                IngestionOriginal(
                    id=str(uuid4()),
                    run_id=run_id,
                    source=original.source,
                    ingested_at=original.ingested_at,
                    original_json=original.original_json,
                    fingerprint=original.fingerprint,
                    row=original.row,
                )
            )
        with session.no_autoflush:
            for record in result.records:
                if session.scalar(
                    select(RawSourceRecord).where(
                        RawSourceRecord.fingerprint == record.fingerprint
                    )
                ):
                    continue
                session.add(
                    RawSourceRecord(
                        id=str(uuid4()),
                        source=record.source,
                        source_id=record.source_id,
                        recorded_at=record.recorded_at,
                        effective_at=record.effective_at,
                        ingested_at=record.ingested_at,
                        payload=record.payload,
                        fingerprint=record.fingerprint,
                        quality=record.quality,
                        verification=record.verification,
                    )
                )
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            raise HTTPException(
                409, "Concurrent import changed deduplication state; retry this batch"
            )
        for conflict in result.conflicts:
            candidates = v.rows(session, RawSourceRecord)

            def matches(r, source, value, source_id):
                return (
                    r.source == source
                    and str(r.payload.get(conflict.field)) == str(value)
                    and (
                        r.source_id == source_id
                        if source_id is not None
                        else (
                            "|".join(
                                str(r.payload.get(field, ""))
                                for field in ADAPTERS[adapter_id].identity_fields
                            )
                            == conflict.subject
                        )
                    )
                )

            previous = next(
                (
                    r
                    for r in reversed(candidates)
                    if matches(
                        r,
                        conflict.current_source,
                        conflict.current_value,
                        conflict.current_source_id,
                    )
                ),
                None,
            )
            incoming = next(
                (
                    r
                    for r in reversed(candidates)
                    if matches(
                        r,
                        conflict.incoming_source,
                        conflict.incoming_value,
                        conflict.incoming_source_id,
                    )
                ),
                None,
            )
            if previous is not None and incoming is not None:
                cid = session.scalar(
                    select(ComponentInstance.id).where(
                        ComponentInstance.serial_number
                        == str(incoming.payload.get("component_serial"))
                    )
                )
                session.add(
                    SourceConflict(
                        id=str(uuid4()),
                        component_id=cid,
                        field=conflict.field,
                        record_a_id=previous.id,
                        record_b_id=incoming.id,
                        value_a=json.dumps(conflict.current_value),
                        value_b=json.dumps(conflict.incoming_value),
                        status=conflict.status,
                        decision=None,
                        note=None,
                        resolved_at=None,
                    )
                )
        audit(
            session,
            actor,
            "import_batch",
            "ingestion_run",
            run_id,
            {
                "adapter_id": adapter_id,
                "accepted": len(result.records),
                "duplicates": result.duplicates,
                "errors": len(result.errors),
                "conflicts": [c.model_dump() for c in result.conflicts],
            },
        )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise HTTPException(
                409, "Concurrent import changed deduplication state; retry this batch"
            )
        return {
            "run_id": run_id,
            **result.model_dump(mode="json"),
            "materialization": "Validated records staged in immutable source storage; domain changes require approved mapping and reconciliation",
        }

    @router.get("/audit")
    def audits(
        session: Session = Depends(get_session),
        actor: Principal = Depends(require_roles("admin")),
    ):
        return {
            "items": [
                {
                    "id": a.id,
                    "timestamp": v.iso(a.timestamp),
                    "actor": a.actor,
                    "role": a.role,
                    "action": a.action,
                    "entity_type": a.entity_type,
                    "entity_id": a.entity_id,
                    "detail": a.detail,
                }
                for a in session.scalars(
                    select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(200)
                )
            ]
        }

    application.include_router(router)
    from .enterprise.router import router as evidence_router
    from .enterprise.jobs_router import router as jobs_router
    from .enterprise.telemetry_router import router as telemetry_router

    application.include_router(evidence_router)
    application.include_router(jobs_router)
    application.include_router(telemetry_router)
    return application


app = create_app()
