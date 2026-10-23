"""Exposure-based descriptive reliability statistics, not equipment specifications.

Rates require comparable components and an appropriate physically relevant
denominator. All-cause Kaplan–Meier assumes independent right censoring.
Cause-specific censoring is descriptive and is not a cumulative-incidence model.
"""
from __future__ import annotations

from collections import defaultdict
from math import exp, isfinite, log, sqrt
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.optimize import minimize
from scipy.stats import chi2, norm, weibull_min


def poisson_rate(failures: int, exposure_hours: float, confidence: float = 0.95) -> dict[str, Any]:
    """Exact two-sided Garwood interval, rates expressed per 1,000 exposure h."""
    if isinstance(failures, bool) or int(failures) != failures or failures < 0:
        raise ValueError("Failure count must be a nonnegative integer")
    if not isfinite(exposure_hours) or exposure_hours <= 0:
        raise ValueError("Positive finite component operating exposure is required")
    if not 0 < confidence < 1:
        raise ValueError("Confidence must be between zero and one")
    alpha = 1 - confidence
    lower_count = float(chi2.ppf(alpha / 2, 2 * failures) / 2) if failures else 0.0
    upper_count = float(chi2.ppf(1 - alpha / 2, 2 * (failures + 1)) / 2)
    scale = 1000 / exposure_hours
    return {"failures": int(failures), "exposure_hours": exposure_hours, "rate_per_1000_hours": failures * scale, "lower": lower_count * scale, "upper": upper_count * scale, "confidence": confidence, "method": "exact Poisson Garwood", "unit": "failures / 1,000 component operating h", "assumptions": ["Comparable component cohort", "Constant event rate over operating exposure", "Independent event increments; recurrent events may violate this assumption"]}


def _observations(observations: Sequence[Mapping[str, Any]]) -> list[tuple[float, bool]]:
    values = []
    for record in observations:
        time = float(record["time"])
        if not isfinite(time) or time < 0:
            raise ValueError("Lifetimes must be finite and nonnegative")
        event = record.get("event", False)
        if not isinstance(event, bool) and event not in (0, 1):
            raise ValueError("Event must be a binary observed failure indicator")
        values.append((time, bool(event)))
    return values


def kaplan_meier(observations: Sequence[Mapping[str, Any]], confidence: float = 0.95) -> list[dict[str, Any]]:
    if not 0 < confidence < 1:
        raise ValueError("Confidence must be between zero and one")
    values = _observations(observations)
    if not values:
        return []
    grouped: dict[float, list[bool]] = defaultdict(list)
    for time, event in values:
        grouped[time].append(event)
    at_risk, survival, greenwood = len(values), 1.0, 0.0
    result = [{"time": 0.0, "survival": 1.0, "at_risk": at_risk, "failures": 0, "censored": 0, "lower": 1.0, "upper": 1.0}]
    z = float(norm.ppf(0.5 + confidence / 2))
    for time in sorted(grouped):
        events = sum(grouped[time])
        censored = len(grouped[time]) - events
        survival *= (at_risk - events) / at_risk
        if events and at_risk > events:
            greenwood += events / (at_risk * (at_risk - events))
        if 0 < survival < 1:
            se_loglog = sqrt(greenwood) / abs(log(survival))
            center = log(-log(survival))
            lower = exp(-exp(center + z * se_loglog))
            upper = exp(-exp(center - z * se_loglog))
        else:
            lower = upper = survival
        row = {"time": time, "survival": survival, "at_risk": at_risk, "failures": events, "censored": censored, "lower": lower, "upper": upper}
        if time == 0:
            result[0] = row
        else:
            result.append(row)
        # Failures at a tied time use the risk set before tied censorings leave.
        at_risk -= events + censored
    return result


def weibull_fit(observations: Sequence[Mapping[str, Any]], *, min_failures: int = 5, min_observations: int = 10) -> dict[str, Any]:
    values = _observations(observations)
    events = sum(e for _, e in values)
    unavailable = {"eligible": False, "method": "right-censored two-parameter Weibull MLE", "failures": events, "observations": len(values), "shape": None, "scale": None, "message": "Insufficient comparable failures for a defensible Weibull fit.", "limitations": ["Requires comparable independent lifetimes and independent right censoring", "No OEM life limit or operational recommendation"]}
    if events < min_failures or len(values) < min_observations:
        return unavailable
    if any(t <= 0 for t, _ in values):
        return {**unavailable, "message": "Zero-exposure observations require interval-censoring treatment; fit withheld."}
    times = np.array([t for t, _ in values], dtype=float)
    observed = np.array([e for _, e in values], dtype=bool)
    if len(np.unique(times[observed])) < 3:
        return {**unavailable, "message": "Failure exposure variation is insufficient for a stable Weibull shape."}

    def negative_log_likelihood(log_parameters: np.ndarray) -> float:
        shape, scale = np.exp(log_parameters)
        value = weibull_min.logpdf(times[observed], c=shape, scale=scale).sum() + weibull_min.logsf(times[~observed], c=shape, scale=scale).sum()
        return -float(value) if np.isfinite(value) else 1e100

    fit = minimize(negative_log_likelihood, np.log([1.5, float(np.median(times))]), method="L-BFGS-B", bounds=[(log(0.05), log(30)), (log(float(times.min()) / 100), log(float(times.max()) * 100))])
    if not fit.success or not isfinite(float(fit.fun)):
        return {**unavailable, "message": "Censored-likelihood optimizer did not converge; fit withheld."}
    shape, scale = np.exp(fit.x)
    if shape <= 0.0501 or shape >= 29.99:
        return {**unavailable, "message": "Weibull solution reached a shape boundary; fit withheld."}
    return {**unavailable, "eligible": True, "shape": float(shape), "scale": float(scale), "message": "Exploratory cohort fit; independently validate before prediction.", "log_likelihood": -float(fit.fun), "unit": "component operating h", "confidence_interval": None, "limitations": unavailable["limitations"] + ["No parameter uncertainty interval computed; do not use for individual operational decisions"]}


def revision_rates(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Sum component exposure, never tool calendar age; events must be adjudicated."""
    cohorts: dict[tuple[str, str], dict[str, Any]] = {}
    for row in records:
        key = (str(row.get("part_number", "unknown")), str(row["revision"]))
        cohort = cohorts.setdefault(key, {"revision": key[1], "part_number": key[0], "failures": 0, "exposure_hours": 0.0, "components": 0})
        value = float(row["exposure_hours"])
        failures = row.get("failures", 0)
        if not isfinite(value) or value < 0 or int(failures) != failures or failures < 0:
            raise ValueError("Invalid component cohort observation")
        cohort["exposure_hours"] += value
        cohort["failures"] += int(failures)
        cohort["components"] += 1
    result = []
    for cohort in cohorts.values():
        if cohort["exposure_hours"] > 0:
            result.append({**cohort, **poisson_rate(cohort["failures"], cohort["exposure_hours"])})
        else:
            result.append({**cohort, "rate_per_1000_hours": None, "lower": None, "upper": None})
    return result


def repair_statistics(durations_hours: Sequence[float]) -> dict[str, Any]:
    values = np.array(durations_hours, dtype=float)
    if np.any(~np.isfinite(values)) or np.any(values < 0):
        raise ValueError("Repair durations must be finite and nonnegative")
    return {"count": len(values), "mean_hours": float(values.mean()) if len(values) else None, "median_hours": float(np.median(values)) if len(values) else None, "p90_hours": float(np.quantile(values, 0.9)) if len(values) else None, "unit": "active repair h"}
