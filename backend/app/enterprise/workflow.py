"""Evidence staging and explicit atomic engineering promotion into existing domains."""

from __future__ import annotations
import base64, hashlib, json
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import select, or_
from app.models import (
    RawSourceRecord,
    Installation,
    ComponentInstance,
    ComponentDefinition,
    Position,
    Assembly,
    Subsystem,
    Chamber,
    Tool,
    Compatibility,
    WorkOrder,
    MaintenanceAction,
    ReplacementEvent,
    PMPlan,
    PMDueEvent,
    FailureEpisode,
    Evidence,
    SourceConflict,
    AuditLog,
)
from .models import EnterpriseSource, SourceVersion, FactProposal, EngineeringReview
from .identity import aware, match_payload, resolve_alias
from .contracts import SourceDocument


class WorkflowConflict(ValueError):
    def __init__(self, message, preview=None):
        super().__init__(message)
        self.preview = preview


def _now():
    return datetime.now(timezone.utc)


def _hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _subject(actor):
    return actor if isinstance(actor, str) else actor.subject


def _role(actor):
    return "service" if isinstance(actor, str) else actor.role


def _audit(session, actor, action, entity, id, detail):
    session.add(
        AuditLog(
            id=str(uuid4()),
            timestamp=_now(),
            actor=_subject(actor),
            role=_role(actor),
            action=action,
            entity_type=entity,
            entity_id=id,
            detail=detail,
        )
    )


def _new_raw(session, source, document, metadata, *, suffix=""):
    fingerprint = _hash(
        {
            "source": source.id,
            "metadata": metadata,
            "content_hash": document.content_hash,
            "suffix": suffix,
        }
    )
    existing = session.scalar(
        select(RawSourceRecord).where(RawSourceRecord.fingerprint == fingerprint)
    )
    if existing:
        return existing
    record = RawSourceRecord(
        id=str(uuid4()),
        source="enterprise:" + source.id,
        source_id=document.original_id[:160],
        recorded_at=document.recorded_at,
        effective_at=document.effective_at,
        ingested_at=_now(),
        payload={
            "synthetic": True,
            "document": metadata,
            "content_b64": base64.b64encode(document.content).decode(),
            "content_hash": document.content_hash,
        },
        fingerprint=fingerprint,
        quality="original_retained",
        verification="unverified_source",
    )
    session.add(record)
    session.flush()
    return record


def stage_document(
    session,
    source: EnterpriseSource,
    document: SourceDocument,
    actor="worker",
    force_reprocess=False,
):
    """Stage immutable bytes and claims; caller owns commit/checkpoint transaction."""
    if source.classification != "synthetic" or not document.synthetic:
        raise ValueError("External foundation accepts synthetic documents only")
    if (
        document.equipment_alias not in source.authorized_equipment
        or document.collection not in source.authorized_collections
    ):
        raise PermissionError(
            "Document exceeds approved source equipment or collection"
        )
    if not source.enabled:
        raise PermissionError("Source is disabled")
    from .documents import parse_document
    from .extraction import extract_facts

    metadata = document.metadata().model_dump(mode="json")
    version = session.scalar(
        select(SourceVersion).where(
            SourceVersion.source_id == source.id,
            SourceVersion.original_id == document.original_id,
            SourceVersion.revision == document.revision,
            SourceVersion.content_hash == document.content_hash,
        )
    )
    if version:
        original = session.get(RawSourceRecord, version.raw_record_id).payload.get(
            "document", {}
        )
        if original != metadata:
            incoming = _new_raw(
                session, source, document, metadata, suffix="metadata-conflict"
            )
            existing_conflict = session.scalar(
                select(SourceConflict).where(
                    SourceConflict.record_a_id == version.raw_record_id,
                    SourceConflict.record_b_id == incoming.id,
                    SourceConflict.field == "source_metadata",
                )
            )
            if existing_conflict is None:
                session.add(
                    SourceConflict(
                        id=str(uuid4()),
                        component_id=None,
                        field="source_metadata",
                        record_a_id=version.raw_record_id,
                        record_b_id=incoming.id,
                        value_a=json.dumps(original, sort_keys=True),
                        value_b=json.dumps(metadata, sort_keys=True),
                        status="unresolved",
                        decision=None,
                        note=None,
                        resolved_at=None,
                    )
                )
            _audit(
                session,
                actor,
                "source_metadata_conflict",
                "source_version",
                version.id,
                {"source_id": source.id, "incoming_raw_record_id": incoming.id},
            )
            return {
                "source_version_id": version.id,
                "proposal_ids": [],
                "duplicate": True,
                "status": "metadata_conflict",
            }
        if not force_reprocess:
            return {
                "source_version_id": version.id,
                "proposal_ids": [
                    p.id
                    for p in session.scalars(
                        select(FactProposal).where(
                            FactProposal.source_version_id == version.id
                        )
                    )
                ],
                "duplicate": True,
                "status": version.parse_status,
            }
    parsed = parse_document(document)
    if version is None:
        raw = _new_raw(session, source, document, metadata)
        version = SourceVersion(
            id=str(uuid4()),
            source_id=source.id,
            raw_record_id=raw.id,
            original_id=document.original_id,
            revision=document.revision,
            content_hash=document.content_hash,
            mime_type=document.mime_type,
            content_b64=base64.b64encode(document.content).decode(),
            title=document.title,
            equipment_alias=document.equipment_alias,
            collection=document.collection,
            recorded_at=document.recorded_at,
            effective_at=document.effective_at,
            ingested_at=_now(),
            parser_version=parsed.parser_version,
            parse_status=parsed.status,
            structured_payload={},
        )
        session.add(version)
        session.flush()
    version.parser_version = parsed.parser_version
    version.parse_status = parsed.status
    prior = dict(version.structured_payload or {})
    parses = dict(prior.get("parses", {}))
    parses[parsed.parser_version] = parsed.model_dump(mode="json")
    prior.update(
        {
            "parsed": parsed.model_dump(mode="json"),
            "parses": parses,
            "metadata": metadata,
        }
    )
    version.structured_payload = prior
    proposals = []
    if parsed.status == "parsed":
        for draft in extract_facts(
            parsed, field_mapping=source.config.get("field_mapping")
        ):
            payload = dict(draft.payload)
            fingerprint = _hash({"kind": draft.kind, "payload": payload})
            extract_version = parsed.parser_version + "+" + draft.extraction_version
            existing = session.scalar(
                select(FactProposal).where(
                    FactProposal.source_version_id == version.id,
                    FactProposal.extraction_version == extract_version,
                    FactProposal.proposal_hash == fingerprint,
                )
            )
            if existing:
                proposals.append(existing.id)
                continue
            evidence = {
                field: [span.model_dump(mode="json") for span in spans]
                for field, spans in draft.evidence.items()
            }
            fact = FactProposal(
                id=str(uuid4()),
                source_version_id=version.id,
                kind=draft.kind,
                payload=payload,
                evidence=evidence,
                extraction_method=draft.method,
                extraction_version=extract_version,
                confidence=min(draft.confidence.values(), default=0),
                status="pending",
                match_status="unresolved",
                matched_entities={},
                validation_errors=[],
                created_at=_now(),
                proposal_hash=fingerprint,
                supersedes_id=None,
            )
            session.add(fact)
            session.flush()
            preview = preview_proposal(session, fact)
            fact.matched_entities = preview["matched_entities"]
            fact.match_status = (
                "conflict"
                if preview["conflicts"]
                else "unresolved"
                if preview["validation_errors"]
                else "matched"
            )
            fact.status = "conflict" if preview["conflicts"] else "pending"
            fact.validation_errors = preview["validation_errors"] + preview["conflicts"]
            proposals.append(fact.id)
        _audit(
            session,
            actor,
            "stage_document",
            "source_version",
            version.id,
            {
                "source_id": source.id,
                "proposal_ids": proposals,
                "parser_version": parsed.parser_version,
            },
        )
    return {
        "source_version_id": version.id,
        "proposal_ids": proposals,
        "duplicate": False,
        "status": parsed.status,
        "issues": parsed.issues,
    }


ingest_document = stage_document


def document_view(version, proposal=None):
    data = version.structured_payload or {}
    parsed = data.get("parsed", {})
    if proposal:
        for spans in proposal.evidence.values():
            if spans and isinstance(spans, list) and isinstance(spans[0], dict):
                parser = spans[0].get("parser_version")
                parsed = data.get("parses", {}).get(parser, parsed)
                break
    return {
        "id": version.id,
        "source_id": version.source_id,
        "original_id": version.original_id,
        "revision": version.revision,
        "title": version.title,
        "mime_type": version.mime_type,
        "content_hash": version.content_hash,
        "content_b64": version.content_b64,
        "equipment_alias": version.equipment_alias,
        "collection": version.collection,
        "recorded_at": version.recorded_at.isoformat(),
        "effective_at": version.effective_at.isoformat(),
        "ingested_at": version.ingested_at.isoformat(),
        "parser_version": parsed.get("parser_version", version.parser_version),
        "parse_status": parsed.get("status", version.parse_status),
        "text": parsed.get("text", ""),
        "blocks": parsed.get("blocks", []),
        "parsed": parsed,
        "metadata": data.get("metadata", {}),
        "synthetic": True,
    }


def proposal_view(proposal):
    return {
        field: getattr(proposal, field)
        for field in [
            "id",
            "source_version_id",
            "kind",
            "payload",
            "evidence",
            "extraction_method",
            "extraction_version",
            "confidence",
            "status",
            "match_status",
            "matched_entities",
            "validation_errors",
            "supersedes_id",
        ]
    } | {"created_at": proposal.created_at.isoformat()}


def preview_proposal(session, proposal):
    version = session.get(SourceVersion, proposal.source_version_id)
    payload = proposal.payload
    errors = []
    conflicts = []
    planned = []
    try:
        at = aware(
            payload.get("installed_at")
            or payload.get("completed_at")
            or payload.get("pm_completed_at")
            or version.effective_at
        )
    except (ValueError, TypeError):
        at = version.effective_at
        errors.append(
            {
                "field": "timestamp",
                "code": "invalid_timestamp",
                "message": "An explicit timezone-aware engineering event timestamp is required",
            }
        )
    if proposal.kind == "inventory":
        at = version.effective_at
    matched, match_errors = match_payload(session, version.source_id, payload, at)
    errors.extend(match_errors)
    expected_tool, _ = resolve_alias(
        session, version.source_id, "tool", version.equipment_alias, at
    )
    if expected_tool is None or (
        matched.get("tool_id") and matched["tool_id"] != expected_tool
    ):
        errors.append(
            {
                "field": "tool_alias",
                "code": "document_scope_mismatch",
                "message": "Claim equipment does not agree with the authorized source document identity",
            }
        )
    required = ["tool_alias", "chamber_alias", "component_serial"]
    if proposal.kind in {"installation", "replacement", "inventory"}:
        required += ["position_alias", "installed_at", "part_number"]
    if proposal.kind == "replacement":
        required += ["old_component_serial", "removed_at"]
    if proposal.kind == "maintenance":
        required += ["maintenance_type"]
    if proposal.kind == "failure_evidence":
        required += ["failure_id", "findings"]
    for field in required:
        if not payload.get(field):
            errors.append(
                {
                    "field": field,
                    "code": "missing_evidence",
                    "message": f"{field} is required; unknown values cannot be inferred",
                }
            )
    for field, value in payload.items():
        if (
            value is not None
            and field not in proposal.evidence
            and proposal.extraction_method != "human_correction"
        ):
            errors.append(
                {
                    "field": field,
                    "code": "missing_source_span",
                    "message": "Extracted claim has no supporting source location",
                }
            )
    parsed = document_view(version, proposal)["parsed"]
    for field, spans in proposal.evidence.items():
        for span in spans if isinstance(spans, list) else []:
            if not isinstance(span, dict):
                continue
            start, end = span.get("start"), span.get("end")
            if (
                not isinstance(start, int)
                or not isinstance(end, int)
                or not 0 <= start < end <= len(parsed.get("text", ""))
                or parsed.get("text", "")[start:end] != span.get("quote")
                or span.get("content_hash") != version.content_hash
            ):
                errors.append(
                    {
                        "field": field,
                        "code": "invalid_source_span",
                        "message": "Evidence must reference exact retained document text and hash",
                    }
                )
    component = (
        session.get(ComponentInstance, matched.get("component_id"))
        if matched.get("component_id")
        else None
    )
    position = (
        session.get(Position, matched.get("position_id"))
        if matched.get("position_id")
        else None
    )
    if component and position:
        ass = session.get(Assembly, position.assembly_id)
        sub = session.get(Subsystem, ass.subsystem_id)
        ch = session.get(Chamber, sub.chamber_id)
        tool = session.get(Tool, ch.tool_id)
        definition = session.get(ComponentDefinition, component.definition_id)
        if definition.category != sub.name:
            errors.append(
                {
                    "field": "position_alias",
                    "code": "incompatible_position",
                    "message": "Component physical category is incompatible with target subsystem",
                }
            )
        compatible = session.scalar(
            select(Compatibility).where(
                Compatibility.definition_id == definition.id,
                Compatibility.configuration_id == tool.configuration_id,
                Compatibility.effective_from <= at,
                or_(
                    Compatibility.effective_to.is_(None),
                    Compatibility.effective_to > at,
                ),
            )
        )
        if not compatible:
            errors.append(
                {
                    "field": "part_number",
                    "code": "configuration_unverified",
                    "message": "Applicable equipment compatibility has not been verified",
                }
            )
        if proposal.kind == "inventory":
            active = session.scalar(
                select(Installation).where(
                    Installation.position_id == position.id,
                    Installation.installed_at <= at,
                    or_(
                        Installation.removed_at.is_(None), Installation.removed_at > at
                    ),
                )
            )
            if active is None or active.component_id != component.id:
                conflicts.append(
                    {
                        "code": "inventory_disagreement",
                        "message": "Source inventory disagrees with effective-dated canonical installation; preserve both records and review lifecycle correction",
                        "canonical_component_id": active.component_id
                        if active
                        else None,
                        "reported_component_id": component.id,
                    }
                )
            else:
                planned.append(
                    {
                        "entity": "installation",
                        "action": "corroborate",
                        "details": {"installation_id": active.id},
                    }
                )
        elif proposal.kind in {"installation", "replacement"}:
            new_at = None
            remove_at = None
            try:
                new_at = aware(payload["installed_at"])
            except (KeyError, ValueError, TypeError):
                errors.append(
                    {
                        "field": "installed_at",
                        "code": "invalid_timestamp",
                        "message": "Actual installation timestamp with UTC offset required",
                    }
                )
            if proposal.kind == "replacement":
                try:
                    remove_at = aware(payload["removed_at"])
                except (KeyError, ValueError, TypeError):
                    errors.append(
                        {
                            "field": "removed_at",
                            "code": "invalid_timestamp",
                            "message": "Actual removal timestamp with UTC offset required",
                        }
                    )
                if new_at and remove_at and remove_at > new_at:
                    errors.append(
                        {
                            "field": "removed_at",
                            "code": "reversed_replacement",
                            "message": "Removal must not follow replacement installation",
                        }
                    )
            old_id = matched.get("old_component_id")
            if proposal.kind == "replacement" and old_id == component.id:
                errors.append(
                    {
                        "field": "old_component_serial",
                        "code": "same_serial_replacement",
                        "message": "Replacement must identify a distinct incoming serial; reinstallation/refurbishment requires its own reviewed workflow",
                    }
                )
            old_install = None
            if proposal.kind == "replacement" and remove_at and old_id:
                old_install = session.scalar(
                    select(Installation)
                    .where(
                        Installation.component_id == old_id,
                        Installation.position_id == position.id,
                        Installation.installed_at < remove_at,
                        or_(
                            Installation.removed_at.is_(None),
                            Installation.removed_at >= remove_at,
                        ),
                    )
                    .order_by(Installation.installed_at.desc())
                )
                if old_install is None:
                    conflicts.append(
                        {
                            "code": "old_installation_mismatch",
                            "message": "Removed serial is not documented in the target slot at removal time",
                        }
                    )
                elif (
                    old_install.removed_at is not None
                    and old_install.removed_at != remove_at
                ):
                    conflicts.append(
                        {
                            "code": "removal_time_conflict",
                            "message": "Removal differs from the canonical installation history",
                        }
                    )
                else:
                    matched["old_installation_id"] = old_install.id
            if new_at:
                exact = session.scalar(
                    select(Installation).where(
                        Installation.component_id == component.id,
                        Installation.position_id == position.id,
                        Installation.installed_at == new_at,
                    )
                )
                if exact:
                    matched["existing_installation_id"] = exact.id
                for existing in session.scalars(
                    select(Installation).where(
                        or_(
                            Installation.component_id == component.id,
                            Installation.position_id == position.id,
                        ),
                        or_(
                            Installation.removed_at.is_(None),
                            Installation.removed_at > new_at,
                        ),
                    )
                ):
                    if exact and existing.id == exact.id:
                        continue
                    if (
                        old_install
                        and existing.id == old_install.id
                        and remove_at
                        and remove_at <= new_at
                    ):
                        continue
                    conflicts.append(
                        {
                            "code": "overlapping_installation",
                            "message": "Serialized component or position already has an overlapping installation",
                            "installation_id": existing.id,
                        }
                    )
                planned.append(
                    {
                        "entity": "installation",
                        "action": "reuse" if exact else "create",
                        "details": {
                            "component_id": component.id,
                            "position_id": position.id,
                            "installed_at": new_at.isoformat(),
                        },
                    }
                )
                if old_install:
                    planned.insert(
                        0,
                        {
                            "entity": "installation",
                            "action": "remove",
                            "details": {
                                "id": old_install.id,
                                "removed_at": remove_at.isoformat(),
                            },
                        },
                    )
    if proposal.kind == "maintenance":
        if not payload.get("completed_at") and not payload.get("pm_completed_at"):
            errors.append(
                {
                    "field": "completed_at",
                    "code": "missing_timestamp",
                    "message": "A maintenance completion timestamp must be explicit",
                }
            )
        planned.append(
            {
                "entity": "maintenance_action",
                "action": "record_completion",
                "details": {"failure_created": False, "exposure_reset": False},
            }
        )
    if proposal.kind == "failure_evidence" and payload.get("failure_id"):
        episode = session.get(FailureEpisode, payload["failure_id"])
        if episode is None:
            errors.append(
                {
                    "field": "failure_id",
                    "code": "unresolved_episode",
                    "message": "Evidence must reference an existing failure episode",
                }
            )
        elif episode.chamber_id != matched.get("chamber_id") or (
            episode.component_id and episode.component_id != matched.get("component_id")
        ):
            errors.append(
                {
                    "field": "failure_id",
                    "code": "episode_identity_conflict",
                    "message": "Evidence identity does not agree with the existing failure episode",
                }
            )
        planned.append(
            {
                "entity": "evidence",
                "action": "associate",
                "details": {
                    "failure_id": payload["failure_id"],
                    "failure_adjudication_changed": False,
                },
            }
        )
    can_approve = (
        not errors and not conflicts and proposal.status in {"pending", "conflict"}
    )
    return {
        "proposal": proposal_view(proposal),
        "document": document_view(version, proposal),
        "matched_entities": matched,
        "validation_errors": errors,
        "conflicts": conflicts,
        "planned_changes": planned,
        "can_approve": can_approve,
        "synthetic": True,
    }


def review_proposal(session, proposal_id, decision, note, actor, corrections=None):
    proposal = session.scalar(
        select(FactProposal).where(FactProposal.id == proposal_id).with_for_update()
    )
    if proposal is None:
        raise KeyError("Proposal not found")
    if decision == "approve" and proposal.status == "approved":
        version = session.get(SourceVersion, proposal.source_version_id)
        authorize_proposal_entities(
            session,
            actor,
            version,
            proposal.matched_entities,
            payload=proposal.payload,
            write=True,
        )
        return {
            "proposal": proposal_view(proposal),
            "idempotent": True,
            "canonical": proposal.matched_entities.get("_canonical", {}),
        }
    if proposal.status not in {"pending", "conflict"}:
        raise WorkflowConflict(
            "Proposal is already finalized; preserve history and stage a corrected claim"
        )
    version = session.get(SourceVersion, proposal.source_version_id)
    authorized_preview = preview_proposal(session, proposal)
    authorize_proposal_entities(
        session,
        actor,
        version,
        authorized_preview["matched_entities"],
        payload=proposal.payload,
        write=True,
    )
    authorize_proposal_entities(
        session,
        actor,
        version,
        proposal.matched_entities,
        payload=proposal.payload,
        write=True,
    )
    before = proposal_view(proposal)
    if decision == "correct":
        allowed = {
            "tool_alias",
            "chamber_alias",
            "position_alias",
            "component_serial",
            "old_component_serial",
            "part_number",
            "revision",
            "installed_at",
            "removed_at",
            "completed_at",
            "pm_completed_at",
            "maintenance_type",
            "reason",
            "replacement_reason",
            "findings",
            "failure_id",
            "work_order_reference",
            "symptom",
            "diagnosis",
        }
        if not corrections or set(corrections) - allowed:
            raise ValueError("Corrections require supported engineering claim fields")
        payload = {**proposal.payload, **corrections}
        new = FactProposal(
            id=str(uuid4()),
            source_version_id=proposal.source_version_id,
            kind=proposal.kind,
            payload=payload,
            evidence=dict(proposal.evidence),
            extraction_method="human_correction",
            extraction_version=proposal.extraction_version + "+review",
            confidence=proposal.confidence,
            status="pending",
            match_status="unresolved",
            matched_entities={},
            validation_errors=[],
            created_at=_now(),
            proposal_hash=_hash(
                {"kind": proposal.kind, "payload": payload, "supersedes": proposal.id}
            ),
            supersedes_id=proposal.id,
        )
        session.add(new)
        session.flush()
        proposal.status = "superseded"
        preview = preview_proposal(session, new)
        authorize_proposal_entities(
            session,
            actor,
            version,
            preview["matched_entities"],
            payload=new.payload,
            write=True,
        )
        new.matched_entities = preview["matched_entities"]
        new.validation_errors = preview["validation_errors"] + preview["conflicts"]
        new.match_status = "matched" if not new.validation_errors else "unresolved"
        result = {
            "proposal": proposal_view(new),
            "id": new.id,
            "superseded_id": proposal.id,
            "canonical": {},
        }
    elif decision == "reject":
        proposal.status = "rejected"
        result = {"proposal": proposal_view(proposal), "canonical": {}}
    elif decision == "approve":
        preview = preview_proposal(session, proposal)
        if not preview["can_approve"]:
            raise WorkflowConflict(
                "Proposal requires identity, evidence or conflict correction before approval",
                preview,
            )
        version = session.get(SourceVersion, proposal.source_version_id)
        payload = proposal.payload
        matched = preview["matched_entities"]
        canonical = {}
        for key, model in [
            ("component_id", ComponentInstance),
            ("old_component_id", ComponentInstance),
            ("position_id", Position),
        ]:
            if matched.get(key):
                session.scalar(
                    select(model).where(model.id == matched[key]).with_for_update()
                )
        preview = preview_proposal(session, proposal)
        if not preview["can_approve"]:
            raise WorkflowConflict(
                "Canonical state changed while acquiring review locks; refresh preview",
                preview,
            )
        matched = preview["matched_entities"]
        authorize_proposal_entities(
            session, actor, version, matched, payload=proposal.payload, write=True
        )
        if proposal.kind in {"installation", "replacement"}:
            installed_at = aware(payload["installed_at"])
            existing = matched.get("existing_installation_id")
            if existing:
                canonical = {"installation_id": existing, "reused": True}
            else:
                wo_id = "ent-wo-" + proposal.id
                session.add(
                    WorkOrder(
                        id=wo_id,
                        chamber_id=matched["chamber_id"],
                        title="Reviewed synthetic " + proposal.kind,
                        kind="replacement"
                        if proposal.kind == "replacement"
                        else "installation",
                        status="completed",
                        opened_at=aware(
                            payload.get("removed_at") or payload["installed_at"]
                        ),
                        completed_at=installed_at,
                        source_record_id=version.raw_record_id,
                    )
                )
                session.flush()
                if proposal.kind == "replacement":
                    old = session.get(Installation, matched["old_installation_id"])
                    old.removed_at = aware(payload["removed_at"])
                    old.removal_reason = payload.get(
                        "replacement_reason"
                    ) or payload.get("reason", "Reviewed source replacement record")
                    session.get(
                        ComponentInstance, old.component_id
                    ).disposition = "removed_pending_review"
                    session.flush()
                    session.add(
                        MaintenanceAction(
                            id="ent-remove-" + proposal.id,
                            work_order_id=wo_id,
                            component_id=old.component_id,
                            timestamp=old.removed_at,
                            action="Reviewed removal",
                            findings=payload.get(
                                "findings",
                                "Source-reported replacement; no failure proven",
                            ),
                            confirmed_failure=False,
                        )
                    )
                    session.add(
                        ReplacementEvent(
                            id="ent-repl-" + proposal.id,
                            old_component_id=matched["old_component_id"],
                            new_component_id=matched["component_id"],
                            work_order_id=wo_id,
                            timestamp=installed_at,
                            reason=payload.get("replacement_reason")
                            or payload.get("reason", "Reviewed source replacement"),
                        )
                    )
                install_id = "ent-ins-" + proposal.id
                session.add(
                    Installation(
                        id=install_id,
                        component_id=matched["component_id"],
                        position_id=matched["position_id"],
                        installed_at=installed_at,
                        removed_at=None,
                        reason=payload.get("replacement_reason")
                        or payload.get("reason", "Reviewed source installation"),
                        removal_reason=None,
                        maintenance_reference=wo_id,
                        source_record_id=version.raw_record_id,
                    )
                )
                session.get(
                    ComponentInstance, matched["component_id"]
                ).disposition = "installed"
                session.add(
                    MaintenanceAction(
                        id="ent-install-" + proposal.id,
                        work_order_id=wo_id,
                        component_id=matched["component_id"],
                        timestamp=installed_at,
                        action="Reviewed installation",
                        findings=payload.get(
                            "findings", "Identity verified by engineering review"
                        ),
                        confirmed_failure=False,
                    )
                )
                canonical = {
                    "installation_id": install_id,
                    "work_order_id": wo_id,
                    "failure_created": False,
                }
        elif proposal.kind == "maintenance":
            completed = aware(payload.get("pm_completed_at") or payload["completed_at"])
            wo_id = "ent-wo-" + proposal.id
            session.add(
                WorkOrder(
                    id=wo_id,
                    chamber_id=matched["chamber_id"],
                    title="Reviewed synthetic maintenance completion",
                    kind=payload["maintenance_type"],
                    status="completed",
                    opened_at=completed,
                    completed_at=completed,
                    source_record_id=version.raw_record_id,
                )
            )
            session.flush()
            session.add(
                MaintenanceAction(
                    id="ent-maint-" + proposal.id,
                    work_order_id=wo_id,
                    component_id=matched["component_id"],
                    timestamp=completed,
                    action="Reviewed " + payload["maintenance_type"],
                    findings=payload.get(
                        "findings", "Source-reported maintenance completion"
                    ),
                    confirmed_failure=False,
                )
            )
            if payload["maintenance_type"] in {"pm", "preventive"}:
                component = session.get(ComponentInstance, matched["component_id"])
                plan = session.scalar(
                    select(PMPlan).where(
                        PMPlan.definition_id == component.definition_id,
                        PMPlan.effective_from <= completed,
                        or_(
                            PMPlan.effective_to.is_(None),
                            PMPlan.effective_to > completed,
                        ),
                    )
                )
                if plan:
                    session.add(
                        PMDueEvent(
                            id="ent-pm-" + proposal.id,
                            plan_id=plan.id,
                            component_id=component.id,
                            due_at=None,
                            status="completed",
                            completed_work_order_id=wo_id,
                        )
                    )
            canonical = {
                "work_order_id": wo_id,
                "failure_created": False,
                "exposure_reset": False,
            }
        elif proposal.kind == "failure_evidence":
            evidence_id = "ent-evidence-" + proposal.id
            session.add(
                Evidence(
                    id=evidence_id,
                    failure_id=payload["failure_id"],
                    timestamp=version.effective_at,
                    kind="reviewed_source_document",
                    description=payload["findings"],
                    quality="human_reviewed_synthetic_report",
                    source_record_id=version.raw_record_id,
                )
            )
            canonical = {
                "evidence_id": evidence_id,
                "failure_id": payload["failure_id"],
                "failure_adjudication_changed": False,
            }
        elif proposal.kind == "inventory":
            canonical = {
                "corroborated": True,
                "installation_id": preview["planned_changes"][0]["details"][
                    "installation_id"
                ],
            }
        proposal.status = "approved"
        proposal.match_status = "verified"
        proposal.matched_entities = {**matched, "_canonical": canonical}
        proposal.validation_errors = []
        result = {
            "proposal": proposal_view(proposal),
            "canonical": canonical,
            "idempotent": False,
        }
    else:
        raise ValueError("Unsupported review decision")
    session.add(
        EngineeringReview(
            id=str(uuid4()),
            entity_type="fact_proposal",
            entity_id=proposal.id,
            actor=_subject(actor),
            decision=decision,
            note=note,
            created_at=_now(),
            before_after={
                "before": before,
                "after": result["proposal"],
                "corrections": corrections or {},
                "canonical": result["canonical"],
            },
        )
    )
    _audit(
        session,
        actor,
        "review_fact_proposal",
        "fact_proposal",
        proposal.id,
        {
            "decision": decision,
            "note": note,
            "source_version_id": proposal.source_version_id,
            "canonical": result["canonical"],
        },
    )
    session.flush()
    if decision == "approve":
        if proposal.kind in {"installation", "replacement"}:
            from .telemetry import rebuild_component_exposure

            for component_id in {
                proposal.matched_entities.get("component_id"),
                proposal.matched_entities.get("old_component_id"),
            } - {None}:
                rebuild_component_exposure(session, component_id)
        refresh_pending_proposals(session, actor)
        session.flush()
    return result


def refresh_pending_proposals(session, actor="reconciliation-service"):
    """Re-evaluate staged observations after canonical changes; never auto-promote."""
    changed = 0
    for proposal in session.scalars(
        select(FactProposal).where(FactProposal.status.in_(["pending", "conflict"]))
    ):
        preview = preview_proposal(session, proposal)
        old = (
            proposal.match_status,
            proposal.validation_errors,
            proposal.matched_entities,
        )
        proposal.match_status = (
            "conflict"
            if preview["conflicts"]
            else "unresolved"
            if preview["validation_errors"]
            else "matched"
        )
        proposal.validation_errors = preview["validation_errors"] + preview["conflicts"]
        proposal.matched_entities = preview["matched_entities"]
        proposal.status = "conflict" if preview["conflicts"] else "pending"
        if old != (
            proposal.match_status,
            proposal.validation_errors,
            proposal.matched_entities,
        ):
            changed += 1
            _audit(
                session,
                actor,
                "refresh_staged_reconciliation",
                "fact_proposal",
                proposal.id,
                {
                    "source_version_id": proposal.source_version_id,
                    "match_status": proposal.match_status,
                    "error_codes": [e.get("code") for e in proposal.validation_errors],
                },
            )
    return changed


def authorize_proposal_entities(
    session, actor, version, matched, *, payload=None, write=False
):
    """Authorize canonical identities independently of source-document ownership.

    A scoped source record can contain an erroneous or human-corrected reference
    to another tool. Exact matching never grants permission to that identity.
    Uninstalled spares have no history to scope, so they require an authorized
    and resolved target tool, chamber and physical slot instead.
    """
    from fastapi import HTTPException
    from app.auth import Principal
    from .canonical_security import canonical_scope
    from .security import authorize_source

    if not isinstance(actor, Principal):
        raise ValueError("Engineering review requires a verified principal")
    source = session.get(EnterpriseSource, version.source_id)
    authorize_source(
        session,
        actor,
        source,
        write=write,
        equipment_alias=version.equipment_alias,
        collection=version.collection,
        at=version.effective_at,
    )
    scope = canonical_scope(
        session, actor, "synthetic" if actor.anonymous_demo else "enterprise"
    )
    if scope.unrestricted:
        return
    target_tool = matched.get("tool_id")
    target_chamber = matched.get("chamber_id")
    target_position = matched.get("position_id")
    if target_tool:
        scope.require_tool(target_tool)
    if target_chamber:
        scope.require_chamber(session, target_chamber)
    if target_position:
        position = session.get(Position, target_position)
        if position is None:
            raise HTTPException(403, "Proposed canonical identity cannot be authorized")
        assembly = session.get(Assembly, position.assembly_id)
        subsystem = session.get(Subsystem, assembly.subsystem_id)
        scope.require_chamber(session, subsystem.chamber_id)
        if target_chamber and subsystem.chamber_id != target_chamber:
            raise HTTPException(
                403, "Proposed position is outside the authorized target chamber"
            )
    for key in ("component_id", "old_component_id"):
        component_id = matched.get(key)
        if not component_id:
            continue
        component = session.get(ComponentInstance, component_id)
        if component is None:
            raise HTTPException(403, "Proposed canonical identity cannot be authorized")
        history_tools = scope.component_tools(session, component_id)
        if history_tools:
            scope.require_component(session, component_id)
        elif not (
            component.disposition == "spare"
            and target_tool
            and target_chamber
            and target_position
        ):
            raise HTTPException(
                403,
                "Uninstalled component requires an authorized, resolved target tool and physical position",
            )
    for key in ("old_installation_id", "existing_installation_id"):
        if matched.get(key):
            scope.require_installation(session, matched[key])
    canonical = matched.get("_canonical", {})
    if canonical.get("installation_id"):
        scope.require_installation(session, canonical["installation_id"])
    if payload and payload.get("failure_id"):
        scope.require_failure(session, payload["failure_id"])
