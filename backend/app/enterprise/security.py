"""Source/equipment/collection authorization for ingestion and source evidence."""

from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select

from app.auth import Principal
from .contracts import SourceScope
from .models import EnterpriseSource, EntityAlias

LEGACY_SOURCE_SCOPES = {
    "informs-demo": "maintenance",
    "lam-demo": "parts",
    "fdc-demo": "fdc",
}


def authorize_source(
    session,
    actor: Principal,
    source: EnterpriseSource,
    *,
    write: bool = False,
    equipment_alias: str | None = None,
    collection: str | None = None,
    at: datetime | None = None,
) -> SourceScope:
    if write and actor.role not in {"editor", "admin"}:
        raise HTTPException(403, "Engineering editor or admin access is required")
    anonymous_demo = (
        actor.anonymous_demo
        and source.classification == "synthetic"
        and source.connector_kind == "synthetic_file"
    )
    if not anonymous_demo and actor.role != "admin":
        names = {source.id, LEGACY_SOURCE_SCOPES.get(source.id)}
        if not names.intersection(actor.sources):
            raise HTTPException(403, "Principal is not authorized for this source")
    maximum_equipment = set(source.authorized_equipment)
    maximum_collections = set(source.authorized_collections)
    if actor.role == "admin" or anonymous_demo:
        equipment, collections = maximum_equipment, maximum_collections
    else:
        when = at or datetime.now(timezone.utc)
        canonical: dict[str, set[str]] = {}
        for alias in session.scalars(
            select(EntityAlias).where(
                EntityAlias.source_id == source.id,
                EntityAlias.entity_type == "tool",
                EntityAlias.verification_status == "verified",
                EntityAlias.valid_from <= when,
                (EntityAlias.valid_to.is_(None)) | (EntityAlias.valid_to > when),
            )
        ):
            canonical.setdefault(alias.external_id, set()).add(alias.canonical_id)
        equipment = {
            alias
            for alias in maximum_equipment
            if alias in actor.equipment
            or (
                len(canonical.get(alias, set())) == 1
                and next(iter(canonical[alias])) in actor.equipment
            )
        }
        collections = maximum_collections.intersection(actor.collections)
    if not equipment or not collections:
        raise HTTPException(
            403, "Explicit equipment and collection permissions are required"
        )
    if equipment_alias is not None and equipment_alias not in equipment:
        raise HTTPException(403, "Equipment is outside the authorized source scope")
    if collection is not None and collection not in collections:
        raise HTTPException(403, "Collection is outside the authorized source scope")
    return SourceScope(
        source_id=source.id,
        equipment_aliases=frozenset(equipment),
        collections=frozenset(collections),
    )


def permitted_sources(session, actor: Principal, *, write: bool = False):
    result = []
    for source in session.scalars(
        select(EnterpriseSource).order_by(EnterpriseSource.id)
    ):
        try:
            scope = authorize_source(session, actor, source, write=write)
        except HTTPException:
            continue
        result.append((source, scope))
    return result
