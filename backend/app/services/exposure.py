"""Source-specific exposure attribution with half-open installation intervals.

RF-on records describe observed ON time, not monitoring coverage. Coverage is a
separate observation interval covering both ON and OFF states. Missing intervals
are never extrapolated. Counter deltas are not prorated across a replacement.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any, Iterable, Mapping, Sequence

UTC = timezone.utc
HOUR_DIMENSIONS = {"rf_hours", "powered_hours", "operating_hours", "calendar_hours"}
UNITS = {"rf_hours": "RF h", "powered_hours": "powered h", "operating_hours": "operating h", "calendar_hours": "h", "process_cycles": "cycles", "mechanical_cycles": "cycles", "thermal_cycles": "cycles", "wafers": "wafers", "lots": "lots"}


def timestamp(value: datetime | str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if not isinstance(result, datetime):
        raise ValueError("A timestamp is required")
    # SQLite DateTime values lose tzinfo; all persisted application times are UTC.
    return result.replace(tzinfo=UTC) if result.tzinfo is None else result.astimezone(UTC)


def merge_intervals(intervals: Iterable[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    ordered = sorted((s, e) for s, e in intervals if s < e)
    merged: list[tuple[datetime, datetime]] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def union_hours(intervals: Iterable[tuple[datetime, datetime]]) -> float:
    return sum((e - s).total_seconds() / 3600 for s, e in merge_intervals(intervals))


def calculate_exposure(
    intervals: Sequence[Mapping[str, Any]],
    installed_at: datetime | str,
    removed_at: datetime | str | None = None,
    *,
    as_of: datetime | str | None = None,
    dimension: str = "rf_hours",
    source: str | None = None,
    coverage_intervals: Sequence[Mapping[str, Any]] | None = None,
    refurbished_at: datetime | str | None = None,
) -> dict[str, Any]:
    start = timestamp(installed_at)
    requested_end = timestamp(as_of) if as_of else datetime.now(UTC)
    end = min(timestamp(removed_at), requested_end) if removed_at else requested_end
    if end < start:
        raise ValueError("Exposure window ends before installation")
    if source is None:
        sources = {str(r.get("source", "unknown")) for r in intervals if r.get("dimension", "rf_hours") == dimension}
        if len(sources) > 1:
            raise ValueError("Select one applicable exposure source; unrelated RF sources cannot be summed")
        source = next(iter(sources), "unknown")
    issues: list[str] = []
    derivation: list[dict[str, Any]] = []
    durations: list[tuple[datetime, datetime]] = []
    weighted: list[tuple[datetime, datetime, float, str]] = []
    events: dict[tuple[str, str], float] = {}
    good_records: list[Mapping[str, Any]] = []
    for index, record in enumerate(intervals):
        if record.get("dimension", "rf_hours") != dimension or record.get("source", "unknown") != source:
            continue
        record_id = str(record.get("id", index))
        if record.get("quality", "good") not in {"good", "verified", "synthetic", "complete"}:
            issues.append(f"Record {record_id}: excluded quality={record.get('quality')}")
            continue
        if "at" in record:
            at = timestamp(record["at"])
            if start <= at < end:
                value = float(record.get("value", 1))
                if not isfinite(value) or value < 0:
                    raise ValueError("Exposure increments must be finite and nonnegative")
                key = (record_id, at.isoformat())
                if key in events and events[key] != value:
                    raise ValueError("Conflicting values for an exposure event")
                events[key] = value
                good_records.append(record)
                derivation.append({"source_record_id": record_id, "at": at.isoformat(), "increment": value})
            continue
        rs, re = timestamp(record["start"]), timestamp(record["end"])
        if re <= rs:
            issues.append(f"Record {record_id}: invalid or reversed interval excluded")
            continue
        clipped_start, clipped_end = max(start, rs), min(end, re)
        if clipped_start >= clipped_end:
            continue
        if "value" in record:
            increment = float(record["value"])
            if not isfinite(increment) or increment < 0:
                raise ValueError("Exposure increments must be finite and nonnegative")
            if clipped_start != rs or clipped_end != re:
                issues.append(f"Record {record_id}: counter interval crosses an installation/as-of boundary; increment unallocated")
                continue
            if any(rs == s and re == e and increment == v for s, e, v, _ in weighted):
                continue
            weighted.append((rs, re, increment, record_id))
            derivation.append({"source_record_id": record_id, "start": rs.isoformat(), "end": re.isoformat(), "increment": increment, "method": "observed_counter_delta"})
        elif dimension in HOUR_DIMENSIONS:
            durations.append((clipped_start, clipped_end))
            derivation.append({"source_record_id": record_id, "start": clipped_start.isoformat(), "end": clipped_end.isoformat(), "method": "state_interval_union"})
        else:
            issues.append(f"Record {record_id}: {dimension} requires a measured increment, not elapsed time")
            continue
        good_records.append(record)
    conflicts = {i for i, (s, e, _, _) in enumerate(weighted) for j, (s2, e2, _, _) in enumerate(weighted) if i != j and s < e2 and e > s2}
    if conflicts:
        issues.append("Conflicting overlapping counter increments excluded pending reconciliation")
        conflicted_ids = {weighted[i][3] for i in conflicts}
        weighted = [r for i, r in enumerate(weighted) if i not in conflicts]
        derivation = [r for r in derivation if r["source_record_id"] not in conflicted_ids]
    if durations and weighted:
        raise ValueError("Choose state reconstruction or cumulative counter derivation, not both")
    value = union_hours(durations) + sum(v for _, _, v, _ in weighted) + sum(events.values())
    coverage: list[tuple[datetime, datetime]] = []
    for record in coverage_intervals or []:
        if record.get("source", source) != source or record.get("quality", "good") not in {"good", "verified", "synthetic", "complete"}:
            continue
        cs, ce = max(start, timestamp(record["start"])), min(end, timestamp(record["end"]))
        if cs < ce:
            coverage.append((cs, ce))
    window_hours = (end - start).total_seconds() / 3600
    completeness = min(1.0, union_hours(coverage) / window_hours) if coverage_intervals is not None and window_hours else (1.0 if window_hours == 0 else None)
    if completeness is None:
        issues.append("Monitoring coverage unavailable; RF utilization is not evidence of completeness")
    elif completeness < 0.999999:
        issues.append("Incomplete monitoring coverage; accumulated exposure is an observed lower bound")
    since_refurbishment = value
    if refurbished_at and timestamp(refurbished_at) > start:
        ref = timestamp(refurbished_at)
        since_refurbishment = 0.0 if ref >= end else calculate_exposure(
            intervals, ref, end, as_of=end, dimension=dimension, source=source,
            coverage_intervals=coverage_intervals,
        )["hours"]
    return {
        "dimension": dimension, "unit": UNITS.get(dimension, dimension),
        "hours": round(value, 6), "value": round(value, 6),
        "lifetime_hours": round(value, 6), "since_refurbishment": round(since_refurbishment, 6),
        "completeness": round(completeness, 6) if completeness is not None else None,
        "confidence": "complete" if completeness == 1.0 and not issues else "limited" if completeness is not None else "unknown",
        "source": source, "issues": list(dict.fromkeys(issues)), "derivation": derivation,
        "observed_window_hours": round(window_hours, 6),
        "calendar_days": round(window_hours / 24, 6),
    }


def component_exposure(
    intervals: Sequence[Mapping[str, Any]],
    installations: Sequence[Mapping[str, Any]],
    as_of: datetime | str,
    dimension: str = "rf_hours",
    source: str | None = None,
    refurbished_at: datetime | str | None = None,
    coverage_intervals: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Aggregate a serial's disjoint location histories; callers provide all locations.

    Records and histories may carry chamber_id. When present, only records from
    that installation's chamber are attributed. A component may be reinstalled.
    """
    results = []
    sorted_installs = sorted(installations, key=lambda x: timestamp(x["installed_at"]))
    previous_end: datetime | None = None
    for install in sorted_installs:
        begins = timestamp(install["installed_at"])
        if begins > timestamp(as_of):
            continue
        ends = min(timestamp(install["removed_at"]), timestamp(as_of)) if install.get("removed_at") else timestamp(as_of)
        if previous_end is not None and begins < previous_end:
            raise ValueError("Serialized component has overlapping installations")
        previous_end = ends
        chamber_id = install.get("chamber_id")
        local_records = [r for r in intervals if chamber_id is None or r.get("chamber_id", chamber_id) == chamber_id]
        local_coverage = None if coverage_intervals is None else [r for r in coverage_intervals if chamber_id is None or r.get("chamber_id", chamber_id) == chamber_id]
        result = calculate_exposure(local_records, begins, ends, as_of=as_of, dimension=dimension, source=source, coverage_intervals=local_coverage, refurbished_at=refurbished_at)
        result["installation_id"] = install.get("id")
        results.append(result)
    if not results:
        return {"dimension": dimension, "unit": UNITS.get(dimension, dimension), "hours": 0.0, "value": 0.0, "lifetime_hours": 0.0, "since_refurbishment": 0.0, "completeness": None, "confidence": "unknown", "source": source, "issues": ["No eligible installation history"], "installations": []}
    latest = results[-1].copy()
    latest["lifetime_hours"] = round(sum(r["hours"] for r in results), 6)
    latest["since_refurbishment"] = round(sum(r["since_refurbishment"] for r in results), 6)
    latest["installations"] = results
    latest["issues"] = list(dict.fromkeys(issue for r in results for issue in r["issues"]))
    windows = sum(r["observed_window_hours"] for r in results)
    latest["lifetime_completeness"] = round(sum(r["observed_window_hours"] * r["completeness"] for r in results) / windows, 6) if windows and all(r["completeness"] is not None for r in results) else None
    latest["lifetime_confidence"] = "complete" if all(r["confidence"] == "complete" for r in results) else "limited"
    if latest["lifetime_confidence"] != "complete":
        latest["confidence"] = "limited"
    return latest


def counter_intervals(
    samples: Sequence[Mapping[str, Any]], *, source: str, dimension: str = "rf_hours",
    max_gap_hours: float = 24, rollover: float | None = None, max_rate: float = 1.0,
) -> dict[str, Any]:
    """Convert measured cumulative counters to auditable, non-extrapolated deltas.

    A reset without a known timestamp/baseline loses that interval. A configured
    rollover is accepted only if its increment is physically plausible.
    """
    if max_gap_hours <= 0 or max_rate <= 0 or (rollover is not None and rollover <= 0):
        raise ValueError("Counter policy parameters must be positive")
    grouped: dict[datetime, list[Mapping[str, Any]]] = {}
    for sample in samples:
        if sample.get("source", source) != source or sample.get("dimension", dimension) != dimension:
            raise ValueError("Counter samples must share the selected measurement source and dimension")
        value = float(sample["value"])
        if not isfinite(value) or value < 0 or (rollover is not None and value >= rollover):
            raise ValueError("Invalid cumulative counter sample")
        grouped.setdefault(timestamp(sample["at"]), []).append(sample)
    ordered = sorted(grouped)
    issues: list[str] = []
    increments: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []

    def sample_signature(sample: Mapping[str, Any]) -> tuple[Any, ...]:
        return (float(sample["value"]), bool(sample.get("reset", False)), str(sample.get("reset_at")), sample.get("reset_baseline"))

    for at in ordered:
        if len({sample_signature(s) for s in grouped[at]}) > 1:
            issues.append(f"Conflicting samples at {at.isoformat()}; adjacent deltas excluded")
    for previous_at, current_at in zip(ordered, ordered[1:]):
        previous, current = grouped[previous_at], grouped[current_at]
        if any(len({sample_signature(s) for s in values}) != 1 for values in (previous, current)):
            continue
        p, c = previous[0], current[0]
        gap = (current_at - previous_at).total_seconds() / 3600
        if gap > max_gap_hours:
            issues.append(f"Missing samples between {previous_at.isoformat()} and {current_at.isoformat()}; interval unallocated")
            continue
        delta = float(c["value"]) - float(p["value"])
        method = "counter_delta"
        interval_start = previous_at
        if c.get("reset", False) or c.get("reset_at") is not None:
            if c.get("reset_at") is not None:
                reset_at = timestamp(c["reset_at"])
                baseline = c.get("reset_baseline")
                if not previous_at <= reset_at < current_at or baseline is None or not isfinite(float(baseline)) or float(baseline) < 0:
                    issues.append("Counter reset lacks a valid timestamp and baseline; interval excluded")
                    continue
                interval_start = reset_at
                delta = float(c["value"]) - float(baseline)
                method = "known_reset_postreset_only"
                issues.append("Exposure before the known reset is unallocated")
            else:
                issues.append(f"Counter reset between {previous_at.isoformat()} and {current_at.isoformat()}; interval excluded")
                continue
        elif delta < 0:
            if rollover is not None:
                delta += rollover
                method = "declared_rollover"
            else:
                issues.append(f"Counter reset between {previous_at.isoformat()} and {current_at.isoformat()}; interval excluded")
                continue
        available = (current_at - interval_start).total_seconds() / 3600
        if delta < 0 or delta > available * max_rate + 1e-9:
            issues.append(f"Implausible counter increment ending {current_at.isoformat()}; excluded")
            continue
        increments.append({"id": f"counter:{p.get('id', previous_at.isoformat())}:{c.get('id', current_at.isoformat())}", "start": interval_start.isoformat(), "end": current_at.isoformat(), "value": delta, "source": source, "dimension": dimension, "quality": "good", "method": method, "source_record_ids": [p.get("id"), c.get("id")]})
        coverage.append({"start": interval_start.isoformat(), "end": current_at.isoformat(), "source": source})
    return {"intervals": increments, "coverage_intervals": coverage, "issues": issues, "original_samples": [dict(s) for s in samples]}


exposure_from_counters = counter_intervals
