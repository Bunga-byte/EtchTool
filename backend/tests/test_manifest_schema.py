"""Machine-readable handoff can be consumed without guessing proprietary schemas."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "schemas/manifest.schema.json").read_text())


def test_manifest_schema_is_valid():
    Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize(
    "path",
    sorted((ROOT / "integration_manifests").glob("*.json")),
    ids=lambda p: p.stem,
)
def test_enterprise_manifest_obeys_strict_schema(path):
    value = json.loads(path.read_text())
    Draft202012Validator(SCHEMA).validate(value)
    assert value, "An empty manifest cannot define an internal handoff"


def test_required_handoff_guides_exist_and_all_six_sources_have_manifests():
    assert len(list((ROOT / "integration_manifests").glob("*.json"))) == 6
    for name in [
        "SAMSUNG_HANDOFF",
        "INTEGRATION_MATRIX",
        "DATA_DICTIONARY",
        "SENSOR_MAPPING_GUIDE",
        "RF_HOUR_VALIDATION",
        "SECURITY_AND_DATA_BOUNDARIES",
        "INTERNAL_AI_INSTRUCTIONS",
    ]:
        assert (ROOT / f"docs/{name}.md").stat().st_size > 100
