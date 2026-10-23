"""Deterministic synthetic fixture. No actual equipment identifiers or OEM limits."""

from datetime import datetime, timedelta, timezone
import hashlib, json, math
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import *
from .db import make_engine, migrate
from .config import settings

AS_OF = datetime(2026, 1, 31, tzinfo=timezone.utc)
START = datetime(2025, 12, 1, tzinfo=timezone.utc)


def raw(session, id, source, payload, at=START):
    session.add(
        RawSourceRecord(
            id=id,
            source=source,
            source_id="SYN-" + id,
            recorded_at=at,
            effective_at=at,
            ingested_at=AS_OF,
            payload={"synthetic": True, **payload},
            fingerprint=hashlib.sha256(
                (id + json.dumps(payload, sort_keys=True)).encode()
            ).hexdigest(),
            quality="complete",
            verification="synthetic_only",
        )
    )
    session.flush()
    return id


def seed(session: Session):
    if session.get(Site, "site-demo"):
        return False
    session.add(Site(id="site-demo", name="Synthetic Engineering Fab", synthetic=True))
    session.flush()
    session.add(
        EquipmentConfiguration(
            id="cfg-demo",
            family="Flex-family (fictional configuration)",
            variant="DEMO-FLEX",
            revision="SYN-1",
            description="Conceptual configuration only; not an OEM hardware specification",
        )
    )
    session.flush()
    defs = [
        (
            "rf-a",
            "SYN-RF-100-A",
            "RF matching module",
            "RF delivery",
            "Transform impedance within the synthetic RF path",
            "A",
            "rf_hours",
        ),
        (
            "rf-b",
            "SYN-RF-100-B",
            "RF matching module",
            "RF delivery",
            "Transform impedance within the synthetic RF path",
            "B",
            "rf_hours",
        ),
        (
            "valve",
            "SYN-VLV-200",
            "Isolation valve assembly",
            "Vacuum and gas",
            "Isolate a conceptual vacuum line",
            "A",
            "powered_hours",
        ),
        (
            "sensor",
            "SYN-THM-300",
            "Thermal sensing module",
            "Thermal management",
            "Observe conceptual cooling circuit",
            "A",
            "powered_hours",
        ),
    ]
    for id, pn, name, category, function, rev, dim in defs:
        session.add(
            ComponentDefinition(
                id=id,
                manufacturer="Fictional Demonstration Supplier",
                part_number=pn,
                name=name,
                category=category,
                function=function,
                revision=rev,
                exposure_dimension=dim,
                failure_mechanisms=["Synthetic contact degradation"]
                if id.startswith("rf")
                else ["Unknown; pending physical evidence"],
                supersedes_id=None,
            )
        )
    session.flush()
    for id, *_ in defs:
        session.add(
            Compatibility(
                id="compat-" + id,
                definition_id=id,
                configuration_id="cfg-demo",
                effective_from=START,
                verification="synthetic_only",
            )
        )
        session.add(
            Specification(
                id="spec-" + id,
                definition_id=id,
                parameter="OEM operating limits",
                unit=None,
                nominal=None,
                minimum=None,
                maximum=None,
                part_revision="B" if id == "rf-b" else "A",
                configuration_id="cfg-demo",
                source_document="OEM documentation not supplied",
                document_revision="Unknown",
                effective_from=START,
                verification="pending_verification",
            )
        )
        session.add(
            PMPlan(
                id="plan-" + id,
                definition_id=id,
                dimension="rf_hours" if id.startswith("rf") else "powered_hours",
                threshold=900
                if id == "rf-b"
                else 650
                if id == "rf-a"
                else 1400
                if id == "valve"
                else 1600,
                calendar_days=None,
                unit="RF h" if id.startswith("rf") else "powered h",
                basis="synthetic_engineer_recommendation",
                source_document="SYN-PM-POLICY-001 — demonstration only, not OEM or site approved",
                effective_from=START,
                verification="synthetic_only",
            )
        )
    session.flush()
    for t in range(1, 4):
        tool_id = f"tool-{t}"
        session.add(
            Tool(
                id=tool_id,
                site_id="site-demo",
                configuration_id="cfg-demo",
                name=f"SYN-FLEX-{t:02d}",
                status="qualification"
                if t == 2
                else "available"
                if t == 3
                else "engineering",
                phase="commissioning" if t == 1 else "qualification",
            )
        )
        session.flush()
        for c in ["A", "B"]:
            chamber = f"ch-{t}-{c.lower()}"
            session.add(
                Chamber(
                    id=chamber,
                    tool_id=tool_id,
                    name=f"Chamber {c}",
                    status="investigation" if (t, c) == (1, "A") else "available",
                )
            )
            session.flush()
            for typ, subname, assembly_name in [
                ("rf", "RF delivery", "Matching network"),
                ("valve", "Vacuum and gas", "Isolation assembly"),
                ("sensor", "Thermal management", "Sensing assembly"),
            ]:
                sub = f"sub-{chamber}-{typ}"
                ass = f"ass-{chamber}-{typ}"
                pos = f"pos-{chamber}-{typ}"
                session.add(Subsystem(id=sub, chamber_id=chamber, name=subname))
                session.flush()
                session.add(Assembly(id=ass, subsystem_id=sub, name=assembly_name))
                session.flush()
                session.add(
                    Position(
                        id=pos,
                        assembly_id=ass,
                        name="Primary " + typ + " slot",
                        exposure_source="rf_primary" if typ == "rf" else "powered",
                    )
                )
                session.flush()
                definition = (
                    "rf-b" if typ == "rf" and t > 1 else "rf-a" if typ == "rf" else typ
                )
                cid = f"cmp-{t}-{c.lower()}-{typ}"
                session.add(
                    ComponentInstance(
                        id=cid,
                        definition_id=definition,
                        serial_number=f"SYN-{t:02d}{c}-{typ.upper()}-002"
                        if (t, c, typ) == (1, "A", "rf")
                        else f"SYN-{t:02d}{c}-{typ.upper()}-001",
                        lot=f"SYN-LOT-{t:02d}",
                        supplier="Fictional Demonstration Supplier",
                        revision="B" if definition == "rf-b" else "A",
                        disposition="installed",
                        repair_cycle=1 if (t, c, typ) == (2, "A", "rf") else 0,
                        refurbishment_status="qualified_synthetic"
                        if (t, c, typ) == (2, "A", "rf")
                        else "new",
                        traceability_status="synthetic_complete"
                        if (t, c) != (3, "B")
                        else "source_gap",
                        manufactured_at=START - timedelta(days=30),
                    )
                )
                session.flush()
                installed = START + timedelta(days=10 if t == 3 else 0)
                if (t, c, typ) == (1, "A", "rf"):
                    installed = datetime(2026, 1, 21, tzinfo=timezone.utc)
                rec = raw(
                    session,
                    "raw-install-" + cid,
                    "synthetic_parts",
                    {
                        "component_id": cid,
                        "position_id": pos,
                        "installed_at": installed.isoformat(),
                    },
                    installed,
                )
                session.add(
                    Installation(
                        id="ins-" + cid,
                        component_id=cid,
                        position_id=pos,
                        installed_at=installed,
                        removed_at=None,
                        reason="Synthetic commissioning installation"
                        if installed < datetime(2026, 1, 1, tzinfo=timezone.utc)
                        else "Synthetic replacement",
                        removal_reason=None,
                        source_record_id=rec,
                    )
                )
                if (t, c, typ) == (2, "A", "rf"):
                    # Qualified refurbishment occurs during this life; counters retain lifetime separately.
                    rr = raw(
                        session,
                        "raw-refurb-" + cid,
                        "synthetic_maintenance",
                        {"component_id": cid, "qualified": True},
                        datetime(2026, 1, 1, tzinfo=timezone.utc),
                    )
                    session.add(
                        Refurbishment(
                            id="refurb-" + cid,
                            component_id=cid,
                            completed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                            qualified=True,
                            findings="Synthetic qualification after bench refurbishment; original serial retained",
                            source_record_id=rr,
                        )
                    )
            session.flush()
            # Observation coverage is explicit ON+OFF coverage, not RF utilization.
            obs_end = AS_OF - timedelta(days=7) if (t, c) == (3, "B") else AS_OF
            r = raw(
                session,
                "raw-coverage-" + chamber,
                "synthetic_fdc",
                {
                    "chamber_id": chamber,
                    "coverage_start": START.isoformat(),
                    "coverage_end": obs_end.isoformat(),
                },
                START,
            )
            for source in ["rf_primary", "powered"]:
                session.add(
                    ObservationCoverage(
                        id="coverage-" + chamber + "-" + source,
                        chamber_id=chamber,
                        source=source,
                        start=START,
                        end=obs_end,
                        source_record_id=r,
                    )
                )
            for day in range((obs_end - START).days):
                start = START + timedelta(days=day)
                rf_h = 12 + (t * 2) + (1 if c == "B" else 0)
                r = raw(
                    session,
                    f"raw-rf-{chamber}-{day}",
                    "synthetic_fdc",
                    {
                        "chamber_id": chamber,
                        "source": "rf_primary",
                        "start": start.isoformat(),
                        "duration_hours": rf_h,
                    },
                    start,
                )
                session.add(
                    ExposureInterval(
                        id=f"rf-{chamber}-{day}",
                        chamber_id=chamber,
                        source="rf_primary",
                        dimension="rf_hours",
                        start=start,
                        end=start + timedelta(hours=rf_h),
                        quality="synthetic",
                        source_record_id=r,
                        value=None,
                    )
                )
                session.add(
                    ExposureInterval(
                        id=f"power-{chamber}-{day}",
                        chamber_id=chamber,
                        source="powered",
                        dimension="powered_hours",
                        start=start,
                        end=start + timedelta(hours=23),
                        quality="synthetic",
                        source_record_id=r,
                        value=None,
                    )
                )
            # Cumulative counters retain a reset and a sample gap for diagnostic inspection.
            for i, value in enumerate([0, 14, 28, 2, 16]):
                r = raw(
                    session,
                    f"raw-count-{chamber}-{i}",
                    "synthetic_fdc",
                    {"value": value, "dimension": "rf_hours"},
                    START + timedelta(days=i),
                )
                session.add(
                    CounterSample(
                        id=f"counter-{chamber}-{i}",
                        chamber_id=chamber,
                        source="rf_primary",
                        dimension="rf_hours",
                        timestamp=START + timedelta(days=i),
                        value=value,
                        modulus=None,
                        source_record_id=r,
                    )
                )
    session.flush()
    # Removed serial and its replacement. Replacement itself does not prove failure.
    old = "cmp-1-a-rf-old"
    position = "pos-ch-1-a-rf"
    removed = datetime(2026, 1, 21, tzinfo=timezone.utc)
    session.add(
        ComponentInstance(
            id=old,
            definition_id="rf-a",
            serial_number="SYN-01A-RF-001",
            lot="SYN-LOT-00",
            supplier="Fictional Demonstration Supplier",
            revision="A",
            disposition="quarantined",
            repair_cycle=0,
            refurbishment_status="pending_evaluation",
            traceability_status="synthetic_complete",
            manufactured_at=START - timedelta(days=60),
        )
    )
    session.flush()
    r = raw(
        session,
        "raw-install-old",
        "synthetic_parts",
        {
            "component_id": old,
            "position_id": position,
            "removed_at": removed.isoformat(),
        },
    )
    session.add(
        Installation(
            id="ins-old-rf",
            component_id=old,
            position_id=position,
            installed_at=START,
            removed_at=removed,
            reason="Synthetic startup installation",
            removal_reason="Unscheduled removal; engineering adjudication required",
            maintenance_reference="wo-replacement",
            source_record_id=r,
        )
    )
    session.flush()
    wr = raw(
        session,
        "raw-wo-replacement",
        "synthetic_maintenance",
        {
            "old_component_id": old,
            "new_component_id": "cmp-1-a-rf",
            "kind": "unscheduled",
        },
        removed,
    )
    session.add(
        WorkOrder(
            id="wo-replacement",
            chamber_id="ch-1-a",
            title="Synthetic RF module investigation and exchange",
            kind="unscheduled",
            status="completed",
            opened_at=removed - timedelta(hours=14),
            completed_at=removed,
            source_record_id=wr,
        )
    )
    session.flush()
    session.add(
        MaintenanceAction(
            id="maint-replacement",
            work_order_id="wo-replacement",
            component_id=old,
            timestamp=removed,
            action="Removed for investigation",
            findings="Synthetic contact wear found at bench; causal review recorded separately",
            confirmed_failure=False,
        )
    )
    session.add(
        MaintenanceAction(
            id="maint-install-new",
            work_order_id="wo-replacement",
            component_id="cmp-1-a-rf",
            timestamp=removed,
            action="Installed replacement",
            findings="Replacement identity verified against synthetic tracker",
            confirmed_failure=False,
        )
    )
    session.add(
        ReplacementEvent(
            id="replacement-1",
            old_component_id=old,
            new_component_id="cmp-1-a-rf",
            work_order_id="wo-replacement",
            timestamp=removed,
            reason="Unscheduled engineering exchange; failure adjudicated separately",
        )
    )
    r = raw(
        session,
        "raw-pm-complete",
        "synthetic_maintenance",
        {"component_id": "cmp-2-b-valve", "kind": "preventive"},
        datetime(2026, 1, 16, tzinfo=timezone.utc),
    )
    session.add(
        WorkOrder(
            id="wo-pm-1",
            chamber_id="ch-2-b",
            title="Synthetic preventive valve inspection",
            kind="preventive",
            status="completed",
            opened_at=datetime(2026, 1, 16, tzinfo=timezone.utc),
            completed_at=datetime(2026, 1, 16, 2, tzinfo=timezone.utc),
            source_record_id=r,
        )
    )
    session.flush()
    session.add(
        MaintenanceAction(
            id="maint-pm-1",
            work_order_id="wo-pm-1",
            component_id="cmp-2-b-valve",
            timestamp=datetime(2026, 1, 16, 2, tzinfo=timezone.utc),
            action="Preventive inspection",
            findings="No physical failure observed; usage counter retained",
            confirmed_failure=False,
        )
    )
    session.add(
        PMDueEvent(
            id="due-demo-1",
            plan_id="plan-valve",
            component_id="cmp-2-b-valve",
            due_at=datetime(2026, 1, 16, tzinfo=timezone.utc),
            status="completed",
            completed_work_order_id="wo-pm-1",
        )
    )
    session.add(
        FailureMode(
            id="mode-contact",
            name="Synthetic contact degradation",
            mechanism="Fictional contact interface wear; requires physical inspection in real use",
        )
    )
    session.add(
        FailureMode(
            id="mode-unknown",
            name="Unconfirmed signal excursion",
            mechanism="Cause not established",
        )
    )
    session.flush()
    scenarios = [
        (
            "case-001",
            "ch-1-a",
            old,
            "Synthetic RF instability during qualification",
            datetime(2026, 1, 20, 10, tzinfo=timezone.utc),
            14,
            "confirmed",
            "confirmed",
            "mode-contact",
        ),
        (
            "case-002",
            "ch-2-b",
            "cmp-2-b-rf",
            "Repeated synthetic matching excursion",
            datetime(2026, 1, 10, 8, tzinfo=timezone.utc),
            6,
            "confirmed",
            "confirmed",
            "mode-contact",
        ),
        (
            "case-003",
            "ch-3-a",
            "cmp-3-a-rf",
            "Synthetic stability loss under review",
            datetime(2026, 1, 25, 12, tzinfo=timezone.utc),
            3,
            "investigating",
            "unconfirmed",
            "mode-unknown",
        ),
        (
            "case-004",
            "ch-2-a",
            "cmp-2-a-valve",
            "Synthetic valve restoration event",
            datetime(2026, 1, 12, 6, tzinfo=timezone.utc),
            4,
            "confirmed",
            "confirmed",
            "mode-contact",
        ),
    ]
    for case, ch, cid, title, start, hours, status, attr, mode in scenarios:
        end = start + timedelta(hours=hours)
        session.add(
            FailureEpisode(
                id=case,
                chamber_id=ch,
                component_id=cid,
                failure_mode_id=mode,
                title=title,
                started_at=start,
                ended_at=end,
                status=status,
                attribution_status=attr,
                root_cause="Synthetic physical evidence supports contact degradation"
                if status == "confirmed"
                else "Insufficient evidence to assign a hardware root cause",
                hypotheses=[
                    {
                        "name": "Contact degradation",
                        "status": "supported" if status == "confirmed" else "open",
                        "evidence": "Synthetic bench finding",
                    },
                    {
                        "name": "Control or measurement artifact",
                        "status": "not_excluded"
                        if status != "confirmed"
                        else "reviewed",
                        "evidence": "Compare unaffected chamber trace",
                    },
                ],
                review_status="reviewed_synthetic"
                if status == "confirmed"
                else "awaiting_engineering_review",
                deduplication_key="SYN-" + case,
            )
        )
        session.flush()
        rr = raw(
            session,
            "raw-evidence-" + case,
            "synthetic_maintenance",
            {"failure_id": case, "physical_findings": "Fictional evidence packet"},
            end,
        )
        session.add(
            Evidence(
                id="evidence-" + case,
                failure_id=case,
                timestamp=end,
                kind="bench_finding"
                if status == "confirmed"
                else "technician_observation",
                description="Synthetic contact surface wear documented; not real part evidence"
                if status == "confirmed"
                else "Trace excursion observed; no confirmed physical damage",
                quality="synthetic_only",
                source_record_id=rr,
            )
        )
        session.add(
            CorrectiveAction(
                id="action-" + case,
                failure_id=case,
                proposal="Inspect contact interface and compare unaffected controls; review causal alternatives",
                validation_status="synthetic_review_only",
                owner="Demo Reliability Engineering",
            )
        )
        for n in range(2):
            er = raw(
                session,
                f"raw-alarm-{case}-{n}",
                "synthetic_alarms",
                {"episode": case, "label": "Synthetic signal excursion"},
                start + timedelta(minutes=n),
            )
            session.add(
                EquipmentEvent(
                    id=f"alarm-{case}-{n}",
                    chamber_id=ch,
                    failure_id=case,
                    asserted_at=start + timedelta(minutes=n),
                    cleared_at=end,
                    label="Synthetic signal excursion"
                    if n == 0
                    else "Synthetic secondary process hold",
                    synthetic_code=f"SYN-EVENT-{n + 1}",
                    symptom_role="primary_symptom" if n == 0 else "secondary_symptom",
                    source_record_id=er,
                )
            )
        # A single equipment loss interval with separate time categories; sums never add the umbrella twice.
        rr = raw(
            session,
            "raw-down-" + case,
            "synthetic_maintenance",
            {"failure_id": case, "hours": hours},
            start,
        )
        segments = [
            ("active_repair", min(4, hours)),
            ("parts_waiting", max(0, hours - 6)),
            ("administrative_delay", 2 if hours > 6 else 0),
        ]
        cursor = start
        for n, (category, duration) in enumerate(segments):
            if duration <= 0:
                continue
            if cursor + timedelta(hours=duration) > end:
                duration = (end - cursor).total_seconds() / 3600
            did = f"down-{case}-{n}"
            session.add(
                DowntimeInterval(
                    id=did,
                    failure_id=case,
                    chamber_id=ch,
                    start=cursor,
                    end=cursor + timedelta(hours=duration),
                    category=category,
                    classification="E10-aligned demonstration: unscheduled downtime",
                    critical_path_hours=None,
                    source_record_id=rr,
                )
            )
            session.flush()
            session.add(
                DowntimeAttribution(
                    id="attr-" + did,
                    downtime_id=did,
                    component_id=cid,
                    weight=1.0,
                    status=attr,
                    rationale="Synthetic engineering adjudication"
                    if attr == "confirmed"
                    else "Association only; excluded from confirmed component attribution",
                )
            )
            cursor += timedelta(hours=duration)
        if cursor < end:
            did = f"down-{case}-rest"
            session.add(
                DowntimeInterval(
                    id=did,
                    failure_id=case,
                    chamber_id=ch,
                    start=cursor,
                    end=end,
                    category="functional_impairment",
                    classification="E10-aligned demonstration: unscheduled downtime",
                    critical_path_hours=None,
                    source_record_id=rr,
                )
            )
            session.flush()
            session.add(
                DowntimeAttribution(
                    id="attr-" + did,
                    downtime_id=did,
                    component_id=cid,
                    weight=1,
                    status=attr,
                    rationale="Synthetic remainder",
                )
            )
    # Alarm without a failure episode proves alarms are not counted as confirmed failures.
    r = raw(
        session,
        "raw-alarm-no-failure",
        "synthetic_alarms",
        {"label": "Synthetic transient; self-cleared"},
        AS_OF - timedelta(days=2),
    )
    session.add(
        EquipmentEvent(
            id="alarm-no-failure",
            chamber_id="ch-3-b",
            failure_id=None,
            asserted_at=AS_OF - timedelta(days=2),
            cleared_at=AS_OF - timedelta(days=2) + timedelta(minutes=2),
            label="Synthetic transient with no confirmed hardware failure",
            synthetic_code="SYN-TRANSIENT",
            symptom_role="unconfirmed_event",
            source_record_id=r,
        )
    )
    # Each cohort has its own raw values and timestamps preceding its actual case.
    for cid, ch, case in [
        (old, "ch-1-a", "case-001"),
        ("cmp-2-b-rf", "ch-2-b", "case-002"),
        ("cmp-3-a-rf", "ch-3-a", "case-003"),
    ]:
        event_time = next(x[4] for x in scenarios if x[0] == case)
        for i in range(30):
            for cohort in ["normal", "pre_failure"]:
                at = event_time - timedelta(
                    minutes=30 - i, days=1 if cohort == "normal" else 0
                )
                value = (
                    1
                    + 0.02 * math.sin(i)
                    + (max(0, i - 15) * 0.018 if cohort == "pre_failure" else 0)
                )
                r = raw(
                    session,
                    f"raw-fdc-{cid}-{i}-{cohort}",
                    "synthetic_fdc",
                    {
                        "component_id": cid,
                        "signal": "normalized_rf_response",
                        "value": value,
                        "cohort": cohort,
                        "unit": "normalized demo units",
                        "case_id": case,
                    },
                    at,
                )
                session.add(
                    FDCPoint(
                        id=f"fdc-{cid}-{i}-{cohort}",
                        chamber_id=ch,
                        component_id=cid,
                        timestamp=at,
                        signal="normalized_rf_response",
                        value=value,
                        unit="normalized demo units",
                        state="synthetic_stable_process",
                        cohort=cohort,
                        source_record_id=r,
                    )
                )
    ra = raw(
        session,
        "raw-conflict-maint",
        "synthetic_maintenance",
        {"component_id": old, "installed_component": "cmp-1-a-rf"},
        removed,
    )
    rb = raw(
        session,
        "raw-conflict-parts",
        "synthetic_parts",
        {"component_id": old, "installed_component": old},
        removed,
    )
    session.add(
        SourceConflict(
            id="conflict-001",
            component_id=old,
            field="installed_component",
            record_a_id=ra,
            record_b_id=rb,
            value_a="cmp-1-a-rf",
            value_b=old,
            status="unresolved",
            decision=None,
            note=None,
            resolved_at=None,
        )
    )
    session.add(
        CommissioningMilestone(
            id="milestone-1",
            tool_id="tool-1",
            name="Synthetic qualification checkpoint",
            planned_at=datetime(2026, 1, 21, tzinfo=timezone.utc),
            actual_at=datetime(2026, 1, 22, tzinfo=timezone.utc),
            failure_id="case-001",
            critical_path_established=False,
        )
    )
    for source in ["maintenance", "fdc", "parts", "alarms", "commissioning", "generic"]:
        session.add(
            IngestionRun(
                id="seed-run-" + source,
                adapter_id=source,
                started_at=AS_OF,
                completed_at=AS_OF,
                status="synthetic_fixture_loaded",
                record_count=session.query(RawSourceRecord)
                .filter(RawSourceRecord.source.like("%" + source + "%"))
                .count(),
                duplicate_count=0,
                errors=[
                    {
                        "code": "coverage_gap",
                        "message": "Chamber 3B observation ends seven days before snapshot",
                    }
                ]
                if source == "fdc"
                else [],
                cursor=None,
            )
        )
    session.add(
        AuditLog(
            id="audit-seed",
            timestamp=AS_OF,
            actor="synthetic-seeder",
            role="admin",
            action="seed",
            entity_type="dataset",
            entity_id="frip-demo-v1",
            detail={"synthetic": True, "as_of": AS_OF.isoformat()},
        )
    )
    session.commit()
    return True


if __name__ == "__main__":
    if settings().mode != "synthetic":
        raise SystemExit("Synthetic seeding is disabled outside FRIP_MODE=synthetic")
    engine = make_engine(settings().database_url)
    migrate(engine)
    with Session(engine) as session:
        print(
            "Synthetic seed created"
            if seed(session)
            else "Synthetic seed already present; no changes"
        )
