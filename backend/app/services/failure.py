"""Failure episode grouping and exclusive downtime accounting.

Alarms are symptoms, not failures. Deduplication only merges observations with an
explicit shared episode key; proximity in time is never proof of common cause.
"""
from __future__ import annotations

from collections import defaultdict
from math import isfinite
from typing import Any, Mapping, Sequence

from .exposure import timestamp, union_hours


def deduplicate_episodes(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    episodes: dict[tuple[str, str], dict[str, Any]] = {}
    for index, record in enumerate(records):
        key = (str(record.get("source", "unknown")), str(record.get("episode_key") or record.get("source_id") or record.get("id") or index))
        if key not in episodes:
            episodes[key] = {**record, "original_record_ids": [record.get("id", index)]}
        else:
            episode = episodes[key]
            episode["original_record_ids"].append(record.get("id", index))
            if episode.get("component_id") != record.get("component_id"):
                episode["attribution_status"] = "conflict"
                episode["requires_adjudication"] = True
    return list(episodes.values())


def downtime_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Union by tool; overlapping component allocations cannot exceed wall time.

    For each elementary segment, adjudicated allocation weights must total <= 1.
    Unresolved/conflicting allocations are retained as unattributed. Categories
    with conflicting overlaps are separately reported as 'classification_conflict'.
    Fleet total is tool-hours, not an across-tools union of calendar time.
    """
    per_tool: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[Any, ...]] = set()
    for index, row in enumerate(records):
        start, end = timestamp(row["start"]), timestamp(row["end"])
        if end <= start:
            raise ValueError("Downtime end must follow start")
        weight = float(row.get("weight", 1.0))
        if not isfinite(weight) or not 0 <= weight <= 1:
            raise ValueError("Downtime attribution weights must be between 0 and 1")
        key = (row.get("id", row.get("source_id", index)), row.get("tool_id", "unknown"), start, end, row.get("component_id"), weight, row.get("subsystem"), row.get("attribution_status"), row.get("category"))
        if key in seen:
            continue
        seen.add(key)
        per_tool[str(row.get("tool_id", "unknown"))].append({**row, "start": start, "end": end, "weight": weight})
    total, attributed, unattributed = 0.0, 0.0, 0.0
    by_subsystem: dict[str, float] = defaultdict(float)
    by_component: dict[str, float] = defaultdict(float)
    by_category: dict[str, float] = defaultdict(float)
    conflicts: list[dict[str, Any]] = []
    tool_totals: dict[str, float] = {}
    for tool, rows in per_tool.items():
        tool_totals[tool] = union_hours((r["start"], r["end"]) for r in rows)
        total += tool_totals[tool]
        boundaries = sorted({value for r in rows for value in (r["start"], r["end"])})
        for start, end in zip(boundaries, boundaries[1:]):
            active = [r for r in rows if r["start"] < end and r["end"] > start]
            if not active:
                continue
            hours = (end - start).total_seconds() / 3600
            categories = {str(r.get("category", "unknown")) for r in active}
            category = next(iter(categories)) if len(categories) == 1 else "classification_conflict"
            by_category[category] += hours
            # A repeated downtime observation for the same component should not
            # create repeated credit; conflicting weights force adjudication.
            allocation: dict[str, tuple[float, str]] = {}
            inconsistent = False
            for r in active:
                if r.get("attribution_status") not in {"confirmed", "adjudicated"} or not r.get("component_id"):
                    continue
                component = str(r["component_id"])
                entry = (r["weight"], str(r.get("subsystem", "unknown")))
                if component in allocation and allocation[component] != entry:
                    inconsistent = True
                allocation[component] = entry
            weight_sum = sum(w for w, _ in allocation.values())
            if inconsistent or weight_sum > 1 + 1e-9:
                conflicts.append({"tool_id": tool, "start": start.isoformat(), "end": end.isoformat(), "reason": "Conflicting or excessive component attribution weights"})
                unattributed += hours
                continue
            for component, (weight, subsystem) in allocation.items():
                by_component[component] += hours * weight
                by_subsystem[subsystem] += hours * weight
            attributed += hours * weight_sum
            unattributed += hours * max(0.0, 1 - weight_sum)
    if unattributed:
        by_subsystem["Unattributed"] += unattributed
    return {"total_hours": round(total, 6), "attributed_hours": round(attributed, 6), "unattributed_hours": round(unattributed, 6), "by_tool": tool_totals, "by_component": dict(by_component), "by_category": dict(by_category), "downtime_by_subsystem": [{"name": name, "hours": round(hours, 6)} for name, hours in sorted(by_subsystem.items())], "conflicts": conflicts, "unit": "tool h", "classification_note": "Configurable engineering categories; not a certified SEMI E10 implementation", "limitations": ["Union of reported tool impairment intervals; lost throughput and critical-path delay require separate evidence", "Simultaneous category disagreements are retained as classification conflicts"]}
