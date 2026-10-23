# Component-to-sensor mapping guide

Use real channel identifiers only inside an approved environment after obtaining the controlled sensor dictionary. Bundled channel names are fictional. A configurable hierarchy is an inventory structure, not an OEM-accurate Flex schematic.

## Contracts and records

The executable schemas are `backend/app/enterprise/telemetry_contracts.py`; persistence is in `backend/app/enterprise/models.py` and engineering services in `telemetry.py`.

| Record | Required meaning |
| --- | --- |
| `SensorInput` / `sensor_channels` | Source/channel identity, canonical tool/chamber, subsystem/description, measured/state/counter/validated-interval type, units, sample frequency, configuration, effective interval, quality and documentation. Range values require a document reference. |
| `MappingInput` / `component_sensor_mappings` | Component definition, sensor, relationship, physical explanation, configuration, optional chamber/revision restriction, effective interval, evidence, confidence and engineer/internal-AI proposal method. |
| `ExposureRuleInput` / `exposure_definitions` | Definition/sensor/source/configuration, dimension, method, explicit distinct active/inactive states when applicable, allowed gap, rollover/rate, effective interval, union aggregation and controlled reference. |
| `SampleInput` / `sensor_samples` | Source-version-linked time/value or state, optional interval end, quality, reset metadata and exact source location. |
| `equipment_configuration_periods` | Effective-dated actual tool configuration with verification and source. Exposure cannot use the current configuration indiscriminately for old installations. |
| `calculation_lineage` | Component/rule, source versions, derivation interval, method/version, input hash, result and issues. |

The relationship is many-to-many: one sensor may provide chamber/utility context to several parts, and one part may have several relevant sensors. Distinguish the following explicitly:

| Relationship | Interpretation |
| --- | --- |
| `direct_measurement` | Measures a property directly associated with the physical component; still requires validated interpretation. |
| `upstream_influence` | A process or utility upstream of the component can affect its behavior. |
| `downstream_effect` | A downstream response may reflect multiple causes. |
| `supporting_diagnostic` | Useful troubleshooting context without a direct condition measurement. |
| `shared_utility` | Common environmental or utility influence affecting multiple components. |
| `exposure_counter` | The approved source from which an applicable operating exposure can be derived. |

## Engineering approval sequence

1. Identify the exact tool/chamber/configuration period and part definition/revision, then obtain an approved component function description and sensor catalog.
2. Determine the physical relationship and units. Record what the channel does **and does not** measure. Do not infer a condition measurement from correlation or a similar channel name.
3. Propose the mapping with explanation, source citations, effective interval and confidence. Internal AI may propose through the constrained interface; its output remains unverified.
4. An authorized equipment engineer checks the real configuration, physical causal relationship, applicability interval, source evidence and sampling/quality limitations. Approve or reject with a recorded reason. A proposal's confidence does not authorize it.
5. For exposure, separately approve a matching rule: physical source, eligible operating mode, distinct active/inactive-state definitions or counter semantics, allowed gaps, reset/rollover/rate limits, units and reference. Unknown state labels are unavailable observation coverage. An approved diagnostic mapping alone does not authorize RF-hour accumulation.
6. Compare the derived exposure against an independent approved source and known replacement history before using it for PM. Preserve disagreements and uncertainty.

Effective calculation applicability is the intersection of installation, mapping, sensor, exposure rule, and verified equipment-configuration periods. Revision and chamber restrictions must match. Multiple applicable rules for the same physical window require reconciliation; they must not silently add unrelated source hours. Duplicate mappings to one rule do not create additional exposure.

## Component traces

Retrieve only bounded historical windows and only authorized source/equipment/collection records. The typed query contract permits at most 31 days; retrieval is bounded to 50,000 raw records and at most 1,000 display points per channel. Display downsampling is not used for exposure calculations. These limits protect the local foundation; source-specific limits may be stricter and must be supplied internally.

Filter trace context by the component's actual installation and approved mapping/configuration interval, and retain operating-state labels. Compare normal and pre-failure traces only when state, sampling, units and cohort are physically comparable. Display freshness, coverage and missing/conflicting sample issues. A temperature, response or pressure deviation is **diagnostic telemetry** unless an independently validated degradation model supports a stronger claim.

The foundation supplies bounded data and mapping/lineage workflows. Large-scale time-series storage, production precursor validation, OEM channel dictionaries and source-specific rate/retention controls remain internal integration work. No actual Flex sensor naming, ranges or predicted health are supplied.

Current APIs are under `/api/enterprise`: `sensors`, `mappings`, `exposure-rules`, the corresponding mapping/rule review routes, and `components/{id}/telemetry` / `components/{id}/lineage`. Use the running OpenAPI schema for validated request bodies and permissions. Proposed mappings and rules remain inert until their separate approval requirements are satisfied.
