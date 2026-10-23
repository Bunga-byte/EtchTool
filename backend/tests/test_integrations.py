"""Source-boundary and batch correctness tests; no network access is required."""
import json
from pathlib import Path

import pytest

from app.integrations import ADAPTERS, adapter_descriptions, ingest_records, parse_csv_records, parse_json_records


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.mark.parametrize("adapter_id", list(ADAPTERS))
def test_six_typed_synthetic_connectors(adapter_id):
    rows = load(adapter_id)
    result = ingest_records(adapter_id, rows, authorized_sources={adapter_id})
    assert len(result.records) == len(rows)
    assert not result.errors
    assert result.audit[0]["accepted"] == len(rows)
    assert all(row.verification == "synthetic_unverified" for row in result.records)
    assert all(item["connected"] is False for item in adapter_descriptions())


def test_connector_scope_cannot_be_bypassed():
    with pytest.raises(PermissionError, match="not authorized"):
        ingest_records("maintenance", load("maintenance"), authorized_sources={"fdc"})


def test_unknown_adapter_and_invalid_configuration_fail():
    with pytest.raises(KeyError, match="unknown adapter"):
        ingest_records("real_internal_api", [], authorized_sources={"real_internal_api"})
    with pytest.raises(ValueError, match="mapping targets"):
        ingest_records("fdc", [], authorized_sources={"fdc"}, field_mapping={"x":"unknown_field"})
    with pytest.raises(ValueError, match="multiple source fields"):
        ingest_records("fdc", [], authorized_sources={"fdc"}, field_mapping={"x":"value","y":"value"})
    with pytest.raises(ValueError, match="page_size"):
        ingest_records("fdc", [], authorized_sources={"fdc"}, page_size=0)


def test_dedup_retries_preserve_original_and_do_not_duplicate_records():
    rows = load("parts")
    initial = ingest_records("parts", rows, authorized_sources={"parts"})
    retried = ingest_records("parts", rows + rows, authorized_sources={"parts"}, existing=initial.records)
    assert retried.duplicates == 4
    assert not retried.records
    assert len(retried.originals) == 4
    original = initial.originals[0]
    assert json.loads(original.original_json) == rows[0]
    rows[0]["part_number"] = "mutated caller dictionary"
    assert json.loads(original.original_json)["part_number"] == "SYN-PN-100"
    with pytest.raises(Exception):
        original.fingerprint = "overwritten"


def test_pagination_uses_compound_cursor_including_equal_timestamps():
    rows = load("fdc")
    for row in rows:
        row["effective_at"] = "2026-10-20T08:00:00Z"
    first = ingest_records("fdc", rows, authorized_sources={"fdc"}, page_size=2)
    second = ingest_records("fdc", rows, authorized_sources={"fdc"}, page_size=2, cursor=first.next_cursor)
    third = ingest_records("fdc", rows, authorized_sources={"fdc"}, page_size=2, cursor=second.next_cursor)
    ids = [row.source_id for result in (first, second, third) for row in result.records]
    assert len(ids) == len(set(ids)) == 5
    assert third.next_cursor is None
    with pytest.raises(ValueError, match="cursor"):
        ingest_records("fdc", rows, authorized_sources={"fdc"}, cursor="not-a-valid-cursor")


def test_bad_rows_retained_and_valid_rows_continue():
    good = load("fdc")[0]
    bad = dict(good, source_id="SYN-BAD", value="not-a-number", effective_at="2026-10-20T08:00:00")
    result = ingest_records("fdc", [bad,good], authorized_sources={"fdc"})
    assert len(result.records) == 1
    assert len(result.originals) == 2
    assert result.errors[0].row == 1
    assert "UTC offset" in result.errors[0].message
    assert "value" in result.errors[0].message


def test_synthetic_attestation_and_unknown_fields_are_required():
    row = load("parts")[0]
    row.pop("synthetic")
    row["real_proprietary_field"] = "not accepted"
    result = ingest_records("parts", [row], authorized_sources={"parts"})
    assert not result.records
    assert "synthetic" in result.errors[0].message
    assert "real_proprietary_field" in result.errors[0].message


def test_changed_record_is_conflict_not_last_arrival_wins():
    original = load("parts")[1]
    first = ingest_records("parts", [original], authorized_sources={"parts"})
    changed = dict(original, component_serial="SYN-DISAGREEMENT")
    result = ingest_records("parts", [changed], authorized_sources={"parts"}, existing=first.records)
    assert len(result.records) == 1  # both originals survive, physical state is not changed
    conflict = result.conflicts[0]
    assert conflict.field == "component_serial"
    assert conflict.status == "unresolved"
    assert conflict.current_value == "SYN-SERIAL-NEW"
    assert first.records[0].payload["component_serial"] == "SYN-SERIAL-NEW"


def test_explicit_authority_rule_is_auditable():
    row = load("parts")[1]
    previous = {"source":"authorized-maintenance-export", "source_id":"SYN-OTHER", "payload":dict(row,component_serial="SYN-OTHER")}
    result = ingest_records("parts", [row], authorized_sources={"parts"}, existing=[previous],
                            authority_rules={"parts.component_serial":"authorized-maintenance-export"})
    conflict = result.conflicts[0]
    assert conflict.status == "authority_rule_applied"
    assert conflict.authoritative_source == "authorized-maintenance-export"
    assert result.records[0].payload["component_serial"] == row["component_serial"]


def test_source_priority_cannot_resolve_conflicting_rows_from_same_source():
    row = load("fdc")[0]
    first = ingest_records("fdc", [row], authorized_sources={"fdc"})
    changed = dict(row, value=500.0)
    result = ingest_records("fdc", [changed], authorized_sources={"fdc"}, existing=first.records,
                            authority_rules={"fdc.value":"fdc"})
    assert result.conflicts[0].status == "unresolved"
    assert result.conflicts[0].authoritative_source is None


def test_historical_replacement_is_not_a_conflict_or_failure():
    result = ingest_records("parts", load("parts"), authorized_sources={"parts"})
    assert len(result.records) == 2
    assert not result.conflicts
    alarm = ingest_records("alarms", load("alarms"), authorized_sources={"alarms"}).records[0]
    assert "failure" not in alarm.payload
    assert alarm.payload["episode_reference"] is None


def test_field_mapping_does_not_discard_unknown_data():
    row = load("fdc")[0]
    row["sample_number"] = row.pop("value")
    result = ingest_records("fdc", [row], authorized_sources={"fdc"}, field_mapping={"sample_number":"value"})
    assert result.records[0].payload["value"] == 1.0
    assert "sample_number" in result.records[0].original_json
    row["value"] = 100
    collision = ingest_records("fdc", [row], authorized_sources={"fdc"}, field_mapping={"sample_number":"value"})
    assert "mapping collision" in collision.errors[0].message


def test_strict_file_formats_and_csv_example():
    records = parse_csv_records((FIXTURES / "fdc.csv").read_text())
    result = ingest_records("fdc", records, authorized_sources={"fdc"})
    assert len(result.records) == 5
    assert not result.errors
    assert len(parse_json_records((FIXTURES / "fdc.json").read_text())) == 5
    for document in ('{"records":[]}', '[1]', '[{"value":NaN}]', 'invalid'):
        with pytest.raises(ValueError):
            parse_json_records(document)
    for document in ("a,a\n1,2", "a,b\n1", "a,b\n1,2,3", "synthetic\nfalse"):
        with pytest.raises(ValueError):
            parse_csv_records(document)
