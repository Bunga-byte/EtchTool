"""Integration operations with source/equipment/collection authorization."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal, principal
from app.db import get_session
from .connectors import fixture_connector
from .contracts import PermanentConnectorError
from .models import (
    DeadLetter,
    FactProposal,
    SourceVersion,
    SyncCheckpoint,
    SyncJob,
)
from .orchestrator import (
    audit_job,
    create_job,
    job_scope,
    retry_job,
    run_job,
    source_required,
)
from .security import authorize_source, permitted_sources

router = APIRouter(prefix="/api/enterprise", tags=["Enterprise synchronization"])


class JobQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    equipment_aliases: list[str] = Field(default_factory=list, max_length=100)
    collections: list[str] = Field(default_factory=list, max_length=100)
    original_ids: list[str] = Field(default_factory=list, max_length=200)
    chamber_alias: str | None = Field(default=None, max_length=200)
    keyword: str | None = Field(default=None, max_length=200)
    part_number: str | None = Field(default=None, max_length=200)
    serial_number: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=100, ge=1, le=200)


class JobInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(min_length=1, max_length=80)
    kind: Literal["backfill", "incremental", "reprocess"] = "backfill"
    window_start: AwareDatetime
    window_end: AwareDatetime
    query: JobQuery = Field(default_factory=JobQuery)
    max_attempts: int = Field(default=3, ge=1, le=8)


class ScheduleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    interval_seconds: int = Field(default=3600, ge=60, le=86400)
    window_start: AwareDatetime
    window_end: AwareDatetime
    note: str = Field(min_length=10, max_length=2000)


class MappingPreviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_version_id: str = Field(min_length=1, max_length=80)
    field_mapping: dict[str, str] = Field(default_factory=dict, max_length=100)


def job_dict(job):
    return {
        key: getattr(job, key)
        for key in (
            "id",
            "source_id",
            "kind",
            "status",
            "cursor",
            "window_start",
            "window_end",
            "attempts",
            "max_attempts",
            "next_attempt_at",
            "created_at",
            "started_at",
            "finished_at",
            "error",
            "metrics",
            "requested_by",
            "query",
        )
    }


def source_dict(session, source, actor):
    scope = authorize_source(session, actor, source)
    versions = []
    for version in session.scalars(
        select(SourceVersion).where(SourceVersion.source_id == source.id)
    ):
        try:
            authorize_source(
                session,
                actor,
                source,
                equipment_alias=version.equipment_alias,
                collection=version.collection,
                at=version.effective_at,
            )
        except HTTPException:
            continue
        versions.append(version)
    proposals = (
        session.scalars(
            select(FactProposal).where(
                FactProposal.source_version_id.in_([v.id for v in versions])
            )
        ).all()
        if versions
        else []
    )
    jobs = []
    for job in session.scalars(
        select(SyncJob)
        .where(SyncJob.source_id == source.id)
        .order_by(SyncJob.created_at.desc())
    ):
        try:
            job_scope(session, actor, job)
        except HTTPException:
            continue
        jobs.append(job)
    try:
        connector = fixture_connector(source.id)
        capabilities = connector.capabilities().model_dump()
        raw_health = connector.health()
        health = {
            key: raw_health[key]
            for key in ("status", "source_id", "external_connection")
            if key in raw_health
        }
    except PermanentConnectorError:
        capabilities, health = (
            {},
            {"status": "not_configured", "external_connection": False},
        )
    return {
        "id": source.id,
        "name": source.name,
        "connector_kind": source.connector_kind,
        "connection_type": source.connector_kind,
        "classification": source.classification,
        "enabled": source.enabled,
        "polling_allowed": source.polling_allowed,
        "interval_seconds": source.interval_seconds,
        "capabilities": capabilities,
        "health": health,
        "status": health["status"],
        "connected": False,
        "external_connection": False,
        "authorized_scope": scope.model_dump(mode="json"),
        "last_success_at": source.last_success_at,
        "latest_source_timestamp": max((v.recorded_at for v in versions), default=None),
        "last_error": next((j.error for j in jobs if j.error), None),
        "records_discovered": sum(j.metrics.get("discovered", 0) for j in jobs),
        "records_processed": sum(j.metrics.get("processed", 0) for j in jobs),
        "records_rejected": sum(j.metrics.get("rejected", 0) for j in jobs),
        "document_count": len(versions),
        "pending_approvals": sum(
            p.status not in {"approved", "rejected", "superseded"} for p in proposals
        ),
        "unresolved_identity_conflicts": sum(
            p.match_status in {"unresolved", "ambiguous", "conflict"} for p in proposals
        ),
        "read_only_upstream": True,
        "synthetic": source.classification == "synthetic",
    }


@router.get("/sources")
def sources(
    session: Session = Depends(get_session), actor: Principal = Depends(principal)
):
    return {
        "items": [
            source_dict(session, source, actor)
            for source, _ in permitted_sources(session, actor)
        ],
        "external_systems_connected": False,
    }


@router.get("/sources/{source_id}/capabilities")
def capabilities(
    source_id: str,
    session: Session = Depends(get_session),
    actor: Principal = Depends(principal),
):
    source = source_required(session, source_id)
    scope = authorize_source(session, actor, source)
    try:
        connector = fixture_connector(source_id)
        caps = connector.capabilities().model_dump()
        schema = (
            connector.discover_schema(scope) if caps.get("discover_schema") else None
        )
        return {
            "source_id": source_id,
            "capabilities": caps,
            "supported": [k for k, v in caps.items() if v],
            "unsupported": [k for k, v in caps.items() if not v],
            "source_schema": schema,
            "actual_enterprise_schema_known": False,
            "external_connection": False,
        }
    except PermanentConnectorError:
        raise HTTPException(
            409, "Authorized internal connector implementation is not installed"
        ) from None


@router.post("/sources/{source_id}/schedule")
def schedule(
    source_id: str,
    data: ScheduleInput,
    session: Session = Depends(get_session),
    actor: Principal = Depends(principal),
):
    source = source_required(session, source_id)
    authorize_source(session, actor, source, write=True)
    if actor.role != "admin":
        raise HTTPException(
            403, "Only an administrator may authorize continuous polling"
        )
    if not timedelta(0) < data.window_end - data.window_start <= timedelta(days=366):
        raise HTTPException(
            422, "An approved bounded synchronization window is required"
        )
    caps = fixture_connector(source_id).capabilities()
    if data.enabled and not caps.incremental_polling:
        raise HTTPException(409, "Source does not support incremental polling")
    source.polling_allowed, source.interval_seconds = (
        data.enabled,
        data.interval_seconds,
    )
    source.config = {
        **source.config,
        "poll_window_start": data.window_start.isoformat(),
        "poll_window_end": data.window_end.isoformat(),
    }
    audit_job(
        session,
        actor,
        "configure_source_schedule",
        source_id,
        {**data.model_dump(mode="json")},
    )
    session.commit()
    return source_dict(session, source, actor)


@router.post("/sources/{source_id}/mapping-preview")
def mapping_preview(
    source_id: str,
    data: MappingPreviewInput,
    session: Session = Depends(get_session),
    actor: Principal = Depends(principal),
):
    source = source_required(session, source_id)
    version = session.get(SourceVersion, data.source_version_id)
    if version is None or version.source_id != source_id:
        raise HTTPException(404, "Source document version not found")
    authorize_source(
        session,
        actor,
        source,
        equipment_alias=version.equipment_alias,
        collection=version.collection,
        at=version.effective_at,
    )
    from .contracts import ParsedDocument
    from .extraction import extract_facts

    try:
        parsed = ParsedDocument.model_validate(
            version.structured_payload.get("parsed", {})
        )
        drafts = extract_facts(parsed, field_mapping=data.field_mapping)
    except (ValueError, TypeError):
        raise HTTPException(
            422, "Field mapping or retained parser representation is invalid"
        ) from None
    return {
        "source_version_id": version.id,
        "field_mapping": data.field_mapping,
        "proposals": [draft.model_dump(mode="json") for draft in drafts],
        "dry_run": True,
        "canonical_records_changed": False,
    }


@router.get("/jobs")
def jobs(
    session: Session = Depends(get_session), actor: Principal = Depends(principal)
):
    items = []
    for job in session.scalars(
        select(SyncJob).order_by(SyncJob.created_at.desc()).limit(500)
    ):
        try:
            job_scope(session, actor, job)
        except HTTPException:
            continue
        items.append(job_dict(job))
    return {"items": items, "limit": 500}


@router.post("/jobs", status_code=201)
def submit_job(
    data: JobInput,
    session: Session = Depends(get_session),
    actor: Principal = Depends(principal),
):
    job = create_job(
        session,
        data.source_id,
        actor,
        kind=data.kind,
        window_start=data.window_start,
        window_end=data.window_end,
        query=data.query.model_dump(exclude_none=True),
        max_attempts=data.max_attempts,
    )
    session.commit()
    return job_dict(job)


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str,
    session: Session = Depends(get_session),
    actor: Principal = Depends(principal),
):
    job = session.get(SyncJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    job_scope(session, actor, job)
    checkpoints = session.scalars(
        select(SyncCheckpoint).where(SyncCheckpoint.job_id == job.id)
    ).all()
    return {
        **job_dict(job),
        "checkpoints": [
            {
                "stream": c.stream,
                "cursor": json.loads(c.cursor),
                "updated_at": c.updated_at,
            }
            for c in checkpoints
        ],
    }


@router.post("/jobs/{job_id}/run")
def execute_job(
    job_id: str,
    session: Session = Depends(get_session),
    actor: Principal = Depends(principal),
):
    return job_dict(run_job(session, job_id, actor))


@router.post("/jobs/{job_id}/retry")
def resubmit_job(
    job_id: str,
    session: Session = Depends(get_session),
    actor: Principal = Depends(principal),
):
    job = retry_job(session, job_id, actor)
    session.commit()
    return job_dict(job)


@router.get("/dead-letters")
def dead_letters(
    session: Session = Depends(get_session), actor: Principal = Depends(principal)
):
    items = []
    for letter in session.scalars(
        select(DeadLetter).order_by(DeadLetter.created_at.desc()).limit(500)
    ):
        job = session.get(SyncJob, letter.job_id)
        try:
            job_scope(session, actor, job)
        except HTTPException:
            continue
        items.append(
            {
                key: getattr(letter, key)
                for key in (
                    "id",
                    "job_id",
                    "source_version_id",
                    "stage",
                    "error_code",
                    "error_detail",
                    "created_at",
                    "resolved_at",
                )
            }
        )
    return {"items": items}


@router.post("/dead-letters/{letter_id}/retry", status_code=201)
def retry_dead_letter(
    letter_id: str,
    session: Session = Depends(get_session),
    actor: Principal = Depends(principal),
):
    letter = session.get(DeadLetter, letter_id)
    if letter is None:
        raise HTTPException(404, "Dead letter not found")
    original = session.get(SyncJob, letter.job_id)
    job_scope(session, actor, original, write=True)
    query = dict(original.query)
    if letter.source_version_id:
        version = session.get(SourceVersion, letter.source_version_id)
        query["original_ids"] = [version.original_id]
    job = create_job(
        session,
        original.source_id,
        actor,
        kind="reprocess",
        window_start=original.window_start,
        window_end=original.window_end,
        query=query,
    )
    audit_job(
        session, actor, "retry_dead_letter", job.id, {"dead_letter_id": letter.id}
    )
    session.commit()
    return job_dict(job)
