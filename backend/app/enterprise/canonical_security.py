"""Equipment boundaries for the existing canonical API projections.

Approved canonical records do not bypass equipment authorization after source
ingestion. A serial with history on an unauthorized tool is withheld as a whole:
returning a partial lifetime would both leak history and corrupt engineering
denominators. Synthetic mode deliberately preserves the public fictional demo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from app.auth import Principal
from app import views
from app.models import (
    Chamber, ComponentInstance, DowntimeAttribution, DowntimeInterval,
    EquipmentEvent, Evidence, FailureEpisode, FDCPoint, Installation,
    MaintenanceAction, PMDueEvent, RawSourceRecord, Refurbishment, Assembly, Subsystem, Position,
    ReplacementEvent, SourceConflict, Tool, WorkOrder,
)
from app.seed import AS_OF
from .models import CalculationLineage, EnterpriseSource, ExposureDefinition, SourceVersion
from .security import authorize_source


@dataclass
class CanonicalScope:
    actor: Principal
    mode: str
    tool_ids: frozenset[str]
    unrestricted: bool = False
    _component_tools: dict[str, frozenset[str]] = field(default_factory=dict, repr=False)

    def require_tool(self, tool_id: str) -> None:
        if tool_id not in self.tool_ids:
            raise HTTPException(403, "Equipment is outside the authorized canonical scope")

    def require_chamber(self, session, chamber_id: str) -> Chamber:
        chamber = session.get(Chamber, chamber_id)
        if chamber is None:
            raise HTTPException(404, "Chamber not found")
        self.require_tool(chamber.tool_id)
        return chamber

    def component_tools(self, session, component_id: str) -> frozenset[str]:
        if component_id not in self._component_tools:
            component = session.get(ComponentInstance, component_id)
            if component is None:
                raise HTTPException(404, "Component not found")
            tool_ids = {views.location(session, installation)[4].id
                        for installation in views.history(session, component)}
            chamber_ids = set(session.scalars(select(FailureEpisode.chamber_id).where(FailureEpisode.component_id == component_id)))
            chamber_ids.update(session.scalars(select(FDCPoint.chamber_id).where(FDCPoint.component_id == component_id)))
            chamber_ids.update(session.scalars(select(WorkOrder.chamber_id).join(MaintenanceAction, MaintenanceAction.work_order_id == WorkOrder.id).where(MaintenanceAction.component_id == component_id)))
            chamber_ids.update(session.scalars(select(DowntimeInterval.chamber_id).join(DowntimeAttribution, DowntimeAttribution.downtime_id == DowntimeInterval.id).where(DowntimeAttribution.component_id == component_id)))
            tool_ids.update(session.scalars(select(Chamber.tool_id).where(Chamber.id.in_(chamber_ids))))
            self._component_tools[component_id] = frozenset(tool_ids)
        return self._component_tools[component_id]

    def require_component(self, session, component_id: str, *, evidence: bool = False) -> ComponentInstance:
        component = session.get(ComponentInstance, component_id)
        if component is None:
            raise HTTPException(404, "Component not found")
        if self.unrestricted:
            return component
        related = {component_id}
        for replacement in session.scalars(select(ReplacementEvent).where(
            (ReplacementEvent.old_component_id == component_id) | (ReplacementEvent.new_component_id == component_id)
        )):
            related.update((replacement.old_component_id, replacement.new_component_id))
        for related_id in related:
            tools = self.component_tools(session, related_id)
            if not tools or not tools <= self.tool_ids:
                raise HTTPException(403, "Complete component history is outside the authorized equipment scope")
        if evidence:
            require_raw_evidence(session, self, component_raw_ids(session, component_id))
            require_exposure_evidence(session, self, component_id)
        return component

    def require_failure(self, session, failure_id: str, *, evidence: bool = False) -> FailureEpisode:
        failure = session.get(FailureEpisode, failure_id)
        if failure is None:
            raise HTTPException(404, "Failure episode not found")
        if self.unrestricted:
            return failure
        self.require_chamber(session, failure.chamber_id)
        if failure.component_id:
            self.require_component(session, failure.component_id, evidence=evidence)
        for event in session.scalars(select(EquipmentEvent).where(EquipmentEvent.failure_id == failure_id)):
            self.require_chamber(session, event.chamber_id)
        for downtime in session.scalars(select(DowntimeInterval).where(DowntimeInterval.failure_id == failure_id)):
            self.require_chamber(session, downtime.chamber_id)
            for attribution in session.scalars(select(DowntimeAttribution).where(DowntimeAttribution.downtime_id == downtime.id)):
                self.require_component(session, attribution.component_id)
        if evidence:
            raw_ids = set(session.scalars(select(Evidence.source_record_id).where(Evidence.failure_id == failure_id)))
            raw_ids.update(session.scalars(select(EquipmentEvent.source_record_id).where(EquipmentEvent.failure_id == failure_id)))
            raw_ids.update(session.scalars(select(DowntimeInterval.source_record_id).where(DowntimeInterval.failure_id == failure_id)))
            require_raw_evidence(session, self, raw_ids)
        return failure

    def require_installation(self, session, installation_id: str) -> Installation:
        installation = session.get(Installation, installation_id)
        if installation is None:
            raise HTTPException(404, "Installation not found")
        self.require_component(session, installation.component_id)
        return installation


def canonical_scope(session, actor: Principal, mode: str) -> CanonicalScope:
    tools = list(session.scalars(select(Tool)))
    unrestricted = mode == "synthetic" or actor.role == "admin"
    allowed = {tool.id for tool in tools if unrestricted or tool.id in actor.equipment or tool.name in actor.equipment}
    if not unrestricted and not allowed:
        raise HTTPException(403, "Explicit canonical equipment permission is required")
    return CanonicalScope(actor=actor, mode=mode, tool_ids=frozenset(allowed), unrestricted=unrestricted)


def component_raw_ids(session, component_id: str) -> set[str]:
    ids = set(session.scalars(select(Installation.source_record_id).where(Installation.component_id == component_id)))
    ids.update(session.scalars(select(Refurbishment.source_record_id).where(Refurbishment.component_id == component_id)))
    ids.update(session.scalars(select(FDCPoint.source_record_id).where(FDCPoint.component_id == component_id)))
    ids.update(session.scalars(select(WorkOrder.source_record_id).join(MaintenanceAction, MaintenanceAction.work_order_id == WorkOrder.id).where(MaintenanceAction.component_id == component_id)))
    failures = list(session.scalars(select(FailureEpisode.id).where(FailureEpisode.component_id == component_id)))
    ids.update(session.scalars(select(Evidence.source_record_id).where(Evidence.failure_id.in_(failures))))
    ids.update(session.scalars(select(EquipmentEvent.source_record_id).where(EquipmentEvent.failure_id.in_(failures))))
    return ids


def require_raw_evidence(session, scope: CanonicalScope, raw_ids: set[str]) -> None:
    if scope.unrestricted:
        return
    for version in session.scalars(select(SourceVersion).where(SourceVersion.raw_record_id.in_(raw_ids))):
        source = session.get(EnterpriseSource, version.source_id)
        if source is None:
            raise HTTPException(403, "Original evidence source cannot be authorized")
        authorize_source(session, scope.actor, source, equipment_alias=version.equipment_alias,
                         collection=version.collection, at=version.effective_at)


def require_exposure_evidence(session, scope: CanonicalScope, component_id: str, exposure=None) -> None:
    """Calculation ancestry remains subject to the original evidence grants."""
    if scope.unrestricted:
        return
    version_ids = set()
    for lineage in session.scalars(select(CalculationLineage).where(CalculationLineage.component_id == component_id)):
        version_ids.update(lineage.source_version_ids)
    for version_id in version_ids:
        version = session.get(SourceVersion, version_id)
        if version is None:
            raise HTTPException(403, "Calculation ancestry cannot be authorized")
        require_raw_evidence(session, scope, {version.raw_record_id})
    # Read projections can include newly calculated windows before a persisted
    # lineage exists. Authorize those rule sources as well as persisted ancestry.
    if exposure is None:
        exposure = views.exposure_for(session, session.get(ComponentInstance, component_id))
    for entry in exposure.get("rules", []):
        rule = session.get(ExposureDefinition, entry["id"])
        source = session.get(EnterpriseSource, rule.source_id) if rule else None
        if source is None:
            raise HTTPException(403, "Exposure rule source cannot be authorized")
        at = datetime.fromisoformat(entry["start"].replace("Z", "+00:00")) if entry.get("start") else rule.effective_from
        authorize_source(session, scope.actor, source, collection="telemetry", at=at)


def _permitted_component(session, scope: CanonicalScope, component_id: str) -> bool:
    try:
        scope.require_component(session, component_id)
        return True
    except HTTPException as exc:
        if exc.status_code in {403, 404}:
            return False
        raise


def _permitted_failure(session, scope: CanonicalScope, failure_id: str) -> bool:
    try:
        scope.require_failure(session, failure_id)
        return True
    except HTTPException as exc:
        if exc.status_code in {403, 404}:
            return False
        raise


def scoped_inventory(session, scope: CanonicalScope, chamber_id=None, at=AS_OF, q=None, status=None) -> list[dict[str, Any]]:
    if chamber_id:
        scope.require_chamber(session, chamber_id)
    items = []
    for installation in session.scalars(select(Installation).where(
        Installation.installed_at <= at,
        (Installation.removed_at.is_(None)) | (Installation.removed_at > at),
    )):
        if not _permitted_component(session, scope, installation.component_id):
            continue
        location = views.location(session, installation)
        if location[4].id not in scope.tool_ids or (chamber_id and location[3].id != chamber_id):
            continue
        item = views.component_summary(session, session.get(ComponentInstance, installation.component_id), at, installation)
        if status and item["pm"]["status"] != status and item["status"] != status:
            continue
        if q and q.casefold() not in " ".join(str(item.get(key, "")) for key in (
            "name", "part_number", "serial_number", "revision", "subsystem", "assembly", "position", "tool_name", "chamber_name"
        )).casefold():
            continue
        if not scope.unrestricted:
            restricted_installation = False
            try:
                require_raw_evidence(session, scope, {installation.source_record_id})
            except HTTPException as exc:
                if exc.status_code != 403:
                    raise
                restricted_installation = True
                item["provenance"].update(source="restricted evidence", source_system="restricted evidence", original_source_id="restricted", quality="restricted")
            restricted_exposure = False
            try:
                require_exposure_evidence(session, scope, installation.component_id, item["exposure"])
            except HTTPException as exc:
                if exc.status_code != 403:
                    raise
                restricted_exposure = True
            if restricted_installation or restricted_exposure:
                allowed_fields = {"dimension", "unit", "hours", "value", "lifetime_hours", "since_refurbishment", "completeness", "confidence", "lifetime_completeness", "lifetime_confidence", "observed_window_hours", "calendar_days", "snapshot_at", "attribution_status"}
                item["exposure"] = {key: value for key, value in item["exposure"].items() if key in allowed_fields}
                item["exposure"].update(source="restricted evidence", measurement_source="Approved canonical exposure; original evidence restricted", issues=["Detailed exposure evidence and calculation lineage require source-specific permission."])
                item["data_quality"]["issues"] = item["exposure"]["issues"]
                item["evidence_access"] = "Restricted; approved canonical fields only"
        items.append(item)
    return items


def scoped_hierarchy(session, scope: CanonicalScope) -> dict[str, Any]:
    result = views.hierarchy(session)
    for site in result["sites"]:
        site["tools"] = [tool for tool in site["tools"] if tool["id"] in scope.tool_ids]
    result["sites"] = [site for site in result["sites"] if site["tools"]]
    return result


def scoped_component_detail(session, scope: CanonicalScope, component_id: str):
    return views.component_detail(session, scope.require_component(session, component_id, evidence=True))


def scoped_failure_detail(session, scope: CanonicalScope, failure_id: str):
    return views.failure_detail(session, scope.require_failure(session, failure_id, evidence=True))


def scoped_failures(session, scope: CanonicalScope):
    episodes = [failure for failure in session.scalars(select(FailureEpisode).order_by(FailureEpisode.started_at.desc()))
                if _permitted_failure(session, scope, failure.id)]
    chamber_ids = set(session.scalars(select(Chamber.id).where(Chamber.tool_id.in_(scope.tool_ids))))
    return {"items": [views.failure_summary(session, episode) for episode in episodes],
            "alarm_only_events": session.query(EquipmentEvent).filter(EquipmentEvent.failure_id.is_(None), EquipmentEvent.chamber_id.in_(chamber_ids)).count(),
            "synthetic": True}


def require_conflict(session, scope: CanonicalScope, conflict_id: str) -> SourceConflict:
    conflict = session.get(SourceConflict, conflict_id)
    if conflict is None:
        raise HTTPException(404, "Source conflict not found")
    if scope.unrestricted:
        return conflict
    anchored = False
    if conflict.component_id:
        scope.require_component(session, conflict.component_id)
        anchored = True
    for encoded in (conflict.value_a, conflict.value_b):
        try:
            decoded = json.loads(encoded)
        except (TypeError, ValueError):
            decoded = encoded
        value = decoded if isinstance(decoded, str) else encoded
        if session.get(ComponentInstance, value) is not None:
            scope.require_component(session, value)
            anchored = True
    for raw_id in (conflict.record_a_id, conflict.record_b_id):
        versions = list(session.scalars(select(SourceVersion).where(SourceVersion.raw_record_id == raw_id)))
        if versions:
            require_raw_evidence(session, scope, {raw_id})
            anchored = True
        record = session.get(RawSourceRecord, raw_id)
        payload = record.payload if record else {}
        for key in ("component_id", "installed_component", "old_component_id", "new_component_id"):
            candidate = payload.get(key)
            if isinstance(candidate, str) and session.get(ComponentInstance, candidate) is not None:
                scope.require_component(session, candidate)
                anchored = True
        if payload.get("position_id"):
            position = session.get(Position, str(payload["position_id"]))
            if position is not None:
                assembly = session.get(Assembly, position.assembly_id)
                subsystem = session.get(Subsystem, assembly.subsystem_id)
                scope.require_chamber(session, subsystem.chamber_id)
                anchored = True
        if payload.get("chamber_id"):
            if session.get(Chamber, str(payload["chamber_id"])) is not None:
                scope.require_chamber(session, str(payload["chamber_id"]))
                anchored = True
            elif not versions:
                raise HTTPException(403, "Unresolved source chamber cannot establish an authorized evidence scope")
        for key in ("tool_id", "equipment_id"):
            tool = session.get(Tool, str(payload.get(key, "")))
            if tool is None:
                tool = session.scalar(select(Tool).where(Tool.name == str(payload.get(key, ""))))
            if tool is not None:
                scope.require_tool(tool.id)
                anchored = True
            elif payload.get(key) and not versions:
                raise HTTPException(403, "Unresolved source equipment cannot establish an authorized evidence scope")
    if not anchored:
        raise HTTPException(403, "Unresolved source identity has no authorized canonical equipment anchor")
    return conflict


def scoped_quality(session, scope: CanonicalScope, payload: dict[str, Any]):
    if scope.unrestricted:
        return payload
    items = []
    for item in payload.get("items", []):
        try:
            require_conflict(session, scope, item["id"])
        except HTTPException as exc:
            if exc.status_code in {403, 404}:
                continue
            raise
        items.append(item)
    chamber_ids = set(session.scalars(select(Chamber.id).where(Chamber.tool_id.in_(scope.tool_ids))))
    result = dict(payload)
    result["items"] = items
    result["issues"] = [issue for issue in payload.get("issues", []) if issue.get("chamber_id") in chamber_ids or issue.get("code") == "unknown_oem_limits"]
    return result


def scoped_pm(session, scope: CanonicalScope, status=None):
    items = scoped_inventory(session, scope, status=status)
    safe_ids = {component.id for component in session.scalars(select(ComponentInstance)) if _permitted_component(session, scope, component.id)}
    due = list(session.scalars(select(PMDueEvent).where(PMDueEvent.component_id.in_(safe_ids))))
    return {"items": items, "compliance": {"completed": sum(event.status == "completed" for event in due), "recorded_due_events": len(due)},
            "synthetic": True, "policy_note": "Engineer-entered demonstration intervals; not OEM limits, site-approved policy, or reliability estimates"}


def scoped_analytics(session, scope: CanonicalScope):
    component_ids = {component.id for component in session.scalars(select(ComponentInstance)) if _permitted_component(session, scope, component.id)}
    return views.analytics(session, component_ids=component_ids, tool_ids=scope.tool_ids)


def scoped_fleet(session, scope: CanonicalScope, quality_payload: dict[str, Any]):
    items = scoped_inventory(session, scope)
    failures = scoped_failures(session, scope)["items"]
    episodes = [session.get(FailureEpisode, failure["id"]) for failure in failures]
    down = views.downtime_summary([row for row in views.down_records(session) if row["tool_id"] in scope.tool_ids])
    tree = scoped_hierarchy(session, scope)
    completeness = [item["exposure"]["completeness"] for item in items if item["exposure"]["completeness"] is not None]
    visible_quality = scoped_quality(session, scope, quality_payload)
    return {"metrics": {"tools": len(scope.tool_ids), "chambers": session.query(Chamber).filter(Chamber.tool_id.in_(scope.tool_ids)).count(),
                        "installed_components": len(items), "pm_due": sum(item["pm"]["status"] in {"upcoming", "overdue"} for item in items),
                        "open_investigations": sum(episode.review_status == "awaiting_engineering_review" for episode in episodes), "downtime_hours": down["total_hours"]},
            "tools": [tool for site in tree["sites"] for tool in site["tools"]], "downtime_by_subsystem": down["downtime_by_subsystem"], "recent_failures": failures,
            "data_quality": {"completeness": sum(completeness) / len(completeness) if completeness else None,
                             "issues": sum(item["status"] in {"unresolved", "decision_recorded_pending_materialization"} for item in visible_quality.get("items", [])) + sum(issue.get("code") == "coverage_gap" for issue in visible_quality.get("issues", [])),
                             "last_sync": views.iso(AS_OF)}, "as_of": views.iso(AS_OF), "synthetic": True}


def require_canonical_export(scope: CanonicalScope) -> None:
    if scope.mode != "synthetic" and scope.actor.role != "admin" and not scope.actor.export_allowed:
        raise HTTPException(403, "Explicit canonical export permission is required")
