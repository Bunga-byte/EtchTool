"""Scenario I drives production APIs; fixed expectations are hand-calculated."""

import pytest

from app.enterprise.demo import run_demo


def test_scenario_i_source_review_component_exposure_and_pm(tmp_path):
    report = run_demo(tmp_path)
    assert (
        report["source_job"]["status"]
        == report["telemetry_job"]["status"]
        == "succeeded"
    )
    assert report["source_job"]["metrics"]["processed"] == 1
    assert report["telemetry_job"]["metrics"]["processed"] == 1
    assert report["evidence_spans_verified"] >= 8
    assert report["review_status"] == "approved" and report["failure_created"] is False
    assert (
        report["old_removed_at"] == report["replacement_at"] == "2026-01-26T00:00:00Z"
    )
    assert report["old_component_rf_hours"] == 70
    assert (
        report["baseline_new_component_rf_hours"]
        == report["unapproved_telemetry_rf_hours"]
        == 70
    )
    # Five days, each with one twelve-hour RF-active period and twelve hours off.
    assert report["approved_new_component_rf_hours"] == 5 * 12
    assert report["pm"]["threshold"] == 650
    assert report["pm"]["remaining"] == 590
    assert report["pm"]["percent_consumed"] == pytest.approx(9.23)
    assert report["inventory_refreshed"]
    assert report["fleet_pm_refreshed"] == report["pm"]
    assert len(report["lineage"]["items"]) >= 1
    assert len(report["telemetry"]["channels"]) == 2
    assert {c["relationship"] for c in report["telemetry"]["channels"]} == {
        "exposure_counter",
        "supporting_diagnostic",
    }
    assert all(c["points"] for c in report["telemetry"]["channels"])


def test_demo_refuses_to_overwrite_a_database(tmp_path):
    database = tmp_path / "enterprise-demo.db"
    database.write_text("preserve existing data")
    with pytest.raises(ValueError, match="new isolated database"):
        run_demo(tmp_path)
    assert database.read_text() == "preserve existing data"
