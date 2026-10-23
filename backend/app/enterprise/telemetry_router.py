"""Bounded diagnostic reads and source-scoped engineering review routes."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import AwareDatetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal, principal, require_roles
from app.db import get_session
from app.models import ComponentInstance
from .models import ComponentSensorMapping, EnterpriseSource, ExposureDefinition, SensorChannel
from .telemetry_contracts import EngineeringReview, ExposureRuleInput, MappingInput
from . import telemetry as service
from .canonical_security import canonical_scope

router = APIRouter(prefix="/api/enterprise", tags=["Approved component telemetry"])


def _required(session, model, id):
    item = session.get(model, id)
    if item is None:
        raise HTTPException(404, f"{model.__name__} not found")
    return item


def _authorize(session: Session, sensor: SensorChannel, actor: Principal, *, write=False):
    source = _required(session, EnterpriseSource, sensor.source_id)
    if not service.source_allowed(session, actor, source, write=write, sensor=sensor):
        raise HTTPException(403, "Telemetry source is outside authorized scope")


@router.get("/sensors")
def sensors(source_id: str | None = None, chamber_id: str | None = None, actor: Principal = Depends(principal), session: Session = Depends(get_session)):
    items = []
    for sensor in session.scalars(select(SensorChannel).order_by(SensorChannel.channel_key)):
        source = session.get(EnterpriseSource, sensor.source_id)
        if service.source_allowed(session, actor, source, sensor=sensor) and (not source_id or sensor.source_id == source_id) and (not chamber_id or sensor.chamber_id == chamber_id):
            items.append(service.sensor_dict(sensor))
    return {"items": items, "note": "Ranges remain unknown unless supplied by a referenced authorized document"}


@router.get("/mappings")
def mappings(definition_id: str | None = None, actor: Principal = Depends(principal), session: Session = Depends(get_session)):
    items = []
    for mapping in session.scalars(select(ComponentSensorMapping).order_by(ComponentSensorMapping.effective_from)):
        sensor = session.get(SensorChannel, mapping.sensor_id)
        source = session.get(EnterpriseSource, sensor.source_id)
        if service.source_allowed(session, actor, source, sensor=sensor) and (not definition_id or mapping.definition_id == definition_id):
            items.append({**service.mapping_dict(mapping), "channel_key": sensor.channel_key, "source_id": sensor.source_id})
    return {"items": items}


@router.post("/mappings", status_code=201)
@router.post("/mappings/propose", status_code=201)
def propose_mapping(body: MappingInput, actor: Principal = Depends(require_roles("analyst", "editor", "admin")), session: Session = Depends(get_session)):
    sensor = _required(session, SensorChannel, body.sensor_id)
    _authorize(session, sensor, actor, write=True)
    try:
        mapping = service.create_mapping(session, body, actor)
        session.commit()
        return service.mapping_dict(mapping)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(409, str(exc))
    except PermissionError as exc:
        session.rollback()
        raise HTTPException(403, str(exc))


@router.post("/mappings/{id}/review")
def review_mapping(id: str, body: EngineeringReview, actor: Principal = Depends(require_roles("editor", "admin")), session: Session = Depends(get_session)):
    mapping = _required(session, ComponentSensorMapping, id)
    _authorize(session, _required(session, SensorChannel, mapping.sensor_id), actor, write=True)
    try:
        service.review_mapping(session, mapping, body.decision, body.note, actor)
        session.commit()
        return service.mapping_dict(mapping)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(409, str(exc))
    except PermissionError as exc:
        session.rollback()
        raise HTTPException(403, str(exc))


@router.get("/exposure-rules")
def exposure_rules(actor: Principal = Depends(principal), session: Session = Depends(get_session)):
    items = []
    for rule in session.scalars(select(ExposureDefinition).order_by(ExposureDefinition.effective_from)):
        source = session.get(EnterpriseSource, rule.source_id)
        if service.source_allowed(session, actor, source, sensor=session.get(SensorChannel, rule.sensor_id)):
            items.append(service.rule_dict(rule))
    return {"items": items}


@router.post("/exposure-rules", status_code=201)
def propose_rule(body: ExposureRuleInput, actor: Principal = Depends(require_roles("editor", "admin")), session: Session = Depends(get_session)):
    sensor = _required(session, SensorChannel, body.sensor_id)
    _authorize(session, sensor, actor, write=True)
    try:
        rule = service.create_rule(session, body, actor)
        session.commit()
        return service.rule_dict(rule)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(409, str(exc))
    except PermissionError as exc:
        session.rollback()
        raise HTTPException(403, str(exc))


@router.post("/exposure-rules/{id}/review")
def review_rule(id: str, body: EngineeringReview, actor: Principal = Depends(require_roles("editor", "admin")), session: Session = Depends(get_session)):
    rule = _required(session, ExposureDefinition, id)
    _authorize(session, _required(session, SensorChannel, rule.sensor_id), actor, write=True)
    try:
        service.review_rule(session, rule, body.decision, body.note, actor)
        session.commit()
        return service.rule_dict(rule)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(409, str(exc))
    except PermissionError as exc:
        session.rollback()
        raise HTTPException(403, str(exc))


@router.get("/components/{id}/telemetry")
def component_telemetry(id: str, request: Request, start: AwareDatetime, end: AwareDatetime, state: str | None = Query(None, max_length=80), max_points: int = Query(1000, ge=10, le=1000), actor: Principal = Depends(principal), session: Session = Depends(get_session)):
    component = canonical_scope(session, actor, request.app.state.config.mode).require_component(session, id)
    try:
        return service.component_telemetry(session, component, start=start, end=end, state=state, max_points=max_points, actor=actor)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/components/{id}/lineage")
def component_lineage(id: str, request: Request, actor: Principal = Depends(principal), session: Session = Depends(get_session)):
    canonical_scope(session, actor, request.app.state.config.mode).require_component(session, id)
    return service.component_lineage(session, id, actor)
