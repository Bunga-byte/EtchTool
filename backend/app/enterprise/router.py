"""Scoped evidence and review workspace; no live source connection is implied."""

from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.auth import Principal, principal, require_roles
from app.db import get_session
from app.models import Installation, Tool, Chamber, Position, Assembly, Subsystem
from .models import (
    EnterpriseSource,
    SourceVersion,
    FactProposal,
    EntityAlias,
    EngineeringReview,
    SyncJob,
)
from .security import authorize_source, permitted_sources
from .identity import ENTITY_MODELS
from .workflow import (
    document_view,
    proposal_view,
    preview_proposal,
    review_proposal,
    WorkflowConflict,
    authorize_proposal_entities,
    _audit,
)

router = APIRouter(prefix="/api/enterprise", tags=["Enterprise evidence and review"])


def required(session, model, id):
    value = session.get(model, id)
    if value is None:
        raise HTTPException(404, "Record not found")
    return value


def authorize_version(session, actor, version, write=False):
    source = required(session, EnterpriseSource, version.source_id)
    return authorize_source(
        session,
        actor,
        source,
        write=write,
        equipment_alias=version.equipment_alias,
        collection=version.collection,
        at=version.effective_at,
    )


def visible_versions(session, actor):
    visible = []
    for version in session.scalars(
        select(SourceVersion).order_by(SourceVersion.ingested_at.desc())
    ):
        try:
            authorize_version(session, actor, version)
        except HTTPException:
            continue
        visible.append(version)
    return visible


def authorized_proposal(session, actor, fact):
    version = required(session, SourceVersion, fact.source_version_id)
    authorize_version(session, actor, version)
    preview = preview_proposal(session, fact)
    authorize_proposal_entities(
        session, actor, version, preview["matched_entities"], payload=fact.payload
    )
    authorize_proposal_entities(
        session, actor, version, fact.matched_entities, payload=fact.payload
    )
    return preview


def visible_proposal_view(session, actor, fact):
    try:
        authorized_proposal(session, actor, fact)
    except HTTPException as exc:
        if exc.status_code in {403, 404}:
            return None
        raise
    return proposal_view(fact)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str = Field(pattern="^(approve|reject|correct)$")
    note: str = Field(min_length=10, max_length=4000)
    corrections: dict | None = None


class AliasRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(min_length=1, max_length=80)
    entity_type: str = Field(pattern="^(tool|chamber|position|component|definition)$")
    external_id: str = Field(min_length=1, max_length=200)
    canonical_id: str = Field(min_length=1, max_length=80)
    valid_from: AwareDatetime
    valid_to: AwareDatetime | None = None
    evidence: list[dict] = Field(min_length=1, max_length=50)
    note: str = Field(min_length=10, max_length=4000)


def alias_view(alias):
    return {
        "id": alias.id,
        "source_id": alias.source_id,
        "entity_type": alias.entity_type,
        "external_id": alias.external_id,
        "canonical_id": alias.canonical_id,
        "valid_from": alias.valid_from.isoformat(),
        "valid_to": alias.valid_to.isoformat() if alias.valid_to else None,
        "verification_status": alias.verification_status,
        "evidence": alias.evidence,
    }


@router.get("/documents")
def documents(
    source_id: str | None = None,
    session: Session = Depends(get_session),
    actor: Principal = Depends(principal),
):
    items = []
    for version in visible_versions(session, actor):
        if source_id and version.source_id != source_id:
            continue
        view = document_view(version)
        view.pop("content_b64")
        view.pop("text")
        view.pop("blocks")
        view.pop("parsed")
        view["proposal_count"] = (
            session.query(FactProposal)
            .filter(FactProposal.source_version_id == version.id)
            .count()
        )
        items.append(view)
    return {"items": items}


@router.get("/documents/{id}")
def document(
    id: str,
    session: Session = Depends(get_session),
    actor: Principal = Depends(principal),
):
    version = required(session, SourceVersion, id)
    authorize_version(session, actor, version)
    return {
        **document_view(version),
        "proposals": [
            view
            for p in session.scalars(
                select(FactProposal).where(FactProposal.source_version_id == id)
            )
            if (view := visible_proposal_view(session, actor, p)) is not None
        ],
    }


@router.get("/proposals")
def proposals(
    source_id: str | None = None,
    status: str | None = None,
    session: Session = Depends(get_session),
    actor: Principal = Depends(principal),
):
    versions = {
        v.id: v
        for v in visible_versions(session, actor)
        if source_id is None or v.source_id == source_id
    }
    items = []
    for proposal in session.scalars(
        select(FactProposal)
        .where(FactProposal.source_version_id.in_(versions))
        .order_by(FactProposal.created_at.desc())
    ):
        if status and proposal.status != status:
            continue
        view = visible_proposal_view(session, actor, proposal)
        if view is None:
            continue
        items.append(
            {
                **view,
                "source_id": versions[proposal.source_version_id].source_id,
                "document_title": versions[proposal.source_version_id].title,
            }
        )
    return {"items": items}


@router.get("/proposals/{id}")
def proposal(
    id: str,
    session: Session = Depends(get_session),
    actor: Principal = Depends(principal),
):
    fact = required(session, FactProposal, id)
    version = required(session, SourceVersion, fact.source_version_id)
    authorize_version(session, actor, version)
    authorized_proposal(session, actor, fact)
    reviews = session.scalars(
        select(EngineeringReview)
        .where(
            EngineeringReview.entity_id.in_(
                [fact.id, fact.supersedes_id] if fact.supersedes_id else [fact.id]
            )
        )
        .order_by(EngineeringReview.created_at)
    ).all()
    safe_reviews = []
    for review in reviews:
        allowed = True
        for snapshot in (
            review.before_after.get("before"),
            review.before_after.get("after"),
        ):
            if not isinstance(snapshot, dict):
                continue
            try:
                authorize_proposal_entities(
                    session,
                    actor,
                    version,
                    snapshot.get("matched_entities", {}),
                    payload=snapshot.get("payload", {}),
                )
            except HTTPException:
                allowed = False
                break
        if allowed:
            safe_reviews.append(review)
    return {
        **proposal_view(fact),
        "document": document_view(version, fact),
        "reviews": [
            {
                "id": r.id,
                "actor": r.actor,
                "decision": r.decision,
                "note": r.note,
                "created_at": r.created_at.isoformat(),
                "before_after": r.before_after,
            }
            for r in safe_reviews
        ],
    }


@router.get("/proposals/{id}/preview")
def preview(
    id: str,
    session: Session = Depends(get_session),
    actor: Principal = Depends(principal),
):
    fact = required(session, FactProposal, id)
    authorize_version(
        session, actor, required(session, SourceVersion, fact.source_version_id)
    )
    return authorized_proposal(session, actor, fact)


@router.post("/proposals/{id}/review")
def review(
    id: str,
    data: ReviewRequest,
    session: Session = Depends(get_session),
    actor: Principal = Depends(require_roles("editor", "admin")),
):
    fact = required(session, FactProposal, id)
    authorize_version(
        session,
        actor,
        required(session, SourceVersion, fact.source_version_id),
        write=True,
    )
    try:
        result = review_proposal(
            session, id, data.decision, data.note, actor, data.corrections
        )
        session.commit()
        return result
    except WorkflowConflict as exc:
        session.rollback()
        raise HTTPException(409, {"message": str(exc), "preview": exc.preview})
    except ValueError as exc:
        session.rollback()
        raise HTTPException(422, str(exc))
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            409,
            "Concurrent canonical or review update conflicts; refresh preview before retrying",
        )


@router.get("/aliases")
def aliases(
    request: Request,
    source_id: str | None = None,
    session: Session = Depends(get_session),
    actor: Principal = Depends(principal),
):
    from .canonical_security import canonical_scope
    from .identity import resolve_alias
    from app.models import ComponentInstance, ComponentDefinition

    canonical = canonical_scope(session, actor, request.app.state.config.mode)
    allowed = {
        source.id: (source, scope)
        for source, scope in permitted_sources(session, actor)
    }
    items = []
    for alias in session.scalars(
        select(EntityAlias).order_by(EntityAlias.source_id, EntityAlias.entity_type)
    ):
        if alias.source_id not in allowed or (
            source_id and alias.source_id != source_id
        ):
            continue
        source, source_scope = allowed[alias.source_id]
        try:
            permitted = authorize_source(session, actor, source, at=alias.valid_from)
            tools = {
                id
                for external in permitted.equipment_aliases
                for id, method in [
                    resolve_alias(
                        session, source.id, "tool", external, alias.valid_from
                    )
                ]
                if id is not None
            }
            tools &= set(canonical.tool_ids)
            target = session.get(ENTITY_MODELS[alias.entity_type], alias.canonical_id)
            if target is None:
                continue
            if alias.entity_type == "tool":
                if (
                    alias.external_id not in permitted.equipment_aliases
                    or target.id not in tools
                ):
                    continue
            elif alias.entity_type == "chamber":
                if target.tool_id not in tools:
                    continue
            elif alias.entity_type == "position":
                ass = session.get(Assembly, target.assembly_id)
                sub = session.get(Subsystem, ass.subsystem_id)
                chamber = session.get(Chamber, sub.chamber_id)
                if chamber.tool_id not in tools:
                    continue
            elif (
                alias.entity_type == "component"
                and actor.role != "admin"
                and not actor.anonymous_demo
            ):
                canonical.require_component(session, target.id)
                if not canonical.component_tools(session, target.id) <= tools:
                    continue
            elif (
                alias.entity_type == "definition"
                and actor.role != "admin"
                and not actor.anonymous_demo
            ):
                components = session.scalars(
                    select(ComponentInstance).where(
                        ComponentInstance.definition_id == target.id
                    )
                ).all()
                if not any(
                    canonical.component_tools(session, c.id)
                    and canonical.component_tools(session, c.id) <= tools
                    for c in components
                ):
                    continue
        except HTTPException:
            continue
        items.append(alias_view(alias))
    return {"items": items}


@router.post("/aliases", status_code=201)
def create_alias(
    data: AliasRequest,
    request: Request,
    session: Session = Depends(get_session),
    actor: Principal = Depends(require_roles("editor", "admin")),
):
    source = required(session, EnterpriseSource, data.source_id)
    authorize_source(session, actor, source, write=True, at=data.valid_from)
    if data.valid_to and data.valid_to <= data.valid_from:
        raise HTTPException(422, "Alias effective end must follow start")
    model = ENTITY_MODELS[data.entity_type]
    target = required(session, model, data.canonical_id)
    from .canonical_security import canonical_scope

    scope = canonical_scope(session, actor, request.app.state.config.mode)
    if data.entity_type == "tool":
        scope.require_tool(target.id)
        if data.external_id not in source.authorized_equipment:
            raise HTTPException(
                403, "Tool alias must be inside approved source equipment scope"
            )
    elif data.entity_type == "chamber":
        scope.require_chamber(session, target.id)
    elif data.entity_type == "position":
        ass = session.get(Assembly, target.assembly_id)
        sub = session.get(Subsystem, ass.subsystem_id)
        scope.require_chamber(session, sub.chamber_id)
    elif data.entity_type == "component" and actor.role != "admin":
        scope.require_component(session, target.id)
    if data.entity_type == "definition" and actor.role != "admin":
        raise HTTPException(
            403, "Definition identity mapping requires administrative review"
        )
    # Lock the source row to serialize alias history edits on PostgreSQL.
    session.scalar(
        select(EnterpriseSource)
        .where(EnterpriseSource.id == source.id)
        .with_for_update()
    )
    query = select(EntityAlias).where(
        EntityAlias.source_id == source.id,
        EntityAlias.entity_type == data.entity_type,
        EntityAlias.external_id == data.external_id,
        or_(EntityAlias.valid_to.is_(None), EntityAlias.valid_to > data.valid_from),
    )
    if data.valid_to:
        query = query.where(EntityAlias.valid_from < data.valid_to)
    if session.scalar(query):
        raise HTTPException(
            409, "Alias effective period overlaps an existing association"
        )
    alias = EntityAlias(
        id=str(uuid4()),
        source_id=source.id,
        entity_type=data.entity_type,
        external_id=data.external_id,
        canonical_id=data.canonical_id,
        valid_from=data.valid_from,
        valid_to=data.valid_to,
        verification_status="verified",
        evidence=data.evidence,
    )
    session.add(alias)
    session.add(
        EngineeringReview(
            id=str(uuid4()),
            entity_type="entity_alias",
            entity_id=alias.id,
            actor=actor.subject,
            decision="approve",
            note=data.note,
            created_at=datetime.now(timezone.utc),
            before_after={"before": None, "after": data.model_dump(mode="json")},
        )
    )
    _audit(
        session,
        actor,
        "approve_identity_alias",
        "entity_alias",
        alias.id,
        data.model_dump(mode="json"),
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "Concurrent alias update; review effective history")
    return alias_view(alias)
