import { useState } from "react";
import { Clock3 } from "lucide-react";
import { useApi } from "../api";
import { Badge, Empty, Field, Notice, Panel, State } from "../components";
import { date, label, formatNumber as num, toUTC } from "../utils";
import { enterprisePath } from "./shared";
import { recordItems } from "./utils";

function initialWindow(component: any) {
  const dates = [component.removed_at, component.exposure?.snapshot_at]
    .filter(Boolean)
    .map((value: string) => new Date(value).valueOf())
    .filter(Number.isFinite);
  const end = dates.length ? Math.min(...dates) : Date.UTC(2026, 0, 31),
    installed = new Date(
      component.installed_at || end - 31 * 86400000,
    ).valueOf(),
    start = Math.max(
      Number.isFinite(installed) ? installed : 0,
      end - 31 * 86400000,
    );
  return {
    start: new Date(start).toISOString().slice(0, 16),
    end: new Date(end).toISOString().slice(0, 16),
    state: "",
  };
}

export function ComponentTelemetry({ component }: { component: any }) {
  const [window, setWindow] = useState(() => initialWindow(component)),
    [query, setQuery] = useState(() => initialWindow(component)),
    [error, setError] = useState("");
  const path = `${enterprisePath}/components/${encodeURIComponent(component.id)}`;
  const api = useApi(
      `${path}/telemetry?start=${encodeURIComponent(toUTC(query.start))}&end=${encodeURIComponent(toUTC(query.end))}&max_points=500${query.state ? `&state=${encodeURIComponent(query.state)}` : ""}`,
    ),
    lineage = useApi(`${path}/lineage`),
    channels = api.data?.channels || [],
    states = [
      ...new Set(
        channels
          .flatMap((channel: any) => channel.points || [])
          .map(
            (point: any) =>
              point.state || point.source_location?.operating_state,
          )
          .filter(Boolean),
      ),
    ];
  function apply() {
    setError("");
    const seconds =
      (new Date(toUTC(window.end)).valueOf() -
        new Date(toUTC(window.start)).valueOf()) /
      1000;
    if (!Number.isFinite(seconds) || seconds <= 0 || seconds > 31 * 86400) {
      setError("Telemetry windows must be positive and at most 31 days.");
      return;
    }
    setQuery({ ...window });
  }
  return (
    <>
      <Notice>
        <strong>Diagnostic telemetry.</strong> Approved, configuration-,
        revision-, chamber-, and time-applicable mappings determine which
        channels are shown. No signal is presented as a validated degradation
        indicator or failure probability.
      </Notice>
      <Panel
        title="Component telemetry window"
        description="Samples are clipped to the serialized installation and approved mapping interval"
      >
        <div className="telemetry-controls">
          <label>
            Telemetry start (UTC)
            <input
              aria-label="Telemetry start (UTC)"
              type="datetime-local"
              value={window.start}
              onChange={(event) =>
                setWindow({ ...window, start: event.target.value })
              }
            />
          </label>
          <label>
            Telemetry end (UTC)
            <input
              aria-label="Telemetry end (UTC)"
              type="datetime-local"
              value={window.end}
              onChange={(event) =>
                setWindow({ ...window, end: event.target.value })
              }
            />
          </label>
          <label>
            Operating-state filter
            <input
              aria-label="Operating-state filter"
              list="component-telemetry-states"
              value={window.state}
              onChange={(event) =>
                setWindow({ ...window, state: event.target.value })
              }
              placeholder="All observed states"
            />
            <datalist id="component-telemetry-states">
              {states.map((state: any) => (
                <option key={state} value={state} />
              ))}
            </datalist>
          </label>
          <button className="button" onClick={apply}>
            Apply telemetry window
          </button>
        </div>
        {error && (
          <p className="enterprise-error" role="alert">
            {error}
          </p>
        )}
      </Panel>
      <State {...api} loading={api.loading && !api.data}>
        {(api.data?.issues || []).map((issue: string, index: number) => (
          <Notice key={index} kind="warning">
            {issue}
          </Notice>
        ))}
        {channels.map((channel: any) => (
          <Panel
            key={channel.mapping_id || channel.id}
            title={channel.description || channel.channel_key}
            description={`${channel.channel_key} · ${channel.unit || "Unit unknown"} · ${label(channel.relationship)}`}
            action={
              <Badge
                value={channel.mapping_verification || channel.verification}
              />
            }
          >
            <div className="channel-explanation">
              <strong>Physical relationship</strong>
              <p>{channel.physical_explanation}</p>
              <small>{channel.interpretation}</small>
            </div>
            <dl className="field-grid wide-fields">
              <Field
                name="Configuration / component revision"
                value={`${channel.configuration_id} / ${channel.part_revision || component.revision}`}
              />
              <Field
                name="Sensor effective interval"
                value={`${date(channel.effective_from)} → ${channel.effective_to ? date(channel.effective_to) : "open-ended"}`}
              />
              <Field
                name="Measurement freshness"
                value={
                  channel.latest_at
                    ? `${date(channel.latest_at)} · ${num(channel.freshness_seconds)} seconds from query end`
                    : "No observed samples"
                }
              />
              <Field
                name="Data completeness"
                value={
                  channel.completeness == null
                    ? "Unknown sampling coverage"
                    : `${num(channel.completeness * 100, 1)}% observed coverage`
                }
              />
              <Field
                name="Observed / displayed samples"
                value={`${num(channel.record_count, 0)} / ${num(channel.displayed_count ?? channel.points?.length, 0)}`}
              />
              <Field name="Source" value={channel.source_id} />
              <Field
                name="Applicable installation / mapping windows"
                value={
                  (channel.applicable_windows || [])
                    .map(
                      (period: any) =>
                        `${date(period.start)} → ${date(period.end)}`,
                    )
                    .join(" · ") || "Not recorded"
                }
              />
            </dl>
            <DiagnosticTrace
              points={channel.points || []}
              start={api.data.start}
              unit={channel.unit}
            />
            <details className="telemetry-record-details">
              <summary>Inspect measured samples and source locations</summary>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Timestamp</th>
                      <th>Value / state</th>
                      <th>Quality</th>
                      <th>Source version / location</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(channel.points || []).map((point: any) => (
                      <tr key={point.id}>
                        <td>{date(point.timestamp)}</td>
                        <td>
                          {point.value == null
                            ? "Not measured"
                            : num(point.value, 5)}{" "}
                          {point.unit}
                          <div className="cell-sub">
                            {label(
                              point.state ||
                                point.source_location?.operating_state,
                            )}
                          </div>
                        </td>
                        <td>
                          <Badge value={point.quality} />
                        </td>
                        <td className="mono">
                          {point.source_version_id}
                          <div className="cell-sub">
                            {label(point.source_location)}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
            <div className="panel-footnote">
              {channel.downsample_method ||
                "Only observed values are displayed. Missing records are not interpolated."}{" "}
              · {api.data.reference_comparison}
            </div>
          </Panel>
        ))}
        {!channels.length && (
          <Empty>
            No approved applicable sensor mapping or observed telemetry is
            available in this window. Inspect Sensor registry and the FDC
            ingestion job.
          </Empty>
        )}
        {!!api.data?.events?.length && (
          <Panel
            title="Temporally correlated equipment events"
            description="A temporal association is not proof of component causation"
          >
            <div className="record-list">
              {api.data.events.map((event: any) => (
                <div className="record" key={event.id}>
                  <Clock3 size={14} />
                  <div>
                    <strong>{event.label}</strong>
                    <p>
                      {date(event.timestamp)} · {label(event.symptom_role)}
                    </p>
                    <small>{event.interpretation}</small>
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        )}
      </State>
      <Panel
        title="Exposure calculation lineage"
        description="Retained source versions, approved rules, and deterministic derivation"
      >
        <State {...lineage} loading={lineage.loading && !lineage.data}>
          <div className="lineage-list">
            {recordItems(lineage.data).map((item: any) => (
              <article className="lineage-card" key={item.id}>
                <div className="enterprise-job-heading">
                  <div>
                    <span className="mono">{item.id}</span>
                    <h3>{item.method_version}</h3>
                  </div>
                  <Badge value={item.rule?.verification} />
                </div>
                <dl className="field-grid wide-fields">
                  <Field
                    name="Calculation window"
                    value={`${date(item.start)} → ${date(item.end)}`}
                  />
                  <Field
                    name="Relevant exposure definition"
                    value={`${item.rule?.dimension} / ${item.rule?.source_name}`}
                  />
                  <Field
                    name="Calculation timestamp"
                    value={date(item.created_at)}
                  />
                </dl>
                <p className="lineage-sources">
                  Source versions:{" "}
                  {(item.source_version_ids || []).join(", ") || "Not recorded"}
                </p>
                <details>
                  <summary>
                    Inspect exact input fingerprint, derived intervals, result,
                    and issues
                  </summary>
                  <pre>
                    {JSON.stringify(
                      {
                        input_hash: item.input_hash,
                        rule: item.rule,
                        derived_intervals: item.derived_intervals,
                        result: item.result,
                        issues: item.issues,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </details>
              </article>
            ))}
            {!recordItems(lineage.data).length && (
              <Empty>
                No approved imported-exposure calculation has been recorded for
                this component. The existing synthetic exposure engine remains
                available in Overview.
              </Empty>
            )}
          </div>
          <div className="panel-footnote">{lineage.data?.note}</div>
        </State>
      </Panel>
    </>
  );
}

function DiagnosticTrace({
  points,
  start,
  unit,
}: {
  points: any[];
  start: string;
  unit: string;
}) {
  const numeric = points.filter(
      (point) =>
        typeof point.value === "number" && Number.isFinite(point.value),
    ),
    origin = new Date(start).valueOf();
  if (!numeric.length)
    return (
      <Empty>
        No numeric measurements are available for a plot. State samples remain
        available in the original-record table.
      </Empty>
    );
  const rows = numeric.map((point) => ({
      x: (new Date(point.timestamp).valueOf() - origin) / 3600000,
      y: point.value,
      point,
    })),
    minX = Math.min(...rows.map((row) => row.x)),
    maxX = Math.max(...rows.map((row) => row.x)),
    ys = rows.map((row) => row.y),
    low = Math.min(...ys),
    high = Math.max(...ys),
    padding = Math.max((high - low) * 0.1, Math.abs(high) * 0.01, 0.001),
    minY = low - padding,
    maxY = high + padding;
  const xy = (row: (typeof rows)[number]) => [
    60 + ((row.x - minX) / (maxX - minX || 1)) * 570,
    20 + (1 - (row.y - minY) / (maxY - minY)) * 155,
  ];
  return (
    <div className="diagnostic-trace">
      <svg
        viewBox="0 0 680 230"
        role="img"
        aria-label="Component diagnostic telemetry over observed operating time"
      >
        <title>
          Component diagnostic telemetry over observed operating time
        </title>
        {[0, 0.5, 1].map((t) => (
          <g key={t}>
            <line
              x1="60"
              x2="635"
              y1={20 + t * 155}
              y2={20 + t * 155}
              stroke="#e4ebf0"
              strokeDasharray="3 3"
            />
            <text x="50" y={24 + t * 155} textAnchor="end">
              {num(minY + (1 - t) * (maxY - minY), 3)}
            </text>
          </g>
        ))}
        {rows.map((row, index) => (
          <circle
            key={index}
            cx={xy(row)[0]}
            cy={xy(row)[1]}
            r="3.2"
            fill={
              ["bad", "missing", "conflict"].includes(row.point.quality)
                ? "#c97660"
                : "#168e85"
            }
          >
            <title>
              {date(row.point.timestamp)} · {row.y} {unit} · {row.point.quality}
            </title>
          </circle>
        ))}
        <text x="60" y="198">
          {num(minX, 2)} h
        </text>
        <text x="635" y="198" textAnchor="end">
          {num(maxX, 2)} h
        </text>
        <text x="347" y="221" textAnchor="middle">
          Observed samples · hours from query start · {unit || "unknown units"}
        </text>
      </svg>
      <p className="panel-footnote">
        Points show observations. Gaps are not connected or extrapolated as
        continuous signal history.
      </p>
    </div>
  );
}
