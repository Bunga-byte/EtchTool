# RF exposure validation and acceptance

All reference examples here are synthetic arithmetic. Actual RF-active state/source definitions, counter behavior, allowed gaps, operating modes and PM limits require controlled OEM/site evidence. RF-on duration is not applicable to every component.

## Interval formula

For component installation `I = [installed_at, removed_at or as_of)`, approved applicability window `C`, and eligible RF-active intervals `Rj` for the correct chamber/source/mode:

```text
RF_hours = duration(union(Rj intersect I intersect C)) / 3600
```

`C` intersects effective sensor, component mapping, exposure rule and actual configuration periods. Union duplicates and overlapping eligible intervals before measuring duration. Never sum simultaneous independent RF generators unless an approved exposure definition explicitly requires a separate stress quantity. The implementation supports union aggregation; it does not invent a multi-source stress law.

Lifetime exposure aggregates eligible installation histories; exposure since installation uses the selected installation. Exposure since qualified refurbishment uses that separately documented boundary. Removal stops accrual. Reinstallation or repair does not erase prior lifetime exposure. Unqualified refurbishment does not silently reset PM.

## Reference calculations

| Synthetic case | Inputs | Required result |
| --- | --- | --- |
| Installation/removal inside active periods | Installed 00:30, removed 03:15 UTC; RF active `[00:00,01:00)` and `[02:00,04:00)` | `0.5 + 1.25 = 1.75 RF h`. |
| Duplicate source interval | The same eligible `[02:00,04:00)` appears twice | It contributes once. |
| Replacement boundary | Part A removed 01:00, Part B installed 01:00; eligible `[00:00,02:00)` | A receives 1 h, B receives 1 h; later samples cannot increase A after removal. |
| Physical gap | A removed 01:00, B installed 01:30; eligible `[00:00,02:00)` | A receives 1 h, B receives 0.5 h; the uninstalled half-hour is not assigned to either. |
| Unrelated dimension/source | Powered duration or another RF source is present | Exclude from this RF rule; show separately if relevant. |
| Configuration change | A mapping/rule applies only until 02:00 | Its source cannot accrue after 02:00 without a newly approved applicable definition. |

## Source methods

**Validated intervals:** clip observed active time to the eligible window and union it. Numeric interval quantities must identify a fully inactive interval (zero) or full elapsed active duration; a partial aggregate does not identify where ON time occurred and is withheld. Use a supported cumulative counter or finer validated state intervals instead. Preserve the original interval and derivation. Coverage must identify monitored time; RF-off observations count as monitoring coverage.

**State samples:** require explicit distinct approved active and inactive values, and use the previous recognized state only until a following sample within the approved maximum gap. Unknown labels and conflicting/invalid same-time samples invalidate adjacent coverage. Do not assume that the last observed ON state continues forever. If a window is not observed, mark it unavailable rather than filling a precise duration.

**Cumulative counters:** derive positive increments only with consistent source/units, ordered samples, a plausible rate and documented reset/rollover behavior. Equal counters can represent measured RF-off time; they are not automatically missing. Missing spans, conflicting timestamps and invalid samples reduce coverage.

- An undeclared decrease is a reset/gap issue; do not add a negative increment or infer a rollover.
- A rollover requires an approved modulus and a physically plausible resulting increment.
- A declared reset with no exact timestamp/baseline loses the affected interval. With exact reset metadata, only defensible post-reset usage can be assigned; pre-reset usage remains unallocated.
- A cumulative delta crossing installation/removal, configuration, rule or as-of boundaries cannot be prorated from elapsed time. Withhold it unless finer observations establish attribution.

The calculation returns verified observed usage/minimum where justified, issues, coverage/confidence, source and method traceability. It does not turn unobserved time into fact. Competing approved definitions are surfaced and the overlapping disputed result is withheld.

An approved Phase 2 rule replaces the baseline source only within its applicable window. Missing samples inside that approved window are not backfilled from the old baseline to create artificial completeness. Baseline observations outside the approved window remain available. Lineage retains source-version IDs, sample identity/metadata/quality/reset signatures, rule/window, method version, derived intervals, result and issues; old calculation revisions remain retained. Conflicting revised inputs produce a new traceable calculation rather than reusing a stale result hash.

## PM linkage

For a matching applicable policy with threshold `T` and eligible usage `U`, `remaining = T - U` and `percent_consumed = 100 * U / T`. Interpret this with coverage, confidence, source and policy basis. Incomplete data cannot establish an “OK” condition or a reliable failure forecast. If the verified minimum already exceeds a threshold, report that evidence and its limits explicitly.

Rules-based PM, documented OEM limits, site-approved policy, engineering recommendations and statistical life estimates are separate classifications. The bundled intervals are fictional demonstration policies. A predicted remaining useful life is not an OEM PM threshold.

## Validation suite and internal acceptance

The foundation engineering suite `backend/tests/test_engineering.py` contains interval, replacement, reset/rollover/gap, dimension/source, completeness, refurbishment and uncertainty cases. Phase 2 extends this with persisted source/sensor/configuration/lineage and source-to-UI scenarios. The [validation ledger](PHASE2_VALIDATION.md) records actual executed results; do not infer a pass from this list.

Before operational use, compare against a controlled historical sample with independently known installation/removal times and RF counter/state history. Test clock offset/uncertainty, controller restarts, gaps spanning replacements, chamber inactivity, simultaneous generators, configuration changes, counter unit/rate, source revisions and incomplete historical installations. Confirm repeated import/reprocessing does not change exposure merely because content was duplicated. Confirm lineage reproduces the same result from retained originals and versioned rules.

Only after approved meter reconciliation and engineering review should internally imported exposure support PM. Keep the first real integration in read-only shadow mode and surface reconciliation deltas rather than silently selecting the latest source.
