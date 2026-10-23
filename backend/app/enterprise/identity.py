"""Exact, effective-dated identity resolution; descriptions are never fuzzy merged."""

from datetime import datetime, timezone
from sqlalchemy import select, or_
from app.models import (
    Tool,
    Chamber,
    Position,
    Assembly,
    Subsystem,
    ComponentInstance,
    ComponentDefinition,
)
from .models import EntityAlias

ENTITY_MODELS = {
    "tool": Tool,
    "chamber": Chamber,
    "position": Position,
    "component": ComponentInstance,
    "definition": ComponentDefinition,
}


def aware(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("Engineering timestamps require a UTC offset")
    return value.astimezone(timezone.utc)


def resolve_alias(session, source_id, entity_type, external_id, at):
    if entity_type not in ENTITY_MODELS:
        raise ValueError("Unsupported entity type")
    if not external_id:
        return None, "missing"
    aliases = session.scalars(
        select(EntityAlias).where(
            EntityAlias.source_id == source_id,
            EntityAlias.entity_type == entity_type,
            EntityAlias.external_id == external_id,
            EntityAlias.verification_status == "verified",
            EntityAlias.valid_from <= at,
            or_(EntityAlias.valid_to.is_(None), EntityAlias.valid_to > at),
        )
    ).all()
    ids = {a.canonical_id for a in aliases}
    if len(ids) > 1:
        return None, "ambiguous"
    if not ids:
        return None, "unresolved"
    id = next(iter(ids))
    return (
        (id, "exact_verified_alias")
        if session.get(ENTITY_MODELS[entity_type], id)
        else (None, "dangling_alias")
    )


def match_payload(session, source_id, payload, at):
    matched = {}
    issues = []
    methods = {}
    fields = [
        ("tool_alias", "tool", "tool_id"),
        ("chamber_alias", "chamber", "chamber_id"),
        ("position_alias", "position", "position_id"),
        ("component_serial", "component", "component_id"),
        ("old_component_serial", "component", "old_component_id"),
        ("part_number", "definition", "definition_id"),
    ]
    for field, kind, key in fields:
        if payload.get(field) is None:
            continue
        id, method = resolve_alias(session, source_id, kind, str(payload[field]), at)
        if id is None and method == "unresolved":
            # Exact canonical serial and part-number lookup is deterministic and
            # does not create or merge unknown identities.
            model = (
                ComponentInstance
                if kind == "component"
                else ComponentDefinition
                if kind == "definition"
                else None
            )
            attr = "serial_number" if kind == "component" else "part_number"
            obj = (
                session.scalar(
                    select(model).where(getattr(model, attr) == payload[field])
                )
                if model
                else None
            )
            if obj is not None:
                id, method = obj.id, "exact_canonical_identifier"
        if id is None:
            issues.append(
                {
                    "field": field,
                    "code": method,
                    "message": f"{field} requires a verified exact identity mapping",
                }
            )
        else:
            matched[key] = id
            methods[key] = method
    tool = session.get(Tool, matched.get("tool_id")) if matched.get("tool_id") else None
    chamber = (
        session.get(Chamber, matched.get("chamber_id"))
        if matched.get("chamber_id")
        else None
    )
    position = (
        session.get(Position, matched.get("position_id"))
        if matched.get("position_id")
        else None
    )
    if chamber and tool and chamber.tool_id != tool.id:
        issues.append(
            {
                "field": "chamber_alias",
                "code": "hierarchy_mismatch",
                "message": "Chamber belongs to another tool",
            }
        )
    if position and chamber:
        assembly = session.get(Assembly, position.assembly_id)
        sub = session.get(Subsystem, assembly.subsystem_id)
        if sub.chamber_id != chamber.id:
            issues.append(
                {
                    "field": "position_alias",
                    "code": "hierarchy_mismatch",
                    "message": "Position belongs to another chamber",
                }
            )
    component = (
        session.get(ComponentInstance, matched.get("component_id"))
        if matched.get("component_id")
        else None
    )
    if (
        component
        and matched.get("definition_id")
        and component.definition_id != matched["definition_id"]
    ):
        issues.append(
            {
                "field": "part_number",
                "code": "identity_conflict",
                "message": "Serialized component has a different canonical part definition",
            }
        )
    if (
        component
        and payload.get("revision")
        and component.revision != payload["revision"]
    ):
        issues.append(
            {
                "field": "revision",
                "code": "revision_conflict",
                "message": "Reported revision differs from canonical serialized identity",
            }
        )
    matched["_matching_methods"] = methods
    return matched, issues
