"""Engineering examples assert physical accounting and statistical identities."""
from math import exp

import pytest

from app.services.exposure import calculate_exposure, component_exposure, counter_intervals
from app.services.failure import deduplicate_episodes, downtime_summary
from app.services.forecast import INSUFFICIENT, component_forecast, synthetic_demo_forecast, validate_split
from app.services.pm import evaluate_pm
from app.services.reliability import kaplan_meier, poisson_rate, repair_statistics, revision_rates, weibull_fit

START = "2026-01-01T00:00:00Z"


def period(start, end, **extra):
    return {"start": f"2026-01-01T{start}:00:00Z", "end": f"2026-01-01T{end}:00:00Z", "source": "fdc", "dimension": "rf_hours", **extra}


def sample(hour, value, **extra):
    return {"at": f"2026-01-01T{hour}:00:00Z", "value": value, **extra}


def test_exposure_stops_at_removal_and_replacement_starts_new_life():
    raw = [period("00", "08")]
    old = calculate_exposure(raw, START, "2026-01-01T03:00:00Z", as_of="2026-01-01T10:00:00Z", source="fdc", coverage_intervals=[period("00", "10")])
    new = calculate_exposure(raw, "2026-01-01T03:00:00Z", as_of="2026-01-01T10:00:00Z", source="fdc", coverage_intervals=[period("00", "10")])
    assert old["hours"] == 3
    assert new["hours"] == 5
    assert old["hours"] + new["hours"] == 8
    assert old["lifetime_hours"] == 3


def test_duplicate_and_overlapping_on_intervals_are_unioned():
    result = calculate_exposure([period("00", "03", id="a"), period("00", "03", id="b"), period("02", "05", id="c")], START, as_of="2026-01-01T06:00:00Z", source="fdc", coverage_intervals=[period("00", "06")])
    assert result["hours"] == 5
    assert result["completeness"] == 1
    assert result["observed_window_hours"] == 6


def test_rf_on_time_is_not_monitoring_completeness():
    result = calculate_exposure([period("00", "01")], START, as_of="2026-01-01T10:00:00Z", source="fdc")
    assert result["hours"] == 1
    assert result["completeness"] is None
    assert result["confidence"] == "unknown"
    result = calculate_exposure([period("00", "01")], START, as_of="2026-01-01T10:00:00Z", source="fdc", coverage_intervals=[period("00", "05")])
    assert result["completeness"] == .5
    assert "lower bound" in " ".join(result["issues"])


def test_exposure_across_midnight_and_dimension_source_filtering():
    raw = [{"start": "2026-01-01T23:00:00Z", "end": "2026-01-02T02:00:00Z", "source": "rf_primary", "dimension": "rf_hours"}, {"start": "2026-01-01T23:00:00Z", "end": "2026-01-02T02:00:00Z", "source": "rf_secondary", "dimension": "rf_hours"}]
    with pytest.raises(ValueError, match="unrelated RF sources"):
        calculate_exposure(raw, "2026-01-01T22:00:00Z", as_of="2026-01-02T03:00:00Z")
    result = calculate_exposure(raw, "2026-01-02T00:00:00Z", as_of="2026-01-02T01:00:00Z", source="rf_primary")
    assert result["hours"] == 1


def test_component_moves_preserve_lifetime_and_reset_refurbishment_usage():
    installations = [{"id": "i1", "chamber_id": "a", "installed_at": START, "removed_at": "2026-01-01T03:00:00Z"}, {"id": "i2", "chamber_id": "b", "installed_at": "2026-01-01T05:00:00Z", "removed_at": None}]
    raw = [period("00", "10", chamber_id="a"), period("00", "10", chamber_id="b")]
    result = component_exposure(raw, installations, "2026-01-01T10:00:00Z", source="fdc", refurbished_at="2026-01-01T04:00:00Z", coverage_intervals=[period("00", "10", chamber_id="a"), period("00", "10", chamber_id="b")])
    assert result["hours"] == 5
    assert result["lifetime_hours"] == 8
    assert result["since_refurbishment"] == 5
    installations[0]["removed_at"] = "2026-01-01T06:00:00Z"
    with pytest.raises(ValueError, match="overlapping installations"):
        component_exposure(raw, installations, "2026-01-01T10:00:00Z", source="fdc")


def test_lifetime_completeness_preserves_old_missing_data():
    installs = [{"installed_at": START, "removed_at": "2026-01-01T02:00:00Z"}, {"installed_at": "2026-01-01T03:00:00Z", "removed_at": None}]
    result = component_exposure([period("00", "05")], installs, "2026-01-01T05:00:00Z", source="fdc", coverage_intervals=[period("03", "05")])
    assert result["completeness"] == 1
    assert result["lifetime_completeness"] == .5
    assert result["confidence"] == "limited"


def test_mechanical_cycle_events_not_assumed_rf_exposure():
    events = [{"id": "e", "at": "2026-01-01T01:00:00Z", "value": 7, "source": "fdc", "dimension": "mechanical_cycles"}]
    result = calculate_exposure(events * 2, START, as_of="2026-01-01T02:00:00Z", source="fdc", dimension="mechanical_cycles")
    assert result["hours"] == 7
    assert result["unit"] == "cycles"
    assert calculate_exposure(events, START, as_of="2026-01-01T02:00:00Z", source="fdc", dimension="rf_hours")["hours"] == 0


def test_counter_reset_missing_samples_and_duplicate_timestamps():
    samples = [sample("00", 10), sample("01", 11), sample("01", 11), sample("02", 0, reset=True), sample("03", 1), sample("10", 8)]
    result = counter_intervals(samples, source="fdc", max_gap_hours=2)
    assert sum(r["value"] for r in result["intervals"]) == 2
    assert len(result["intervals"]) == 2
    assert any("reset" in issue for issue in result["issues"])
    assert any("Missing samples" in issue for issue in result["issues"])
    assert result["original_samples"] == samples


def test_explicit_reset_even_when_counter_is_larger_than_previous():
    result = counter_intervals([sample("00", 1), sample("03", 2, reset=True, reset_at="2026-01-01T01:00:00Z", reset_baseline=0)], source="fdc")
    assert result["intervals"][0]["value"] == 2
    assert result["intervals"][0]["start"] == "2026-01-01T01:00:00+00:00"
    assert "before the known reset" in result["issues"][0]


def test_rollover_requires_declared_modulus_and_plausible_increment():
    samples = [sample("00", 99), sample("02", 1)]
    rolled = counter_intervals(samples, source="fdc", rollover=100)
    assert rolled["intervals"][0]["value"] == 2
    assert rolled["intervals"][0]["method"] == "declared_rollover"
    assert counter_intervals(samples, source="fdc")["intervals"] == []
    assert counter_intervals([sample("00", 80), sample("01", 5)], source="fdc", rollover=100)["intervals"] == []


def test_timestamp_conflicts_do_not_bridge_to_create_counter_exposure():
    result = counter_intervals([sample("00", 0), sample("01", 1), sample("01", .5), sample("02", 2)], source="fdc")
    assert result["intervals"] == []
    assert "Conflicting" in result["issues"][0]


def test_counter_delta_not_prorated_across_component_replacement():
    result = calculate_exposure([period("00", "04", value=2)], "2026-01-01T02:00:00Z", as_of="2026-01-01T05:00:00Z", source="fdc")
    assert result["hours"] == 0
    assert any("unallocated" in issue for issue in result["issues"])


def test_conflicting_counter_intervals_are_excluded_order_independently():
    raw = [period("00", "02", id="one", value=1), period("01", "03", id="two", value=2)]
    for rows in (raw, list(reversed(raw))):
        result = calculate_exposure(rows, START, as_of="2026-01-01T04:00:00Z", source="fdc")
        assert result["hours"] == 0
        assert any("Conflicting" in issue for issue in result["issues"])


def test_pm_policy_evidence_and_dimension_boundaries():
    exposure = {"hours": 90, "dimension": "rf_hours", "unit": "RF h", "completeness": 1, "calendar_days": 35}
    policy = {"threshold": 100, "basis": "synthetic_engineer_recommendation", "dimension": "rf_hours"}
    assert evaluate_pm(exposure, policy)["status"] == "upcoming"
    assert evaluate_pm({**exposure, "hours": 110}, policy)["remaining"] == -10
    assert evaluate_pm({**exposure, "hours": 110, "completeness": .5}, policy)["status"] == "overdue"
    assert evaluate_pm({**exposure, "completeness": .5}, policy)["status"] == "unknown"
    assert evaluate_pm(exposure, None)["status"] == "unknown"
    assert evaluate_pm(exposure, {**policy, "dimension": "mechanical_cycles"})["status"] == "unknown"
    assert evaluate_pm(exposure, {"calendar_days": 30, "basis": "synthetic_engineer_recommendation"})["status"] == "overdue"


def test_disputed_identity_cannot_establish_overdue_pm():
    exposure = {"dimension": "rf_hours", "hours": 120, "unit": "RF h", "completeness": 1.0, "confidence": "limited", "attribution_status": "disputed"}
    policy = {"threshold": 100, "dimension": "rf_hours", "basis": "synthetic_engineer_recommendation", "unit": "RF h"}
    result = evaluate_pm(exposure, policy)
    assert result["status"] == "unknown"
    assert result["percent_consumed"] == 120
    assert "disputed" in result["message"]


def test_poisson_exact_known_confidence_intervals_and_zero_failures():
    result = poisson_rate(5, 1000)
    assert result["rate_per_1000_hours"] == 5
    assert result["lower"] == pytest.approx(1.62348639, abs=1e-7)
    assert result["upper"] == pytest.approx(11.66833208, abs=1e-7)
    zero = poisson_rate(0, 1000)
    assert zero["lower"] == 0
    assert zero["upper"] == pytest.approx(3.68887945)
    for count, exposure in [(-1, 100), (1, 0), (1.5, 10)]:
        with pytest.raises(ValueError):
            poisson_rate(count, exposure)


def test_kaplan_meier_censored_lifetimes_and_tied_event_censoring():
    result = kaplan_meier([{"time": 10, "event": True}, {"time": 10, "event": False}, {"time": 20, "event": True}, {"time": 30, "event": False}])
    assert result[1]["at_risk"] == 4
    assert result[1]["survival"] == .75
    assert result[2]["at_risk"] == 2
    assert result[2]["survival"] == .375
    assert result[-1]["survival"] == .375
    assert result[-1]["censored"] == 1
    assert all(r["lower"] <= r["survival"] <= r["upper"] for r in result)
    assert kaplan_meier([{"time": 10, "event": False}])[-1]["survival"] == 1


def test_weibull_gates_and_right_censored_likelihood():
    assert not weibull_fit([{"time": 50, "event": True}])["eligible"]
    observations = [{"time": t, "event": True} for t in (100, 200, 300, 400, 500)] + [{"time": t, "event": False} for t in (500, 600, 700, 800, 900)]
    result = weibull_fit(observations)
    assert result["eligible"]
    assert result["scale"] > 400
    assert result["shape"] > 0
    assert result["confidence_interval"] is None


def test_revision_rates_keep_part_families_separate_and_use_operating_exposure():
    result = revision_rates([{"part_number": "A", "revision": "R1", "exposure_hours": 100, "failures": 1}, {"part_number": "A", "revision": "R1", "exposure_hours": 300, "failures": 0}, {"part_number": "B", "revision": "R1", "exposure_hours": 1000, "failures": 0}])
    assert len(result) == 2
    assert result[0]["rate_per_1000_hours"] == 2.5
    assert result[0]["components"] == 2


def test_downtime_union_and_exclusive_attribution_never_double_counts():
    records = [{**period("00", "04"), "id": "d1", "tool_id": "tool1", "component_id": "part1", "subsystem": "RF", "attribution_status": "confirmed", "weight": 1, "category": "active_repair"}, {**period("02", "06"), "id": "d2", "tool_id": "tool1", "component_id": "part1", "subsystem": "RF", "attribution_status": "confirmed", "weight": 1, "category": "active_repair"}]
    result = downtime_summary(records + records)
    assert result["total_hours"] == 6
    assert result["by_component"]["part1"] == 6
    assert result["by_category"]["active_repair"] == 6
    other_tool = {**records[0], "tool_id": "tool2"}
    assert downtime_summary(records + [other_tool])["total_hours"] == 10


def test_multiple_component_allocations_share_one_downtime_without_loss():
    common = {**period("00", "10"), "id": "same-original-downtime", "tool_id": "t", "attribution_status": "confirmed", "category": "active_repair"}
    result = downtime_summary([{**common, "component_id": "a", "subsystem": "RF", "weight": .6}, {**common, "component_id": "b", "subsystem": "Vacuum", "weight": .4}])
    assert result["total_hours"] == 10
    assert result["by_component"] == {"a": 6, "b": 4}
    assert result["unattributed_hours"] == 0


def test_excess_attribution_is_unresolved_not_normalized_silently():
    common = {**period("00", "02"), "tool_id": "t", "attribution_status": "confirmed", "weight": 1}
    result = downtime_summary([{**common, "id": "a", "component_id": "a"}, {**common, "id": "b", "component_id": "b"}])
    assert result["total_hours"] == 2
    assert result["attributed_hours"] == 0
    assert result["unattributed_hours"] == 2
    assert result["conflicts"]


def test_episode_dedup_requires_explicit_shared_identity_not_alarm_proximity():
    records = [{"id": "one", "source": "mock", "episode_key": "episodeA", "component_id": "part1"}, {"id": "two", "source": "mock", "episode_key": "episodeA", "component_id": "part1"}, {"id": "alarm-only", "source": "mock", "status": "alarm_unconfirmed"}]
    result = deduplicate_episodes(records)
    assert len(result) == 2
    assert result[0]["original_record_ids"] == ["one", "two"]
    assert result[1]["status"] == "alarm_unconfirmed"
    assert len(deduplicate_episodes([{"id": "a", "episode_key": None}, {"id": "b", "episode_key": None}])) == 2


def test_uncertain_measurements_cannot_become_ok_pm_or_statistical_prediction():
    exposure = {"hours": 5, "dimension": "rf_hours", "completeness": 1, "confidence": "limited", "issues": ["Conflicting counter intervals excluded"]}
    assert evaluate_pm(exposure, {"threshold": 100, "basis": "synthetic_engineer_recommendation"})["status"] == "unknown"
    rows = [{"time": 100 + i, "event": i < 5} for i in range(12)]
    assert not component_forecast(exposure, None, rows)["eligible"]


def test_counter_metadata_conflicts_and_different_sources_do_not_blend():
    samples = [sample("00", 0), sample("01", 1), sample("01", 1, reset=True), sample("02", 2)]
    assert counter_intervals(samples, source="fdc")["intervals"] == []
    with pytest.raises(ValueError, match="selected measurement source"):
        counter_intervals([sample("00", 0, source="other")], source="fdc")


def test_forecast_unavailable_without_comparable_failure_evidence():
    result = component_forecast({"hours": 90, "dimension": "rf_hours", "completeness": 1}, {"threshold": 100}, [{"time": 100, "event": False}])
    assert result["state"] == "rules_based_pm"
    assert not result["eligible"]
    assert result["message"] == INSUFFICIENT
    assert result["horizons"] == []


def test_synthetic_prediction_uses_censored_exposure_and_is_never_state_c():
    result = synthetic_demo_forecast((100,))
    assert result["synthetic"]
    assert result["state"] == "statistical_estimate"
    assert result["model_version"]
    assert result["evidence"]["right_censored"] == 7
    expected = 1 - exp(-5 / result["evidence"]["exposure_hours"] * 100)
    assert result["horizons"][0]["probability"] == pytest.approx(expected)
    assert result["horizons"][0]["lower"] < expected < result["horizons"][0]["upper"]
    assert not result["validated_predictive_model_available"]
    assert result["remaining_useful_life"] is None


def test_leakage_prevention_rejects_group_overlap_future_features_and_labels():
    train = [{"tool_id": "toolA", "prediction_at": "2025-01-01T00:00:00Z", "feature_at": "2025-01-01T00:00:00Z", "label_observed_at": "2025-02-01T00:00:00Z"}]
    valid = [{"tool_id": "toolB", "prediction_at": "2025-04-01T00:00:00Z", "feature_at": "2025-04-01T00:00:00Z", "label_observed_at": "2025-05-01T00:00:00Z"}]
    cutoff = "2025-03-01T00:00:00Z"
    validate_split(train, valid, cutoff=cutoff)
    with pytest.raises(ValueError, match="group leakage"):
        validate_split(train, [{**valid[0], "tool_id": "toolA"}], cutoff=cutoff)
    with pytest.raises(ValueError, match="Future-data leakage"):
        validate_split([{**train[0], "feature_at": "2025-01-02T00:00:00Z"}], valid, cutoff=cutoff)
    with pytest.raises(ValueError, match="Training label"):
        validate_split([{**train[0], "label_observed_at": "2025-06-01T00:00:00Z"}], valid, cutoff=cutoff)


def test_repair_duration_distribution_is_distinct_from_total_downtime():
    assert repair_statistics([1, 2, 6])["mean_hours"] == 3
    assert repair_statistics([])["mean_hours"] is None
