"""Conservative component-level forecasting extension point.

Only the synthetic exponential-rate demonstration is implemented. It is State B,
not a physically validated FDC model. State C requires a separate approved model
implementation and independent validation; a request flag cannot activate it.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite
from typing import Any, Mapping, Protocol, Sequence

from .exposure import timestamp
from .reliability import poisson_rate

INSUFFICIENT = "Insufficient evidence for reliable failure prediction."
DEMO_MODEL_VERSION = "synthetic-exponential-cohort-v1"


@dataclass(frozen=True)
class ModelValidation:
    model_version: str
    held_out_groups: tuple[str, ...]
    calibration_error: float | None
    false_alert_rate: float | None
    median_warning_lead_hours: float | None
    independent_review_reference: str | None
    physically_justified: bool = False
    shadow_mode: bool = True


class ComponentPredictor(Protocol):
    model_version: str

    def predict(self, component: Mapping[str, Any], horizons: Sequence[float]) -> dict[str, Any]:
        """Produce calibrated risks only for an eligible component/cohort."""
        ...


def validate_split(
    training: Sequence[Mapping[str, Any]], validation: Sequence[Mapping[str, Any]], *, cutoff: str,
    group_key: str = "tool_id",
) -> None:
    """Reject group leakage, labels not yet observed, or future-dated features.

    Every row must explicitly identify its prediction origin, latest feature
    timestamp, and label observation timestamp. Outcomes are not feature inputs.
    The caller must additionally enforce revision/operating-state comparability.
    """
    cut = timestamp(cutoff)
    if not training or not validation:
        raise ValueError("A nonempty training and independent validation set is required")
    train_groups = {str(r[group_key]) for r in training}
    validation_groups = {str(r[group_key]) for r in validation}
    if train_groups & validation_groups:
        raise ValueError("Tool/campaign group leakage between training and validation")
    if any(not r.get(group_key) for r in [*training, *validation]):
        raise ValueError("Validation group identity is required")
    for kind, rows in (("training", training), ("validation", validation)):
        for row in rows:
            origin = timestamp(row["prediction_at"])
            feature_time = timestamp(row["feature_at"])
            label_time = timestamp(row["label_observed_at"])
            if feature_time > origin:
                raise ValueError("Future-data leakage: feature occurs after prediction origin")
            if label_time < origin:
                raise ValueError("Outcome precedes the stated prediction origin")
            if kind == "training" and (label_time > cut or origin > cut):
                raise ValueError("Training label was not available at the training cutoff")
            if kind == "validation" and origin <= cut:
                raise ValueError("Validation prediction origin must follow the training cutoff")


def component_forecast(
    exposure: Mapping[str, Any],
    pm: Mapping[str, Any] | None,
    observations: Sequence[Mapping[str, Any]] | None = None,
    *, synthetic: bool = True,
    horizons: Sequence[float] = (100, 500, 1000),
    comparable: bool = True,
    min_failures: int = 5,
    min_observations: int = 10,
    component_id: str | None = None,
    validation: ModelValidation | None = None,
) -> dict[str, Any]:
    """Forecast a single component using an eligible, explicitly synthetic cohort.

    A constant-rate model has no age effect. It uses total component operating
    exposure including right-censored observations, not only failed lifetimes.
    Forecasts are withheld when incomplete measurements or a small cohort make
    even this demonstration inappropriate. No remaining-useful-life is claimed.
    """
    if any(not isfinite(float(h)) or h <= 0 for h in horizons):
        raise ValueError("Exposure horizons must be positive and finite")
    base: dict[str, Any] = {"state": "rules_based_pm" if pm and pm.get("threshold") else "unavailable", "label": "State A · Rules-based PM" if pm and pm.get("threshold") else "Prediction unavailable", "eligible": False, "message": INSUFFICIENT, "component_id": component_id, "model_version": None, "horizons": [], "synthetic": synthetic, "remaining_useful_life": None, "limitations": ["PM threshold proximity is not a failure probability", "No validated predictive health model is connected", "No automatic equipment action"], "validated_predictive_model_available": False}
    if not synthetic:
        base["limitations"].append("Production model registration and independent corporate validation are required")
        return base
    rows = list(observations or [])
    for row in rows:
        if not isfinite(float(row["time"])) or float(row["time"]) < 0 or row.get("event") not in (True, False, 0, 1):
            raise ValueError("Invalid failure/censored lifetime")
    failures = sum(bool(row["event"]) for row in rows)
    total_exposure = sum(float(row["time"]) for row in rows)
    if not comparable or failures < min_failures or len(rows) < min_observations or total_exposure <= 0 or exposure.get("completeness") != 1 or exposure.get("confidence", "complete") != "complete" or exposure.get("issues"):
        base["evidence"] = {"observations": len(rows), "failures": failures, "exposure_hours": total_exposure, "comparable": comparable, "completeness": exposure.get("completeness")}
        return base
    if exposure.get("dimension", "rf_hours") not in {"rf_hours", "powered_hours", "operating_hours"}:
        base["limitations"].append("This demonstration only supports matching operating-hour cohorts")
        return base
    # The caller must form an eligible same-part/revision/condition cohort. An
    # exponential survival likelihood with right censoring has MLE k / sum(t).
    rate = poisson_rate(failures, total_exposure)
    results = []
    for horizon in horizons:
        risk = 1 - exp(-rate["rate_per_1000_hours"] / 1000 * horizon)
        low = 1 - exp(-rate["lower"] / 1000 * horizon)
        high = 1 - exp(-rate["upper"] / 1000 * horizon)
        results.append({"exposure_hours": float(horizon), "horizon": float(horizon), "unit": exposure.get("unit", "RF h"), "probability": risk, "lower": low, "upper": high, "confidence": 0.95, "label": "Synthetic statistical demonstration only"})
    return {**base, "state": "statistical_estimate", "label": "State B · Synthetic statistical estimate", "eligible": True, "message": "Synthetic demonstration only; not validated for any real Flex component.", "model_version": DEMO_MODEL_VERSION, "horizons": results, "evidence": {"observations": len(rows), "failures": failures, "exposure_hours": total_exposure, "right_censored": len(rows) - failures}, "risk_factors": ["Adjudicated failure count in a comparable synthetic cohort", "Component operating exposure includes censored observations"], "limitations": base["limitations"] + ["Homogeneous constant-rate assumption; component age and FDC signatures are not modeled", "Intervals quantify rate sampling uncertainty only, not model misspecification", "Not independently validated or calibrated; false-alert rate and useful lead time unknown", "Shadow-mode educational output; no operational recommendation"]}


def synthetic_demo_forecast(horizons: Sequence[float] = (100, 500, 1000)) -> dict[str, Any]:
    """Deterministic, separate teaching cohort; never merged with fleet failures."""
    observations = [{"time": t, "event": event} for t, event in [(180, True), (240, True), (290, True), (360, True), (420, True), (500, False), (540, False), (600, False), (640, False), (700, False), (740, False), (800, False)]]
    result = component_forecast({"hours": 125, "dimension": "rf_hours", "unit": "RF h", "completeness": 1.0}, None, observations, horizons=horizons, component_id="SYNTHETIC-MODEL-TEACHING-COMPONENT")
    result["dataset"] = "Separate synthetic teaching cohort; not the displayed equipment population"
    return result
