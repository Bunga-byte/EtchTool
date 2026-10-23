"""Durable bounded ingestion, without a scheduler or a proprietary transport.

One run processes one connector page. Its source versions, staged proposals,
telemetry, metrics and checkpoint commit together. A persisted lease protects
the page; failure rolls it back before scheduling an exponential-backoff retry.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_, select, update

from app.models import AuditLog, RawSourceRecord
from .connectors import fixture_connector
from .contracts import (
    AccessDenied,
    CapabilityUnsupported,
    DocumentMetadata,
    PermanentConnectorError,
    SearchQuery,
    SourceScope,
    metadata_version_token,
)
from .models import DeadLetter, EnterpriseSource, SourceVersion, SyncCheckpoint, SyncJob
from .security import authorize_source

log = logging.getLogger("frip.enterprise")
LEASE_SECONDS = 120
MAX_WINDOW_DAYS = 366


class LeaseLost(RuntimeError):
    pass


def utcnow():
    return datetime.now(timezone.utc)


def audit_job(session, actor, action, entity_id, detail):
    session.add(
        AuditLog(
            id=str(uuid4()),
            timestamp=utcnow(),
            actor=actor.subject,
            role=actor.role,
            action=action,
            entity_type="sync_job",
            entity_id=entity_id,
            detail=detail,
        )
    )


def source_required(session, source_id):
    source = session.get(EnterpriseSource, source_id)
    if source is None:
        raise HTTPException(404, "Source not found")
    return source


def job_scope(session, actor, job, *, write=False):
    source = source_required(session, job.source_id)
    scope = authorize_source(session, actor, source, write=write, at=job.window_start)
    equipment = set(job.query.get("equipment_aliases", [])) or set(
        scope.equipment_aliases
    )
    collections = set(job.query.get("collections", [])) or set(scope.collections)
    if not equipment <= scope.equipment_aliases or not collections <= scope.collections:
        raise HTTPException(
            403, "Job contains equipment or collections outside the principal's scope"
        )
    return source, scope


def create_job(
    session,
    source_id,
    actor,
    *,
    kind="backfill",
    window_start,
    window_end,
    query=None,
    max_attempts=3,
):
    if kind not in {"backfill", "incremental", "reprocess"}:
        raise HTTPException(422, "Unsupported synchronization kind")
    if (
        window_start.tzinfo is None
        or window_end.tzinfo is None
        or not timedelta(0)
        < window_end - window_start
        <= timedelta(days=MAX_WINDOW_DAYS)
    ):
        raise HTTPException(
            422, "A bounded UTC-aware window of at most 366 days is required"
        )
    source = source_required(session, source_id)
    scope = authorize_source(session, actor, source, write=True, at=window_start)
    if not source.enabled:
        raise HTTPException(409, "Source is disabled")
    if (
        source.classification != "synthetic"
        or source.connector_kind != "synthetic_file"
    ):
        raise HTTPException(
            409,
            "No approved internal connector is installed; external mode accepts synthetic sources only",
        )
    filters = dict(query or {})
    allowed = {
        "equipment_aliases",
        "collections",
        "chamber_alias",
        "keyword",
        "part_number",
        "serial_number",
        "limit",
        "original_ids",
    }
    if set(filters) - allowed:
        raise HTTPException(422, "Unsupported source query fields")
    equipment = set(filters.get("equipment_aliases") or scope.equipment_aliases)
    collections = set(filters.get("collections") or scope.collections)
    if not equipment <= scope.equipment_aliases or not collections <= scope.collections:
        raise HTTPException(
            403, "Source query exceeds authorized equipment or collections"
        )
    filters.update(equipment_aliases=sorted(equipment), collections=sorted(collections))
    original_ids = filters.get("original_ids", [])
    if (
        not isinstance(original_ids, list)
        or len(original_ids) > 200
        or any(not isinstance(x, str) or len(x) > 200 for x in original_ids)
    ):
        raise HTTPException(
            422, "original_ids must be a bounded list of source identifiers"
        )
    try:
        SearchQuery(
            **{k: v for k, v in filters.items() if k != "original_ids"},
            start_at=window_start,
            end_at=window_end,
        )
    except ValueError:
        raise HTTPException(422, "Source query validation failed") from None
    if not 1 <= max_attempts <= 8:
        raise HTTPException(422, "max_attempts must be between 1 and 8")
    job = SyncJob(
        id=str(uuid4()),
        source_id=source_id,
        kind=kind,
        status="pending",
        cursor=None,
        window_start=window_start,
        window_end=window_end,
        attempts=0,
        max_attempts=max_attempts,
        next_attempt_at=None,
        created_at=utcnow(),
        started_at=None,
        finished_at=None,
        error=None,
        metrics={
            "discovered": 0,
            "processed": 0,
            "rejected": 0,
            "unchanged": 0,
            "pages": 0,
            "consecutive_failures": 0,
        },
        requested_by=actor.subject,
        query=filters,
    )
    session.add(job)
    audit_job(
        session,
        actor,
        "create_sync_job",
        job.id,
        {"source_id": source_id, "kind": kind},
    )
    session.flush()
    return job


def _query_hash(job):
    return hashlib.sha256(
        json.dumps(
            {
                "source": job.source_id,
                "start": job.window_start.isoformat(),
                "end": job.window_end.isoformat(),
                "query": job.query,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()


def _dead_letter(session, job, version_id, stage, code, detail):
    session.add(
        DeadLetter(
            id=str(uuid4()),
            job_id=job.id,
            source_version_id=version_id,
            stage=stage,
            error_code=code,
            error_detail=detail,
            created_at=utcnow(),
            resolved_at=None,
        )
    )


def run_job(session, job_id, actor, *, connector_factory=fixture_connector, now=None):
    """Run one page; caller must not wrap this operation in a wider transaction."""
    now = now or utcnow()
    job = session.get(SyncJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    source, scope = job_scope(session, actor, job, write=True)
    scope = SourceScope(
        source_id=source.id,
        equipment_aliases=frozenset(job.query["equipment_aliases"]),
        collections=frozenset(job.query["collections"]),
    )
    if not source.enabled:
        raise HTTPException(409, "Source is disabled")
    if job.status == "running" and job.next_attempt_at and job.next_attempt_at > now:
        raise HTTPException(409, "Job already has an active execution lease")
    if job.status not in {"pending", "retry_wait", "running"}:
        raise HTTPException(409, "Job is terminal; use the authorized retry operation")
    if job.status == "retry_wait" and job.next_attempt_at and job.next_attempt_at > now:
        raise HTTPException(409, "Retry backoff has not elapsed")
    claim = session.execute(
        update(SyncJob)
        .where(
            SyncJob.id == job_id,
            or_(
                SyncJob.status == "pending",
                (SyncJob.status == "retry_wait") & (SyncJob.next_attempt_at <= now),
                (SyncJob.status == "running") & (SyncJob.next_attempt_at <= now),
            ),
        )
        .values(
            status="running",
            started_at=now,
            next_attempt_at=now + timedelta(seconds=LEASE_SECONDS),
            attempts=SyncJob.attempts + 1,
        )
    )
    if claim.rowcount != 1:
        session.rollback()
        raise HTTPException(409, "Another worker claimed the job")
    session.commit()
    job = session.get(SyncJob, job_id)
    try:
        if (
            source.classification != "synthetic"
            or source.connector_kind != "synthetic_file"
        ):
            raise PermanentConnectorError("unregistered external connector")
        connector = connector_factory(source.id)
        capabilities = connector.capabilities()
        if not capabilities.retrieve_documents or not capabilities.search:
            raise CapabilityUnsupported("document discovery and retrieval are required")
        if job.kind == "incremental" and not capabilities.incremental_polling:
            raise CapabilityUnsupported("incremental polling is unsupported")
        known = {}
        query_equipment = set(job.query["equipment_aliases"])
        query_collections = set(job.query["collections"])
        query_ids = set(job.query.get("original_ids", []))
        if job.kind != "reprocess":
            for version in session.scalars(
                select(SourceVersion)
                .where(SourceVersion.source_id == source.id)
                .order_by(SourceVersion.ingested_at)
            ):
                if (
                    version.equipment_alias not in query_equipment
                    or version.collection not in query_collections
                    or (query_ids and version.original_id not in query_ids)
                    or not job.window_start <= version.recorded_at < job.window_end
                ):
                    continue
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
                # Cache only the complete immutable original envelope. Body
                # revision/hash alone would hide equipment/time corrections
                # before the staging workflow could preserve their conflict.
                # A newer invalid envelope must not fall back to an older hint.
                known.pop(version.original_id, None)
                raw = session.get(RawSourceRecord, version.raw_record_id)
                if raw is None or not isinstance(raw.payload, dict):
                    continue
                try:
                    metadata = DocumentMetadata.model_validate(raw.payload.get("document"))
                except (ValueError, TypeError):
                    continue
                if (
                    metadata.original_id != version.original_id
                    or metadata.revision != version.revision
                    or metadata.content_hash != version.content_hash
                    or metadata.equipment_alias != version.equipment_alias
                    or metadata.collection != version.collection
                    or metadata.recorded_at != version.recorded_at
                    or metadata.effective_at != version.effective_at
                    or not metadata.synthetic
                ):
                    continue
                known[version.original_id] = metadata_version_token(metadata)
        query = SearchQuery(
            **{k: v for k, v in job.query.items() if k != "original_ids"},
            start_at=job.window_start,
            end_at=job.window_end,
            cursor=job.cursor,
            known_versions=known,
        )
        page = (
            connector.incremental(query, scope)
            if job.kind == "incremental"
            else connector.search(query, scope)
        )
        from .workflow import stage_document

        metrics = dict(job.metrics)
        allowed_ids = set(job.query.get("original_ids", []))
        metrics["unchanged"] = metrics.get("unchanged", 0) + page.unchanged_count
        for meta in page.items:
            if allowed_ids and meta.original_id not in allowed_ids:
                continue
            if (
                not scope.permits(meta.equipment_alias, meta.collection)
                or not job.window_start <= meta.recorded_at < job.window_end
            ):
                raise AccessDenied(
                    "Connector returned data outside the requested bounded scope"
                )
            authorize_source(
                session,
                actor,
                source,
                write=True,
                equipment_alias=meta.equipment_alias,
                collection=meta.collection,
                at=meta.effective_at,
            )
            document = connector.get_document(meta.original_id, scope)
            authorize_source(
                session,
                actor,
                source,
                write=True,
                equipment_alias=document.equipment_alias,
                collection=document.collection,
                at=document.effective_at,
            )
            if (
                document.metadata() != meta
                or document.source_system != connector.config.source_system
            ):
                raise PermanentConnectorError(
                    "source changed during bounded page retrieval"
                )
            metrics["discovered"] = metrics.get("discovered", 0) + 1
            result = stage_document(
                session,
                source,
                document,
                actor=actor.subject,
                force_reprocess=job.kind == "reprocess",
            )
            session.flush()
            version = session.get(SourceVersion, result["source_version_id"])
            processing_status = result.get("status", version.parse_status)
            if processing_status not in {"parsed", "ready"}:
                metrics["rejected"] = metrics.get("rejected", 0) + 1
                _dead_letter(
                    session,
                    job,
                    version.id,
                    "parsing",
                    processing_status,
                    "Original source retained; inspect parser issues and internal OCR requirements",
                )
            else:
                if source.id == "fdc-demo" and (
                    not result.get("duplicate") or job.kind == "reprocess"
                ):
                    from .telemetry import ingest_telemetry

                    try:
                        data = json.loads(document.content)
                    except (ValueError, UnicodeError):
                        raise PermanentConnectorError(
                            "telemetry export requires a typed JSON envelope"
                        ) from None
                    telemetry = ingest_telemetry(session, version, data, actor)
                    version.structured_payload = {
                        **version.structured_payload,
                        "telemetry_result": telemetry,
                    }
                    if telemetry.get("errors"):
                        metrics["rejected"] = metrics.get("rejected", 0) + len(
                            telemetry["errors"]
                        )
                        _dead_letter(
                            session,
                            job,
                            version.id,
                            "telemetry",
                            "row_validation",
                            "Telemetry row errors retained in calculation/ingestion evidence",
                        )
                metrics["processed"] = metrics.get("processed", 0) + (
                    0 if result.get("duplicate") else 1
                )
            if job.kind == "reprocess" and processing_status == "parsed":
                for letter in session.scalars(
                    select(DeadLetter).where(
                        DeadLetter.source_version_id == version.id,
                        DeadLetter.resolved_at.is_(None),
                        DeadLetter.stage == "parsing",
                        DeadLetter.error_code != "metadata_conflict",
                    )
                ):
                    letter.resolved_at = now
        metrics["pages"] = metrics.get("pages", 0) + 1
        metrics["consecutive_failures"] = 0
        with session.no_autoflush:
            lease = session.scalar(
                select(SyncJob.started_at).where(SyncJob.id == job.id).with_for_update()
            )
        if lease != now:
            raise LeaseLost("Another worker reclaimed this page")
        job.metrics = metrics
        job.cursor = page.next_cursor
        job.status = (
            "pending"
            if page.next_cursor
            else "succeeded_with_errors"
            if metrics.get("rejected", 0)
            else "succeeded"
        )
        job.next_attempt_at = None
        job.error = None
        job.finished_at = None if page.next_cursor else now
        stream = _query_hash(job)
        checkpoint = session.scalar(
            select(SyncCheckpoint).where(
                SyncCheckpoint.source_id == source.id, SyncCheckpoint.stream == stream
            )
        )
        cursor = json.dumps(
            {
                "cursor": page.next_cursor,
                "complete": not bool(page.next_cursor),
                "snapshot": page.snapshot,
            },
            sort_keys=True,
        )
        if checkpoint is None:
            session.add(
                SyncCheckpoint(
                    id=str(uuid4()),
                    source_id=source.id,
                    stream=stream,
                    cursor=cursor,
                    updated_at=now,
                    job_id=job.id,
                )
            )
        else:
            checkpoint.cursor, checkpoint.updated_at, checkpoint.job_id = (
                cursor,
                now,
                job.id,
            )
        source.last_success_at = now
        audit_job(
            session,
            actor,
            "sync_page_committed",
            job.id,
            {"source_id": source.id, "status": job.status, "metrics": metrics},
        )
        session.commit()
        log.info(
            json.dumps(
                {
                    "event": "sync_page_committed",
                    "job_id": job.id,
                    "source_id": source.id,
                    "status": job.status,
                    "metrics": metrics,
                }
            )
        )
    except Exception as exc:
        session.rollback()
        if isinstance(exc, LeaseLost):
            raise HTTPException(
                409, "Execution lease changed; page was rolled back"
            ) from None
        job = session.get(SyncJob, job_id)
        if job.started_at != now:
            raise HTTPException(
                409, "Execution lease changed; failed page was rolled back"
            ) from None
        metrics = dict(job.metrics)
        failures = metrics.get("consecutive_failures", 0) + 1
        metrics["consecutive_failures"] = failures
        job.metrics = metrics
        permanent = isinstance(
            exc,
            (
                AccessDenied,
                CapabilityUnsupported,
                PermanentConnectorError,
                PermissionError,
                HTTPException,
            ),
        )
        job.error = f"{type(exc).__name__}: source page failed; inspect authorized source/parser configuration"
        terminal = permanent or failures >= job.max_attempts
        job.status = "dead_letter" if terminal else "retry_wait"
        job.next_attempt_at = (
            None if terminal else now + timedelta(seconds=min(60, 2**failures))
        )
        job.finished_at = now if terminal else None
        if terminal:
            _dead_letter(session, job, None, "retrieval", type(exc).__name__, job.error)
        audit_job(
            session,
            actor,
            "sync_page_failed",
            job.id,
            {"error_type": type(exc).__name__, "retryable": not terminal},
        )
        session.commit()
        log.warning(
            json.dumps(
                {
                    "event": "sync_page_failed",
                    "job_id": job.id,
                    "error_type": type(exc).__name__,
                    "status": job.status,
                }
            )
        )
    return session.get(SyncJob, job_id)


def retry_job(session, job_id, actor):
    job = session.get(SyncJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    job_scope(session, actor, job, write=True)
    if job.status not in {"dead_letter", "retry_wait", "succeeded_with_errors"}:
        raise HTTPException(409, "Only failed or incomplete jobs can be retried")
    if job.status == "succeeded_with_errors":
        job.kind, job.cursor = "reprocess", None
    job.status, job.error, job.next_attempt_at, job.finished_at = (
        "pending",
        None,
        None,
        None,
    )
    job.metrics = {**job.metrics, "consecutive_failures": 0}
    audit_job(session, actor, "retry_sync_job", job.id, {"source_id": job.source_id})
    session.flush()
    return job


def enqueue_due_sources(session, actor, *, now=None):
    """Explicit opt-in periodic polling; no background thread polls by default."""
    if actor.role != "admin":
        raise HTTPException(
            403, "Only an approved scheduler identity may enqueue sources"
        )
    now = now or utcnow()
    result = []
    for source in session.scalars(
        select(EnterpriseSource).where(
            EnterpriseSource.enabled.is_(True),
            EnterpriseSource.polling_allowed.is_(True),
        )
    ):
        if (
            source.last_success_at
            and source.last_success_at + timedelta(seconds=source.interval_seconds)
            > now
        ):
            continue
        active = session.scalar(
            select(SyncJob).where(
                SyncJob.source_id == source.id,
                SyncJob.status.in_(["pending", "running", "retry_wait"]),
            )
        )
        if active:
            continue
        # A scheduler must be configured with an approved bounded range.
        start, end = (
            source.config.get("poll_window_start"),
            source.config.get("poll_window_end"),
        )
        if not start or not end:
            continue
        start, end = (
            datetime.fromisoformat(start.replace("Z", "+00:00")),
            datetime.fromisoformat(end.replace("Z", "+00:00")),
        )
        result.append(
            create_job(
                session,
                source.id,
                actor,
                kind="incremental",
                window_start=start,
                window_end=end,
            )
        )
    session.flush()
    return result
