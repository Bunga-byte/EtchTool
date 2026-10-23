"""Read models assembled from relational engineering facts and pure services."""

from datetime import datetime, timezone
from sqlalchemy import select
from .models import *
from .seed import AS_OF
from .services.exposure import calculate_exposure, component_exposure, union_hours
from .services.pm import evaluate_pm
from .services.failure import downtime_summary
from .services.reliability import (
    poisson_rate,
    kaplan_meier,
    weibull_fit,
    revision_rates,
)


def rows(session, model):
    return session.scalars(select(model)).all()


def iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def provenance(record):
    return {
        "source": record.source,
        "source_system": record.source,
        "original_source_id": record.source_id,
        "recorded_at": iso(record.recorded_at),
        "effective_at": iso(record.effective_at),
        "last_sync": iso(record.ingested_at),
        "quality": record.quality,
        "verification_status": record.verification,
        "synthetic": True,
    }


def location(session, install):
    position = session.get(Position, install.position_id)
    assembly = session.get(Assembly, position.assembly_id)
    sub = session.get(Subsystem, assembly.subsystem_id)
    chamber = session.get(Chamber, sub.chamber_id)
    tool = session.get(Tool, chamber.tool_id)
    return position, assembly, sub, chamber, tool


def history(session, component):
    return session.scalars(
        select(Installation)
        .where(Installation.component_id == component.id)
        .order_by(Installation.installed_at)
    ).all()


def exposure_for(session, component, at=AS_OF, until_first_failure=False):
    definition = session.get(ComponentDefinition, component.definition_id)
    installs = history(session, component)
    all_intervals = []
    coverage = []
    hist = []
    sources = set()
    for install in installs:
        pos, ass, sub, ch, tool = location(session, install)
        sources.add(pos.exposure_source)
        hist.append(
            {
                "id": install.id,
                "installed_at": install.installed_at,
                "removed_at": install.removed_at,
                "chamber_id": ch.id,
            }
        )
        for r in session.scalars(
            select(ExposureInterval).where(
                ExposureInterval.chamber_id == ch.id,
                ExposureInterval.dimension == definition.exposure_dimension,
                ExposureInterval.source == pos.exposure_source,
            )
        ):
            obj = {
                "id": r.id,
                "source_record_id": r.source_record_id,
                "start": r.start,
                "end": r.end,
                "dimension": r.dimension,
                "source": r.source,
                "quality": r.quality,
                "chamber_id": r.chamber_id,
            }
            if r.value is not None:
                obj["value"] = r.value
            all_intervals.append(obj)
        for r in session.scalars(
            select(ObservationCoverage).where(
                ObservationCoverage.chamber_id == ch.id,
                ObservationCoverage.source == pos.exposure_source,
            )
        ):
            coverage.append(
                {
                    "id": r.id,
                    "start": r.start,
                    "end": r.end,
                    "source": r.source,
                    "chamber_id": r.chamber_id,
                }
            )
    if len(sources) > 1:
        return {
            "dimension": definition.exposure_dimension,
            "unit": "unknown",
            "hours": None,
            "lifetime_hours": None,
            "since_refurbishment": None,
            "completeness": None,
            "confidence": "unknown",
            "source": "multiple incompatible source assignments",
            "issues": ["Reconcile exposure source before lifetime aggregation"],
            "derivation": [],
        }
    refurb = session.scalar(
        select(Refurbishment)
        .where(
            Refurbishment.component_id == component.id,
            Refurbishment.qualified.is_(True),
            Refurbishment.completed_at <= at,
        )
        .order_by(Refurbishment.completed_at.desc())
    )
    if until_first_failure:
        first = session.scalar(
            select(FailureEpisode)
            .where(
                FailureEpisode.component_id == component.id,
                FailureEpisode.status == "confirmed",
                FailureEpisode.attribution_status == "confirmed",
            )
            .order_by(FailureEpisode.started_at)
        )
        if first:
            at = min(at, first.started_at)
    from .enterprise.telemetry import project_component_exposure

    projection = project_component_exposure(
        session, component, hist, at, all_intervals, coverage
    )
    all_intervals = projection["intervals"]
    coverage = projection["coverage"]
    result = component_exposure(
        all_intervals,
        hist,
        as_of=at,
        dimension=definition.exposure_dimension,
        source=next(iter(sources), "unknown"),
        coverage_intervals=coverage,
        refurbished_at=refurb.completed_at
        if refurb and refurb.completed_at <= at
        else None,
    )
    result["lineage_ids"] = projection.get("lineage_ids", [])
    result["exposure_rules"] = projection.get("rules", [])
    if projection.get("issues"):
        result["issues"] = list(dict.fromkeys(result["issues"] + projection["issues"]))
        result["confidence"] = "limited"
        result["lifetime_confidence"] = "limited"
    result["snapshot_at"] = iso(at)
    result["measurement_source"] = "Synthetic equipment-state records"
    conflicts = [
        c
        for c in rows(session, SourceConflict)
        if c.status in {"unresolved", "decision_recorded_pending_materialization"}
        and c.field == "installed_component"
        and component.id in {c.component_id, c.value_a, c.value_b}
        and max(
            session.get(RawSourceRecord, c.record_a_id).effective_at,
            session.get(RawSourceRecord, c.record_b_id).effective_at,
        )
        <= at
    ]
    result["attribution_status"] = "disputed" if conflicts else "documented_synthetic"
    if conflicts:
        result["issues"].append(
            "Serialized installation identity disputed by source records; exposure attribution is provisional pending reconciliation"
        )
        result["confidence"] = "limited"
        result["lifetime_confidence"] = "limited"
    return result


def component_summary(session, component, at=AS_OF, installation=None):
    definition = session.get(ComponentDefinition, component.definition_id)
    hist = history(session, component)
    eligible = [i for i in hist if i.installed_at <= at]
    install = installation or (eligible[-1] if eligible else None)
    if install is None:
        return None
    pos, ass, sub, ch, tool = location(session, install)
    exposure = exposure_for(session, component, at)
    policy = session.scalar(
        select(PMPlan)
        .where(
            PMPlan.definition_id == definition.id,
            PMPlan.effective_from <= at,
            (PMPlan.effective_to.is_(None)) | (PMPlan.effective_to > at),
        )
        .order_by(PMPlan.effective_from.desc())
    )
    pm = evaluate_pm(
        exposure,
        {
            "threshold": policy.threshold,
            "calendar_days": policy.calendar_days,
            "dimension": policy.dimension,
            "unit": policy.unit,
            "basis": policy.basis,
            "source": policy.source_document,
            "document_reference": policy.source_document,
            "verification_status": policy.verification,
        }
        if policy
        else None,
    )
    installed = install.removed_at is None or install.removed_at > at
    return {
        "id": component.id,
        "name": definition.name,
        "part_number": definition.part_number,
        "serial_number": component.serial_number,
        "revision": component.revision,
        "status": "installed" if installed else component.disposition,
        "subsystem": sub.name,
        "assembly": ass.name,
        "position": pos.name,
        "position_id": pos.id,
        "installation_id": install.id,
        "chamber_id": ch.id,
        "chamber_name": ch.name,
        "tool_id": tool.id,
        "tool_name": tool.name,
        "installed_at": iso(install.installed_at),
        "removed_at": iso(install.removed_at),
        "exposure": exposure,
        "pm": pm,
        "provenance": {
            **provenance(session.get(RawSourceRecord, install.source_record_id)),
            "quality": "disputed"
            if exposure.get("attribution_status") == "disputed"
            else "complete",
        },
        "data_quality": {
            "attribution_status": exposure.get("attribution_status"),
            "issues": exposure.get("issues", []),
        },
        "synthetic": True,
    }


def inventory(session, chamber_id=None, at=AS_OF, q=None, status=None):
    result = []
    for install in session.scalars(
        select(Installation).where(
            Installation.installed_at <= at,
            (Installation.removed_at.is_(None)) | (Installation.removed_at > at),
        )
    ):
        component = session.get(ComponentInstance, install.component_id)
        item = component_summary(session, component, at, install)
        if chamber_id and item["chamber_id"] != chamber_id:
            continue
        if status and item["pm"]["status"] != status and item["status"] != status:
            continue
        if (
            q
            and q.lower()
            not in " ".join(
                str(item.get(k, ""))
                for k in [
                    "name",
                    "part_number",
                    "serial_number",
                    "revision",
                    "subsystem",
                    "assembly",
                    "position",
                    "tool_name",
                    "chamber_name",
                ]
            ).lower()
        ):
            continue
        result.append(item)
    return result


def hierarchy(session):
    sites = []
    for site in rows(session, Site):
        tools = []
        for tool in session.scalars(select(Tool).where(Tool.site_id == site.id)):
            config = session.get(EquipmentConfiguration, tool.configuration_id)
            tools.append(
                {
                    "id": tool.id,
                    "name": tool.name,
                    "variant": config.variant,
                    "status": tool.status,
                    "phase": tool.phase,
                    "chambers": [
                        {"id": c.id, "name": c.name, "status": c.status}
                        for c in session.scalars(
                            select(Chamber).where(Chamber.tool_id == tool.id)
                        )
                    ],
                }
            )
        sites.append({"id": site.id, "name": site.name, "tools": tools})
    return {"sites": sites, "synthetic": True, "as_of": iso(AS_OF)}


def down_records(session, failure_id=None):
    result = []
    for d in rows(session, DowntimeInterval):
        if failure_id and d.failure_id != failure_id:
            continue
        chamber = session.get(Chamber, d.chamber_id)
        attrs = session.scalars(
            select(DowntimeAttribution).where(DowntimeAttribution.downtime_id == d.id)
        ).all()
        if not attrs:
            attrs = [None]
        for a in attrs:
            component = session.get(ComponentInstance, a.component_id) if a else None
            sub = (
                session.get(ComponentDefinition, component.definition_id).category
                if component
                else "Unattributed"
            )
            result.append(
                {
                    "id": d.id + ("-" + a.id if a else ""),
                    "start": d.start,
                    "end": d.end,
                    "tool_id": chamber.tool_id,
                    "chamber_id": chamber.id,
                    "component_id": a.component_id if a else None,
                    "subsystem": sub,
                    "category": d.category,
                    "weight": a.weight if a else 0,
                    "attribution_status": a.status if a else "unknown",
                }
            )
    return result


def failure_summary(session, episode):
    component = (
        session.get(ComponentInstance, episode.component_id)
        if episode.component_id
        else None
    )
    definition = (
        session.get(ComponentDefinition, component.definition_id) if component else None
    )
    chamber = session.get(Chamber, episode.chamber_id)
    tool = session.get(Tool, chamber.tool_id)
    mode = (
        session.get(FailureMode, episode.failure_mode_id)
        if episode.failure_mode_id
        else None
    )
    downtime = downtime_summary(down_records(session, episode.id))
    return {
        "id": episode.id,
        "title": episode.title,
        "component_id": episode.component_id,
        "component_name": definition.name if definition else "Unknown",
        "tool_name": tool.name,
        "chamber_name": chamber.name,
        "started_at": iso(episode.started_at),
        "ended_at": iso(episode.ended_at),
        "status": episode.status,
        "mode": mode.name if mode else "Unknown",
        "downtime_hours": downtime["total_hours"],
        "attribution_status": episode.attribution_status,
        "serial_number": component.serial_number if component else None,
        "synthetic": True,
    }


def fdc_records(session, component_id):
    points = session.scalars(
        select(FDCPoint)
        .where(FDCPoint.component_id == component_id)
        .order_by(FDCPoint.timestamp)
    ).all()
    baselines = {
        cohort: min(p.timestamp for p in points if p.cohort == cohort)
        for cohort in {p.cohort for p in points}
    }
    return [
        {
            "id": p.id,
            "timestamp": iso(p.timestamp),
            "signal": p.signal,
            "value": p.value,
            "unit": p.unit,
            "state": p.state,
            "cohort": p.cohort,
            "alignment_minutes": int(
                (p.timestamp - baselines[p.cohort]).total_seconds() / 60
            ),
            "source": "synthetic_fdc",
            "provenance": provenance(session.get(RawSourceRecord, p.source_record_id)),
        }
        for p in points
    ]


def failure_detail(session, episode):
    result = failure_summary(session, episode)
    evidence = [
        {
            "id": e.id,
            "timestamp": iso(e.timestamp),
            "kind": e.kind,
            "description": e.description,
            "quality": e.quality,
            "provenance": provenance(session.get(RawSourceRecord, e.source_record_id)),
        }
        for e in session.scalars(
            select(Evidence).where(Evidence.failure_id == episode.id)
        )
    ]
    alarms = [
        {
            "id": e.id,
            "timestamp": iso(e.asserted_at),
            "asserted_at": iso(e.asserted_at),
            "cleared_at": iso(e.cleared_at),
            "label": e.label,
            "code": e.synthetic_code,
            "symptom_role": e.symptom_role,
            "provenance": provenance(session.get(RawSourceRecord, e.source_record_id)),
        }
        for e in session.scalars(
            select(EquipmentEvent).where(EquipmentEvent.failure_id == episode.id)
        )
    ]
    actions = [
        {
            "id": a.id,
            "proposal": a.proposal,
            "validation_status": a.validation_status,
            "owner": a.owner,
        }
        for a in session.scalars(
            select(CorrectiveAction).where(CorrectiveAction.failure_id == episode.id)
        )
    ]
    result.update(
        {
            "chronology": sorted(
                [
                    {
                        "timestamp": a["timestamp"],
                        "event": a["label"],
                        "source": "synthetic_alarms",
                    }
                    for a in alarms
                ]
                + [
                    {
                        "timestamp": e["timestamp"],
                        "event": e["description"],
                        "source": "synthetic_maintenance",
                    }
                    for e in evidence
                ],
                key=lambda e: e["timestamp"],
            ),
            "evidence": evidence,
            "hypotheses": episode.hypotheses,
            "corrective_action": actions,
            "alarms": alarms,
            "fdc": fdc_records(session, episode.component_id),
            "review_status": episode.review_status,
            "root_cause": episode.root_cause,
            "downtime": downtime_summary(down_records(session, episode.id)),
            "limitations": [
                "Alarms and replacement records do not independently prove component failure",
                "Synthetic evidence only; not a demonstrated physical root cause on real equipment",
            ],
        }
    )
    return result


def analytics(session, *, component_ids=None, tool_ids=None):
    rf = [
        c
        for c in rows(session, ComponentInstance)
        if (component_ids is None or c.id in component_ids)
        and session.get(ComponentDefinition, c.definition_id).exposure_dimension
        == "rf_hours"
    ]
    cohort = []
    observations = []
    excluded = []
    for c in rf:
        exposure = exposure_for(session, c)
        definition = session.get(ComponentDefinition, c.definition_id)
        failures = session.scalars(
            select(FailureEpisode).where(
                FailureEpisode.component_id == c.id,
                FailureEpisode.status == "confirmed",
                FailureEpisode.attribution_status == "confirmed",
                FailureEpisode.started_at <= AS_OF,
            )
        ).all()
        rate_eligible = (
            exposure.get("lifetime_completeness", exposure.get("completeness")) == 1
            and exposure.get("lifetime_confidence", exposure.get("confidence"))
            == "complete"
            and exposure.get("lifetime_hours") is not None
        )
        if rate_eligible:
            cohort.append(
                {
                    "part_number": definition.part_number,
                    "revision": c.revision,
                    "exposure_hours": exposure["lifetime_hours"],
                    "failures": len(failures),
                }
            )
        else:
            excluded.append(
                {
                    "component_id": c.id,
                    "analysis": "rate",
                    "reason": "Incomplete monitoring or disputed identity; exclude numerator and denominator together",
                    "completeness": exposure.get(
                        "lifetime_completeness", exposure.get("completeness")
                    ),
                }
            )
        life = exposure_for(session, c, until_first_failure=True)
        if (
            life.get("lifetime_completeness", life.get("completeness")) == 1
            and life.get("lifetime_confidence", life.get("confidence")) == "complete"
        ):
            observations.append(
                {
                    "time": life["lifetime_hours"],
                    "event": bool(failures),
                    "component_id": c.id,
                }
            )
        else:
            excluded.append(
                {
                    "component_id": c.id,
                    "analysis": "survival",
                    "reason": "No complete verified first-life observation through event or censor time",
                }
            )
    total = sum(c["exposure_hours"] for c in cohort)
    failures = sum(c["failures"] for c in cohort)
    down_rows = [
        row
        for row in down_records(session)
        if tool_ids is None or row["tool_id"] in tool_ids
    ]
    if component_ids is not None:
        down_rows = [
            {
                **row,
                "component_id": None,
                "weight": 0,
                "subsystem": "Unattributed",
                "attribution_status": "restricted",
            }
            if row.get("component_id") not in component_ids
            else row
            for row in down_rows
        ]
    down = downtime_summary(down_rows)
    return {
        "rate": poisson_rate(failures, total) if total else None,
        "survival": kaplan_meier(observations),
        "revision_comparison": revision_rates(cohort),
        "downtime_by_subsystem": down["downtime_by_subsystem"],
        "downtime": down,
        "weibull": weibull_fit(observations),
        "forecast_policy": {
            "state": "A",
            "message": "Insufficient evidence for reliable failure prediction.",
            "synthetic": True,
            "validated_model": False,
        },
        "observations": observations,
        "excluded_components": excluded,
        "eligible_rate_components": len(cohort),
        "cohort": "Synthetic RF matching modules only; RF sources and powered-hour components are not combined",
        "limitations": [
            "Synthetic descriptive calculations only",
            "Incomplete or disputed lifetimes excluded from rates and survival estimates",
            "Small revision cohorts are not controlled hardware comparisons",
            "Right censoring assumed independent; competing risks and recurrent repair cycles need separate models",
        ],
        "as_of": iso(AS_OF),
        "synthetic": True,
    }


def component_detail(session, component):
    result = component_summary(session, component)
    definition = session.get(ComponentDefinition, component.definition_id)
    specs = [
        {
            "id": s.id,
            "parameter": s.parameter,
            "unit": s.unit,
            "nominal": s.nominal,
            "minimum": s.minimum,
            "maximum": s.maximum,
            "part_revision": s.part_revision,
            "configuration_id": s.configuration_id,
            "source_document": s.source_document,
            "document_revision": s.document_revision,
            "effective_from": iso(s.effective_from),
            "verification_status": s.verification,
        }
        for s in session.scalars(
            select(Specification).where(Specification.definition_id == definition.id)
        )
    ]
    installs = []

    def removal_provenance(installation):
        if installation.removed_at:
            removal = session.scalar(
                select(MaintenanceAction).where(
                    MaintenanceAction.component_id == installation.component_id,
                    MaintenanceAction.timestamp == installation.removed_at,
                    MaintenanceAction.action == "Reviewed removal",
                )
            )
            if removal:
                order = session.get(WorkOrder, removal.work_order_id)
                return provenance(session.get(RawSourceRecord, order.source_record_id))
        event = session.scalar(
            select(AuditLog)
            .where(AuditLog.entity_id == installation.id, AuditLog.action == "remove")
            .order_by(AuditLog.timestamp.desc())
        )
        if event and event.detail.get("raw_record_id"):
            record = session.get(RawSourceRecord, event.detail["raw_record_id"])
            if record:
                return provenance(record)
        return (
            provenance(session.get(RawSourceRecord, installation.source_record_id))
            if installation.removed_at
            else None
        )

    for i in history(session, component):
        pos, ass, sub, ch, tool = location(session, i)
        installs.append(
            {
                "id": i.id,
                "component_id": component.id,
                "tool_name": tool.name,
                "chamber_name": ch.name,
                "position": pos.name,
                "installed_at": iso(i.installed_at),
                "removed_at": iso(i.removed_at),
                "reason": i.reason,
                "removal_reason": i.removal_reason,
                "maintenance_reference": i.maintenance_reference,
                "removal_provenance": removal_provenance(i),
                "provenance": provenance(
                    session.get(RawSourceRecord, i.source_record_id)
                ),
            }
        )
    maintenance = []
    for m in session.scalars(
        select(MaintenanceAction)
        .where(MaintenanceAction.component_id == component.id)
        .order_by(MaintenanceAction.timestamp)
    ):
        wo = session.get(WorkOrder, m.work_order_id)
        maintenance.append(
            {
                "id": m.id,
                "timestamp": iso(m.timestamp),
                "action": m.action,
                "findings": m.findings,
                "confirmed_failure": m.confirmed_failure,
                "work_order_id": wo.id,
                "kind": wo.kind,
                "provenance": provenance(
                    session.get(RawSourceRecord, wo.source_record_id)
                ),
            }
        )
    replacements = []
    for r in rows(session, ReplacementEvent):
        if component.id in {r.old_component_id, r.new_component_id}:
            replacements.append(
                {
                    "id": r.id,
                    "timestamp": iso(r.timestamp),
                    "old_component_id": r.old_component_id,
                    "new_component_id": r.new_component_id,
                    "old_serial_number": session.get(
                        ComponentInstance, r.old_component_id
                    ).serial_number,
                    "new_serial_number": session.get(
                        ComponentInstance, r.new_component_id
                    ).serial_number,
                    "reason": r.reason,
                    "work_order_id": r.work_order_id,
                }
            )
    forecast = {
        "state": "A",
        "label": "Rules-based demonstration PM",
        "eligible": False,
        "message": "Insufficient evidence for reliable failure prediction.",
        "model_version": None,
        "horizons": [],
        "limitations": [
            "No validated predictive health model",
            "Synthetic fixture does not establish a real failure probability",
        ],
        "synthetic": True,
    }
    try:
        from .services.forecast import component_forecast

        forecast = component_forecast(result["exposure"], result["pm"], synthetic=True)
    except ImportError:
        pass
    result.update(
        {
            "definition": {
                "id": definition.id,
                "manufacturer": definition.manufacturer,
                "function": definition.function,
                "category": definition.category,
                "compatible_configurations": ["DEMO-FLEX (synthetic only)"],
                "failure_mechanisms": definition.failure_mechanisms,
            },
            "identity": {
                "lot": component.lot,
                "supplier": component.supplier,
                "repair_cycle": component.repair_cycle,
                "refurbishment_status": component.refurbishment_status,
                "traceability_status": component.traceability_status,
            },
            "specifications": specs,
            "installations": installs,
            "maintenance": maintenance,
            "replacements": replacements,
            "failures": [
                failure_summary(session, f)
                for f in session.scalars(
                    select(FailureEpisode).where(
                        FailureEpisode.component_id == component.id
                    )
                )
            ],
            "forecast": forecast,
            "fdc": fdc_records(session, component.id),
            "source_documents": [s["source_document"] for s in specs],
        }
    )
    return result
