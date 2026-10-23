"""PM policy checks, kept separate from statistical failure estimates."""
from __future__ import annotations

from math import isfinite
from typing import Any, Mapping


def evaluate_pm(exposure: Mapping[str, Any], policy: Mapping[str, Any] | None, *, warning_fraction: float = 0.8) -> dict[str, Any]:
    if not 0 < warning_fraction <= 1:
        raise ValueError("PM warning fraction must be in (0, 1]")
    result: dict[str, Any] = {"status": "unknown", "threshold": None, "remaining": None, "percent_consumed": None, "basis": "unknown", "unit": exposure.get("unit", "unknown"), "message": "No verified specification or configured PM policy."}
    if not policy:
        return result
    result.update({"basis": policy.get("basis", "unknown"), "unit": policy.get("unit", exposure.get("unit", "unknown")), "source": policy.get("source", "user-configured policy"), "document_reference": policy.get("document_reference"), "verification_status": policy.get("verification_status", "unverified")})
    calendar = policy.get("calendar_days")
    threshold = calendar if calendar is not None else policy.get("threshold")
    if threshold is None or not isfinite(float(threshold)) or float(threshold) <= 0 or result["basis"] in {"unknown", ""}:
        return result
    dimension = policy.get("dimension", exposure.get("dimension"))
    if calendar is None and dimension != exposure.get("dimension"):
        result["message"] = "PM policy and exposure dimensions do not match."
        return result
    value = exposure.get("calendar_days") if calendar is not None else exposure.get("hours", exposure.get("value"))
    if value is None or not isfinite(float(value)) or float(value) < 0:
        return result
    if calendar is not None:
        result["unit"] = "days"
    ratio = float(value) / float(threshold)
    complete = calendar is not None or (exposure.get("completeness") == 1.0 and exposure.get("confidence", "complete") == "complete" and not exposure.get("issues"))
    status = "overdue" if ratio >= 1 else "upcoming" if ratio >= warning_fraction else "ok"
    if not complete and ratio < 1:
        status = "unknown"
    result.update({"status": status, "threshold": float(threshold), "remaining": round(float(threshold) - float(value), 6), "percent_consumed": round(100 * ratio, 2), "message": "Configured policy threshold; this is not a failure probability." if complete else "Observed usage is a lower bound; true remaining interval is uncertain.", "dimension": "calendar_days" if calendar is not None else dimension})
    if exposure.get("attribution_status") == "disputed":
        result.update(status="unknown", message="Serialized installation identity is disputed. Provisional usage cannot establish this component's PM disposition.")
    return result
