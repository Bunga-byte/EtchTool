"""Strict batch connectors with no network clients or internal endpoints."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from pydantic import BaseModel, ValidationError

from .schemas import (
    AlarmRecord,
    CommissioningRecord,
    DataConflict,
    FDCRecord,
    GenericRecord,
    IngestionResult,
    MaintenanceRecord,
    NormalizedRecord,
    PartRecord,
    RawOriginal,
    RowError,
    SourceRecord,
)


@dataclass(frozen=True)
class AdapterDefinition:
    id: str
    name: str
    target: str
    schema: type[SourceRecord]
    identity_fields: tuple[str, ...]
    comparison_fields: tuple[str, ...]

    def validate_mapping(self, mapping: dict[str, str]) -> None:
        unknown = set(mapping.values()) - set(self.schema.model_fields)
        if unknown:
            raise ValueError(
                f"mapping targets are not in FRIP schema: {', '.join(sorted(unknown))}"
            )
        if len(set(mapping.values())) != len(mapping):
            raise ValueError("multiple source fields cannot map to one target")

    def map_record(
        self, row: dict[str, Any], mapping: dict[str, str]
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in row.items():
            target = mapping.get(key, key)
            if target in result:
                raise ValueError(f"mapping collision for {target}")
            result[target] = value
        return result


ADAPTERS: dict[str, AdapterDefinition] = {
    "maintenance": AdapterDefinition(
        "maintenance",
        "Maintenance files",
        "c-TTTM / Informs (not connected)",
        MaintenanceRecord,
        ("equipment_id", "work_order_id", "component_serial"),
        ("action", "completed_at", "replacement_serial", "finding"),
    ),
    "fdc": AdapterDefinition(
        "fdc",
        "FDC trace files",
        "FDC Trace (not connected)",
        FDCRecord,
        ("equipment_id", "chamber_id", "signal"),
        ("value", "unit", "operating_state", "rf_source"),
    ),
    "parts": AdapterDefinition(
        "parts",
        "Serialized part files",
        "Lam UI part tracker (not connected)",
        PartRecord,
        ("equipment_id", "chamber_id", "position_id"),
        ("component_serial", "part_number", "revision", "installed_at", "removed_at"),
    ),
    "alarms": AdapterDefinition(
        "alarms",
        "Equipment event files",
        "Equipment alarm/event history (not connected)",
        AlarmRecord,
        ("equipment_id", "event_id"),
        ("event_type", "code", "message", "episode_reference"),
    ),
    "commissioning": AdapterDefinition(
        "commissioning",
        "Commissioning files",
        "Commissioning records (not connected)",
        CommissioningRecord,
        ("equipment_id", "milestone"),
        ("status", "configuration", "document_reference"),
    ),
    "generic": AdapterDefinition(
        "generic",
        "Generic authorized files",
        "Additional enterprise sources (not connected)",
        GenericRecord,
        ("equipment_id", "record_type", "source_id"),
        ("data",),
    ),
}


def adapter_descriptions() -> list[dict[str, Any]]:
    return [
        {
            "id": item.id,
            "name": item.name,
            "target": item.target,
            "mode": "synthetic_file",
            "connected": False,
            "status": "file_only",
            "schema_version": "frip-interchange-v1",
            "authorization_scope": f"ingest:{item.id}",
            "fields": list(item.schema.model_fields),
            "required_fields": [
                name
                for name, field in item.schema.model_fields.items()
                if field.is_required()
            ],
        }
        for item in ADAPTERS.values()
    ]


def parse_json_records(content: str) -> list[dict[str, Any]]:
    """Accept an array only; never guess vendor response envelopes."""
    try:
        data = json.loads(
            content,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"invalid JSON number {value}")
            ),
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("invalid JSON records document") from exc
    if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
        raise ValueError("JSON records must be an array of objects")
    if len(data) > 10000:
        raise ValueError("batch exceeds 10000 records")
    return data


def parse_csv_records(content: str) -> list[dict[str, Any]]:
    """CSV values are validated by typed schemas; blank optional cells become null."""
    reader = csv.DictReader(io.StringIO(content))
    fields = reader.fieldnames
    if (
        not fields
        or any(not field for field in fields)
        or len(set(fields)) != len(fields)
    ):
        raise ValueError("CSV requires unique nonempty column names")
    result = []
    for index, row in enumerate(reader, start=2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"CSV row {index} has the wrong number of fields")
        item: dict[str, Any] = {
            key: value if value != "" else None for key, value in row.items()
        }
        if "synthetic" in item:
            if item["synthetic"] not in ("true", "True", "TRUE"):
                raise ValueError(f"CSV row {index} must attest synthetic=true")
            item["synthetic"] = True
        if item.get("data") is not None:
            try:
                item["data"] = json.loads(item["data"])
            except (json.JSONDecodeError, TypeError) as exc:
                raise ValueError(f"CSV row {index} data must contain JSON") from exc
        result.append(item)
        if len(result) > 10000:
            raise ValueError("batch exceeds 10000 records")
    return result


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=lambda item: item.isoformat()
        if isinstance(item, datetime)
        else str(item),
    )


def fingerprint(source: str, value: dict[str, Any]) -> str:
    return hashlib.sha256(
        (source + "\n" + canonical_json(value)).encode("utf-8")
    ).hexdigest()


def _cursor_key(record: NormalizedRecord) -> tuple[str, str, str]:
    return (record.effective_at.isoformat(), record.source_id, record.fingerprint)


def _encode_cursor(key: tuple[str, str, str]) -> str:
    return base64.urlsafe_b64encode(json.dumps(key).encode()).decode()


def _decode_cursor(cursor: str | None) -> tuple[str, str, str] | None:
    if cursor is None:
        return None
    try:
        result = json.loads(
            base64.b64decode(cursor.encode(), altchars=b"-_", validate=True)
        )
        if (
            not isinstance(result, list)
            or len(result) != 3
            or not all(isinstance(value, str) for value in result)
        ):
            raise ValueError("wrong cursor shape")
        datetime.fromisoformat(result[0])
        return tuple(result)
    except (ValueError, UnicodeError, TypeError) as exc:
        raise ValueError("invalid incremental cursor") from exc


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return dict(value)


def _subject(adapter: AdapterDefinition, payload: dict[str, Any]) -> str:
    return "|".join(str(payload.get(field, "")) for field in adapter.identity_fields)


def ingest_records(
    adapter_id: str,
    rows: list[dict[str, Any]],
    *,
    authorized_sources: set[str],
    existing: Iterable[dict[str, Any]] = (),
    cursor: str | None = None,
    page_size: int = 100,
    field_mapping: dict[str, str] | None = None,
    authority_rules: dict[str, str] | None = None,
    now: datetime | None = None,
) -> IngestionResult:
    """Validate then page a batch; preserve conflicts rather than overwriting.

    `existing` is a persistence-supplied collection of normalized envelopes.
    Authority rules map `adapter_id.field` to an explicitly approved source ID.
    No rule is installed by default. A rule selects authority, not truth: originals
    and a conflict decision remain available for engineering review.
    """
    if adapter_id not in ADAPTERS:
        raise KeyError(f"unknown adapter {adapter_id}")
    if adapter_id not in authorized_sources:
        raise PermissionError(f"not authorized for source {adapter_id}")
    if not 1 <= page_size <= 1000:
        raise ValueError("page_size must be between 1 and 1000")
    if len(rows) > 10000:
        raise ValueError("batch exceeds 10000 records")
    adapter = ADAPTERS[adapter_id]
    mapping = field_mapping or {}
    adapter.validate_mapping(mapping)
    after = _decode_cursor(cursor)
    ingested = now or datetime.now(timezone.utc)
    if ingested.tzinfo is None:
        raise ValueError("ingestion time must include timezone")
    result = IngestionResult(source=adapter_id)
    candidates: list[NormalizedRecord] = []
    for row_number, raw in enumerate(rows, start=1):
        try:
            original = canonical_json(raw)
            raw_fingerprint = fingerprint(adapter_id, raw)
            result.originals.append(
                RawOriginal(
                    source=adapter_id,
                    row=row_number,
                    ingested_at=ingested,
                    original_json=original,
                    fingerprint=raw_fingerprint,
                )
            )
            mapped = adapter.map_record(raw, mapping)
            validated = adapter.schema.model_validate(mapped)
            payload = validated.model_dump(mode="json")
            candidates.append(
                NormalizedRecord(
                    source=adapter_id,
                    source_id=validated.source_id,
                    recorded_at=validated.recorded_at,
                    effective_at=validated.effective_at,
                    ingested_at=ingested,
                    payload=payload,
                    fingerprint=fingerprint(adapter_id, payload),
                    original_json=original,
                )
            )
        except (ValidationError, ValueError, TypeError) as exc:
            message = (
                "; ".join(
                    f"{'.'.join(map(str, err['loc']))}: {err['msg']}"
                    for err in exc.errors()
                )
                if isinstance(exc, ValidationError)
                else str(exc)
            )
            result.errors.append(
                RowError(
                    row=row_number,
                    code="schema_validation",
                    message=message,
                    source_id=str(raw.get("source_id"))
                    if raw.get("source_id")
                    else None,
                )
            )
    candidates.sort(key=_cursor_key)
    remaining = [
        item for item in candidates if after is None or _cursor_key(item) > after
    ]
    page = remaining[:page_size]
    seen = [_as_dict(item) for item in existing]
    seen_fingerprints = {item.get("fingerprint") for item in seen}
    rules = authority_rules or {}
    for item in page:
        result.processed += 1
        if item.fingerprint in seen_fingerprints:
            result.duplicates += 1
            continue
        subject = _subject(adapter, item.payload)
        for previous in seen:
            previous_payload = previous.get("payload", {})
            previous_source = str(previous.get("source", "unknown"))
            same_source_id = (
                previous_source == adapter_id
                and previous.get("source_id") == item.source_id
            )
            # Distinct effective dates are historical changes, not automatically conflicts.
            same_subject_time = _subject(
                adapter, previous_payload
            ) == subject and previous_payload.get("effective_at") == item.payload.get(
                "effective_at"
            )
            if not same_source_id and not same_subject_time:
                continue
            for field in dict.fromkeys(
                (*adapter.comparison_fields, *adapter.identity_fields)
            ):
                if field not in previous_payload or previous_payload.get(
                    field
                ) == item.payload.get(field):
                    continue
                authority = rules.get(f"{adapter_id}.{field}")
                # A source priority cannot decide which revision from the same
                # source is correct. Such corrections require adjudication.
                rule_applies = previous_source != adapter_id and authority in (
                    previous_source,
                    adapter_id,
                )
                result.conflicts.append(
                    DataConflict(
                        subject=subject,
                        field=field,
                        current_value=previous_payload.get(field),
                        incoming_value=item.payload.get(field),
                        current_source=previous_source,
                        incoming_source=adapter_id,
                        current_source_id=previous.get("source_id"),
                        incoming_source_id=item.source_id,
                        status="authority_rule_applied"
                        if rule_applies
                        else "unresolved",
                        authoritative_source=authority if rule_applies else None,
                    )
                )
        result.records.append(item)
        seen.append(item.model_dump(mode="json"))
        seen_fingerprints.add(item.fingerprint)
    if len(remaining) > len(page) and page:
        result.next_cursor = _encode_cursor(_cursor_key(page[-1]))
    result.audit.append(
        {
            "action": "synthetic_batch_ingestion",
            "source": adapter_id,
            "timestamp": ingested.isoformat(),
            "processed": result.processed,
            "accepted": len(result.records),
            "duplicates": result.duplicates,
            "errors": len(result.errors),
            "conflicts": len(result.conflicts),
        }
    )
    return result
