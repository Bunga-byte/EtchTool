# Reliability and prediction assumptions

## Exposure first

An exposure denominator must match the physical mechanism being studied: RF-on duration, powered duration, calendar age, or a relevant cycle count. Unrelated RF sources must not be added together. The services support explicit dimensions and source selection; the demonstration mainly validates interval-based RF exposure and selected non-RF examples. It does not establish plant-wide coverage for every possible counter.

Installed usage is the overlap of eligible raw operating intervals with an effective-dated installation. Removal ends accrual. Duplicate intervals are unioned. Source observation coverage is separate from RF-on duration so RF-off time is not incorrectly treated as missing measurement. Incomplete observations remain incomplete; no undocumented exposure is extrapolated as fact. Missing counter spans, undeclared resets and conflicting overlaps are withheld with calculation issues and retained source derivation. Counter deltas are never prorated across a replacement or as-of boundary: they cannot be assigned exactly without finer information. Conservative uncertainty is preferable to fabricated precision.

## Statistics

- **Poisson rate:** failures per eligible component operating exposure. Exact Garwood confidence limits quantify count uncertainty under a constant-rate Poisson model. A zero failure count has a nonzero upper confidence bound. This is not a proof of zero risk.
- **Kaplan–Meier:** failures and right-censored observations are separate. At tied exposure times, handle events using the at-risk set before removing censoring. Independent censoring and reasonably comparable lifetimes are required. Population changes, recurrent repairs, and competing mechanisms can violate these assumptions.
- **Weibull:** censored maximum-likelihood fitting is gated to at least five failures and ten observations. The foundation does not supply parameter confidence intervals. A shape/scale estimate from synthetic data is an architecture demonstration, not an approved life limit. Extrapolation is not defensible merely because an optimizer converges.
- **Revision comparisons:** descriptive exposure-normalized groups, not causal proof. Tool, lot, operating regime, phase and maintenance history can confound revision effects.
- **Downtime:** union overlapping stoppage intervals within the same chamber and report chamber-hours. Attribution weights and adjudication determine component contributions. Repair time, waiting, administrative delay and critical-path impact are not interchangeable.

The foundation does not certify compliance with SEMI E10. Its configurable delay classifications can be aligned by authorized reliability engineers to the applicable controlled definitions. Commissioning impact requires separate critical-path evidence.

## Forecast states

| State | Meaning | What is permitted here |
| --- | --- | --- |
| A: rules-based PM | Threshold proximity based on an identified policy and measured eligible usage. | Clearly synthetic engineer-configured recommendations; no implied OEM requirement. |
| B: statistical estimate | Population estimate from comparable failures/exposure/censored histories. | Synthetic methodology demonstration with eligibility, uncertainty and model version. |
| C: validated predictive model | Physically justified precursor model with independent outcome validation. | No production-validated model is supplied. |

The unavailable state displays **“Insufficient evidence for reliable failure prediction.”** No arbitrary health score replaces a failure probability. The 100, 500 and 1,000 RF-hour horizons are optional display horizons, not actual useful-life claims for a Flex part. Synthetic forecasts must retain their synthetic label in every downstream export or screenshot.

The synthetic exponential teaching cohort is separate from the operational demonstration fleet. It exercises State B only and has no independently calibrated false-alert rate, warning lead-time, or remaining-useful-life claim. State C is an extension boundary; no validated predictive-health implementation is supplied.

## Promotion criteria for a real model

Collect approved component serial/revision/lot data, effective installation and qualified refurbishment histories, reliable mechanism-specific exposure, adjudicated outcomes, censor reasons, verified downtime and physical evidence. Establish minimum event counts and cohort comparability with reliability engineers. Handle competing mechanisms and recurrent repairs explicitly rather than relabeling every repair as a new independent lifetime.

Define features only from data available before the prediction timestamp. Split development and evaluation by held-out tool or commissioning campaign and preserve temporal ordering. Guard against future maintenance findings, removal dates, post-failure alarms and duplicate component histories leaking across folds. Fit preprocessing only on training data.

Assess calibration, uncertainty coverage, false alerts per operating exposure, useful warning lead time, mechanism specificity and decision consequences on independent outcomes. Record model version, feature schema, source snapshot and validation results. Conduct shadow-mode evaluation before proposing any operational recommendation. Independent engineering and security approval are required; this application provides no path for automatic intervention.
