"""Additive idempotent synthetic source setup; never resets existing domain data."""

from datetime import datetime, timezone
from sqlalchemy import select
from app.models import ComponentInstance, Position, Tool
from .models import EnterpriseSource, EntityAlias, EquipmentConfigurationPeriod

START = datetime(2025, 12, 1, tzinfo=timezone.utc)


def seed_enterprise(session):
    changed = False
    sources = [
        (
            "informs-demo",
            "Synthetic Informs maintenance documents",
            ["maintenance", "procedures"],
            "synthetic_informs",
        ),
        (
            "lam-demo",
            "Synthetic serialized parts inventory",
            ["parts"],
            "synthetic_lam_parts",
        ),
        ("fdc-demo", "Synthetic FDC telemetry", ["telemetry"], "synthetic_fdc"),
    ]
    for id, name, collections, system in sources:
        if session.get(EnterpriseSource, id) is None:
            session.add(
                EnterpriseSource(
                    id=id,
                    name=name,
                    connector_kind="synthetic_file",
                    classification="synthetic",
                    capabilities={
                        "search": True,
                        "retrieve_documents": True,
                        "retrieve_attachments": True,
                        "incremental_polling": True,
                        "discover_schema": True,
                    },
                    config={
                        "source_system": system,
                        "authority_rules": {},
                        "read_only": True,
                    },
                    authorized_equipment=["tool1a"],
                    authorized_collections=collections,
                    enabled=True,
                    polling_allowed=False,
                    interval_seconds=3600,
                    last_success_at=None,
                )
            )
            changed = True
    session.flush()
    spare = "cmp-enterprise-spare"
    if session.get(ComponentInstance, spare) is None:
        session.add(
            ComponentInstance(
                id=spare,
                definition_id="rf-a",
                serial_number="SYN-01A-RF-003",
                lot="SYN-ENTERPRISE-LOT",
                supplier="Fictional Demonstration Supplier",
                revision="A",
                disposition="spare",
                repair_cycle=0,
                refurbishment_status="new",
                traceability_status="synthetic_complete",
                manufactured_at=START,
            )
        )
        changed = True
    if session.get(ComponentInstance, "cmp-enterprise-install-spare") is None:
        session.add(
            ComponentInstance(
                id="cmp-enterprise-install-spare",
                definition_id="rf-a",
                serial_number="SYN-ENT-INSTALL-001",
                lot="SYN-ENTERPRISE-LOT",
                supplier="Fictional Demonstration Supplier",
                revision="A",
                disposition="spare",
                repair_cycle=0,
                refurbishment_status="new",
                traceability_status="synthetic_complete",
                manufactured_at=START,
            )
        )
        changed = True
    # An intentionally empty conceptual slot exercises reviewed new installations.
    if session.get(Position, "pos-enterprise-empty") is None:
        session.add(
            Position(
                id="pos-enterprise-empty",
                assembly_id="ass-ch-1-a-rf",
                name="Synthetic auxiliary RF slot",
                exposure_source="rf_primary",
                description="Empty conceptual demonstration slot; not OEM geometry",
            )
        )
        changed = True
    session.flush()
    aliases = [
        ("tool", "tool1a", "tool-1"),
        ("chamber", "ch1a", "ch-1-a"),
        ("position", "rf1a", "pos-ch-1-a-rf"),
        ("position", "rf_empty_1a", "pos-enterprise-empty"),
        ("position", "emptyrf1a", "pos-enterprise-empty"),
        ("component", "SYN-ENT-INSTALL-001", "cmp-enterprise-install-spare"),
        ("component", "SYN-01A-RF-002", "cmp-1-a-rf"),
        ("component", "SYN-01A-RF-003", spare),
        ("definition", "SYN-RF-100-A", "rf-a"),
    ]
    for source, _, _, _ in sources:
        for entity_type, external, canonical in aliases:
            id = f"alias-{source}-{entity_type}-{external}"
            if session.get(EntityAlias, id) is None:
                session.add(
                    EntityAlias(
                        id=id,
                        source_id=source,
                        entity_type=entity_type,
                        external_id=external,
                        canonical_id=canonical,
                        valid_from=START,
                        valid_to=None,
                        verification_status="verified",
                        evidence=[
                            {
                                "type": "synthetic_seed",
                                "note": "Fictional canonical identity mapping; must be replaced with reviewed corporate mapping",
                            }
                        ],
                    )
                )
                changed = True
    for tool in session.scalars(select(Tool)):
        id = "config-period-" + tool.id
        if session.get(EquipmentConfigurationPeriod, id) is None:
            session.add(
                EquipmentConfigurationPeriod(
                    id=id,
                    tool_id=tool.id,
                    configuration_id=tool.configuration_id,
                    effective_from=START,
                    effective_to=None,
                    verification="verified_synthetic",
                    source_record_id=None,
                )
            )
            changed = True
    session.flush()
    # Telemetry setup is additive too; keep approvals explicit in its own service.
    from .telemetry import seed_telemetry

    changed = seed_telemetry(session) or changed
    return changed
