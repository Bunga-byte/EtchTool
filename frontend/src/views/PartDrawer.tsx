import {
  Activity,
  ArrowRight,
  CalendarClock,
  ChevronRight,
  Clock3,
  FileSearch,
  FlaskConical,
  Layers3,
  Wrench,
  X,
} from "lucide-react";
import { useState } from "react";
import { useApi } from "../api";
import { useDialog } from "../useDialog";
import { asItems, date, label, formatNumber as num } from "../utils";

import {
  Badge,
  Empty,
  FdcPlot,
  Field,
  Metric,
  Notice,
  Panel,
  Progress,
  RecordList,
  State,
  Timeline,
} from "../components";
export function PartDrawer({
  id,
  onClose,
  onCase,
  onPart,
}: {
  id: string;
  onClose: () => void;
  onCase: (id: string) => void;
  onPart: (id: string) => void;
}) {
  const api = useApi(`/api/components/${encodeURIComponent(id)}`),
    d = api.data,
    [tab, setTab] = useState("overview");
  const dialogRef = useDialog(onClose);
  const exposure = d?.exposure || {},
    pm = d?.pm || {},
    f = d?.forecast || {},
    p = d?.provenance || {};
  return (
    <div
      className="drawer-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section
        ref={dialogRef}
        className="part-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="part-title"
      >
        <div className="drawer-top">
          <span className="eyebrow">SERIALIZED COMPONENT RECORD</span>
          <button
            className="icon-button"
            aria-label="Close component details"
            onClick={onClose}
            autoFocus
          >
            <X size={21} />
          </button>
        </div>
        <State {...api}>
          {d && (
            <>
              <div className="part-heading">
                <div className="part-symbol">
                  <Wrench size={26} />
                </div>
                <div>
                  <h2 id="part-title">{d.name}</h2>
                  <p className="mono">
                    {d.part_number} <span>/</span> {d.serial_number}
                  </p>
                </div>
                <Badge value={d.status} />
              </div>
              <div className="part-location">
                <Layers3 size={15} />
                {d.tool_name} <ChevronRight size={13} />
                {d.chamber_name}
                <ChevronRight size={13} />
                {d.subsystem}
                <ChevronRight size={13} />
                {d.assembly}
                <ChevronRight size={13} />
                {d.position}
              </div>
              <div
                className="detail-tabs"
                role="tablist"
                aria-label="Component details"
              >
                {[
                  ["overview", "Overview"],
                  ["history", "Lifecycle history"],
                  ["engineering", "Engineering evidence"],
                ].map(([key, text]) => (
                  <button
                    role="tab"
                    aria-selected={tab === key}
                    className={tab === key ? "active" : ""}
                    key={key}
                    onClick={() => setTab(key)}
                  >
                    {text}
                  </button>
                ))}
              </div>
              <div className="drawer-body">
                <div className="component-snapshot">
                  <Clock3 size={12} /> Detail exposure snapshot:{" "}
                  {date(exposure.snapshot_at)}. A chamber’s historical inventory
                  selection does not change this full lifecycle record.
                </div>
                {tab === "overview" && (
                  <>
                    <div className="metrics-grid three compact-metrics">
                      <Metric
                        label="Since installation"
                        value={exposure.hours}
                        unit={exposure.unit || "RF h"}
                        icon={Activity}
                        note={`${num(typeof exposure.completeness === "number" ? exposure.completeness * 100 : null, 0)}% data coverage`}
                      />
                      <Metric
                        label="Lifetime exposure"
                        value={exposure.lifetime_hours}
                        unit={exposure.unit || "RF h"}
                        icon={Clock3}
                        note="Across recorded installations"
                      />
                      <Metric
                        label="PM interval remaining"
                        value={pm.remaining}
                        unit={pm.unit || "h"}
                        icon={CalendarClock}
                        tone={pm.status === "overdue" ? "red" : "amber"}
                        note={label(pm.status)}
                      />
                    </div>
                    {(exposure.completeness < 0.95 ||
                      exposure.attribution_status === "disputed") && (
                      <Notice kind="warning">
                        <strong>Exposure requires review.</strong>{" "}
                        {Array.isArray(exposure.issues)
                          ? exposure.issues.join(" · ")
                          : label(exposure.issues)}{" "}
                        Unrecorded usage is not extrapolated.
                      </Notice>
                    )}
                    <div className="two-column">
                      <Panel title="Identity & traceability">
                        <dl className="field-grid">
                          <Field
                            name="OEM part number"
                            value={
                              <span className="mono">{d.part_number}</span>
                            }
                          />
                          <Field
                            name="Serial number"
                            value={
                              <span className="mono">{d.serial_number}</span>
                            }
                          />
                          <Field name="Hardware revision" value={d.revision} />
                          <Field name="Assembly" value={label(d.assembly)} />
                          <Field
                            name="Manufacturer"
                            value={label(d.definition?.manufacturer)}
                          />
                          <Field
                            name="Supplier / lot"
                            value={
                              label(d.identity?.supplier) +
                              " / " +
                              label(d.identity?.lot)
                            }
                          />
                          <Field
                            name="Traceability"
                            value={label(d.identity?.traceability_status)}
                          />
                          <Field
                            name="Installed"
                            value={date(d.installed_at)}
                          />
                          <Field
                            name="Refurbishment"
                            value={label(d.identity?.refurbishment_status)}
                          />
                        </dl>
                      </Panel>
                      <Panel title="Maintenance policy">
                        <div className="policy-detail">
                          <div className="policy-status">
                            <Badge value={pm.status} />
                            <strong>
                              {num(pm.percent_consumed, 0)}% consumed
                            </strong>
                          </div>
                          <Progress
                            value={pm.percent_consumed}
                            status={pm.status}
                          />
                          <dl className="field-grid">
                            <Field
                              name="Policy threshold"
                              value={`${num(pm.threshold)} ${pm.unit || "h"}`}
                            />
                            <Field
                              name="Policy basis"
                              value={label(pm.basis)}
                            />
                            <Field
                              name="Relevant dimension"
                              value={label(exposure.dimension)}
                            />
                            <Field
                              name="Since refurbishment"
                              value={`${num(exposure.since_refurbishment)} ${exposure.unit || "h"}`}
                            />
                          </dl>
                          <small>
                            Demonstration recommendation. Not an OEM
                            specification.
                          </small>
                        </div>
                      </Panel>
                    </div>
                    <Panel
                      title="Failure forecast eligibility"
                      description="Rules, statistics, and validated health models are separate states"
                    >
                      <div className="forecast-content">
                        <span className="forecast-icon">
                          <FlaskConical size={25} />
                        </span>
                        <div>
                          <span className="eyebrow">
                            {label(f.state)} ·{" "}
                            {f.label || "Engineering evidence gate"}
                          </span>
                          <h3>
                            {f.eligible
                              ? "Synthetic statistical demonstration"
                              : "Insufficient evidence for reliable failure prediction."}
                          </h3>
                          <p>{f.message}</p>
                          {f.model_version && (
                            <small className="mono">
                              Model version: {f.model_version}
                            </small>
                          )}
                          {asItems(f.horizons).length > 0 && (
                            <div className="horizon-grid">
                              {asItems(f.horizons).map((h: any, i: number) => (
                                <div key={i}>
                                  <span>
                                    Next {num(h.hours || h.horizon)} RF h
                                  </span>
                                  <strong>
                                    {h.probability != null
                                      ? `${num(h.probability * 100, 1)}%`
                                      : "Unavailable"}
                                  </strong>
                                  <small>Synthetic estimate only</small>
                                </div>
                              ))}
                            </div>
                          )}
                          <p className="muted">
                            {Array.isArray(f.limitations)
                              ? f.limitations.join(" · ")
                              : label(
                                  f.limitations ||
                                    "No production validation. No automated equipment intervention.",
                                )}
                          </p>
                        </div>
                      </div>
                    </Panel>
                    <Panel
                      title="Engineering specifications"
                      description="Controlled OEM documentation is required before verification"
                    >
                      <div className="table-scroll">
                        <table>
                          <thead>
                            <tr>
                              <th>Parameter</th>
                              <th>Nominal / limits</th>
                              <th>Units</th>
                              <th>Verification / source</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(d.specifications || []).map(
                              (s: any, i: number) => (
                                <tr key={i}>
                                  <td>
                                    {s.parameter || s.parameter_name || s.name}
                                  </td>
                                  <td>
                                    {s.nominal_value ?? s.nominal ?? "Unknown"}{" "}
                                    / {s.minimum ?? s.min ?? "Unknown"} –{" "}
                                    {s.maximum ?? s.max ?? "Unknown"}
                                  </td>
                                  <td>{s.units || s.unit || "Unknown"}</td>
                                  <td>
                                    <Badge
                                      value={
                                        s.verification_status ||
                                        s.status ||
                                        "pending verification"
                                      }
                                    />
                                    <div className="cell-sub">
                                      {s.source_document ||
                                        s.source ||
                                        "OEM documentation pending"}
                                    </div>
                                  </td>
                                </tr>
                              ),
                            )}
                          </tbody>
                        </table>
                        {!d.specifications?.length && (
                          <Empty>
                            No verified specifications available. OEM limits are
                            unknown.
                          </Empty>
                        )}
                      </div>
                    </Panel>
                    <Panel title="Source provenance & calculation confidence">
                      <dl className="field-grid wide-fields">
                        <Field
                          name="Source system"
                          value={label(
                            p.source_system || p.source || exposure.source,
                          )}
                        />
                        <Field
                          name="Original source ID"
                          value={label(p.source_id || p.original_source_id)}
                        />
                        <Field
                          name="Recorded timestamp"
                          value={date(p.recorded_at)}
                        />
                        <Field
                          name="Effective timestamp"
                          value={date(p.effective_at || d.installed_at)}
                        />
                        <Field
                          name="Last synchronization"
                          value={date(p.last_sync)}
                        />
                        <Field
                          name="Verification status"
                          value={label(p.verification_status || p.quality)}
                        />
                        <Field
                          name="Exposure confidence"
                          value={label(exposure.confidence)}
                        />
                        <Field
                          name="Measurement source"
                          value={label(exposure.source)}
                        />
                      </dl>
                    </Panel>
                  </>
                )}
                {tab === "history" && (
                  <>
                    <Panel
                      title="Installation & replacement timeline"
                      description="Removal closes exposure accrual for that installation"
                    >
                      <Timeline items={d.installations || []} />
                    </Panel>
                    <Panel
                      title="Component replacement sequence"
                      description="Both serialized identities are preserved; replacement does not establish failure"
                    >
                      <div className="replacement-list">
                        {(d.replacements || []).map((r: any, i: number) => (
                          <div className="replacement-row" key={i}>
                            <div>
                              <span className="eyebrow">REMOVED COMPONENT</span>
                              <button
                                className="text-link mono"
                                onClick={() => onPart(r.old_component_id)}
                              >
                                {r.old_serial_number}
                              </button>
                            </div>
                            <ArrowRight size={19} />
                            <div>
                              <span className="eyebrow">
                                REPLACEMENT COMPONENT
                              </span>
                              <button
                                className="text-link mono"
                                onClick={() => onPart(r.new_component_id)}
                              >
                                {r.new_serial_number}
                              </button>
                            </div>
                            <small>
                              {date(r.timestamp)} · {r.reason}
                            </small>
                          </div>
                        ))}
                        {!d.replacements?.length && (
                          <Empty>
                            No component replacement sequence recorded.
                          </Empty>
                        )}
                      </div>
                    </Panel>
                    <Panel
                      title="Maintenance interventions"
                      description="Replacement is not automatically a failure"
                    >
                      <Timeline items={d.maintenance || []} />
                    </Panel>
                    <Panel title="Associated failure episodes">
                      <div className="case-list">
                        {(d.failures || []).map((item: any) => (
                          <button
                            className="case-row"
                            onClick={() => onCase(item.id)}
                            key={item.id}
                          >
                            <FileSearch size={18} />
                            <span>
                              <strong>{item.title}</strong>
                              <small>
                                {date(item.started_at)} ·{" "}
                                {num(item.downtime_hours)} h associated
                              </small>
                            </span>
                            <Badge value={item.status} />
                            <ChevronRight size={16} />
                          </button>
                        ))}
                        {!d.failures?.length && (
                          <Empty>
                            No failure recorded. This component remains a
                            censored observation.
                          </Empty>
                        )}
                      </div>
                    </Panel>
                  </>
                )}
                {tab === "engineering" && (
                  <>
                    <Notice>
                      Signals and specifications are synthetic or pending
                      verification. A trace anomaly alone cannot establish
                      physical root cause.
                    </Notice>
                    <Panel
                      title="Relevant FDC trend"
                      description="Component-linked operating context"
                    >
                      <FdcPlot data={d.fdc} />
                    </Panel>
                    <Panel title="Component definition">
                      <dl className="field-grid wide-fields">
                        {Object.entries(d.definition || {}).map(
                          ([key, value]) => (
                            <Field
                              key={key}
                              name={label(key)}
                              value={label(value)}
                            />
                          ),
                        )}
                      </dl>
                    </Panel>
                    <Panel title="Calculation issues">
                      <RecordList
                        items={exposure.issues || []}
                        empty="No calculation issues reported for available records."
                      />
                    </Panel>
                  </>
                )}
              </div>
            </>
          )}
        </State>
      </section>
    </div>
  );
}
