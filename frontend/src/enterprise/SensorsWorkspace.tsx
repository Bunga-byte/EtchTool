import { useState } from "react";
import { useApi } from "../api";
import { Badge, Empty, Notice, Panel, State } from "../components";
import { date, label, formatNumber as num } from "../utils";
import {
  ActionFeedback,
  enterprisePath,
  useEnterpriseAction,
  ViewerNote,
} from "./shared";
import { parseJsonObject, recordItems } from "./utils";

export function SensorsWorkspace({ token }: { token: string }) {
  const sensors = useApi(`${enterprisePath}/sensors`),
    mappings = useApi(`${enterprisePath}/mappings`),
    rules = useApi(`${enterprisePath}/exposure-rules`),
    [kind, setKind] = useState("mapping"),
    [payload, setPayload] = useState("{}"),
    [note, setNote] = useState<Record<string, string>>({}),
    [error, setError] = useState("");
  const action = useEnterpriseAction(token, () => {
    mappings.reload();
    rules.reload();
  });
  async function create() {
    setError("");
    try {
      const record = parseJsonObject(payload, "Engineering proposal");
      await action.run(
        `${enterprisePath}/${kind === "mapping" ? "mappings" : "exposure-rules"}`,
        record,
        "Engineering proposal staged. Review is required before use for component telemetry or exposure.",
      );
    } catch (reason) {
      setError((reason as Error).message);
    }
  }
  return (
    <>
      <Notice>
        Sensor relationships distinguish direct measurement, upstream influence,
        downstream effect, supporting diagnostic, shared utility, and exposure
        counters. An unverified mapping is not a component health model.
      </Notice>
      <Panel
        title="Equipment sensor catalog"
        description="Synthetic channel names only · configuration and effective-date applicability"
      >
        <State {...sensors} loading={sensors.loading && !sensors.data}>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Channel / source</th>
                  <th>Equipment scope</th>
                  <th>Signal / units</th>
                  <th>Applicability</th>
                  <th>Verification</th>
                </tr>
              </thead>
              <tbody>
                {recordItems(sensors.data).map((sensor: any) => (
                  <tr key={sensor.id}>
                    <td>
                      <strong className="mono">{sensor.channel_key}</strong>
                      <div className="cell-sub">{sensor.source_id}</div>
                      <small>{sensor.description}</small>
                    </td>
                    <td>
                      {sensor.tool_id} / {sensor.chamber_id}
                      <div className="cell-sub">{sensor.subsystem}</div>
                    </td>
                    <td>
                      {label(sensor.signal_type)} ·{" "}
                      {sensor.unit || "Unknown unit"}
                      <div className="cell-sub">
                        {num(sensor.sampling_hz)} Hz
                      </div>
                    </td>
                    <td>
                      {sensor.configuration_id}
                      <div className="cell-sub">
                        {date(sensor.effective_from)} →{" "}
                        {sensor.effective_to
                          ? date(sensor.effective_to)
                          : "open-ended"}
                      </div>
                    </td>
                    <td>
                      <Badge value={sensor.verification} />
                      <div className="cell-sub">{label(sensor.quality)}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!recordItems(sensors.data).length && (
            <Empty>
              No sensor is registered. Ingest the authorized synthetic telemetry
              source.
            </Empty>
          )}
        </State>
      </Panel>
      <Panel
        title="Component-to-sensor relationships"
        description="Engineering explanation and evidence are required for mapping approval"
      >
        <State {...mappings} loading={mappings.loading && !mappings.data}>
          <div className="mapping-card-list">
            {recordItems(mappings.data).map((mapping: any) => (
              <article className="mapping-card" key={mapping.id}>
                <div className="enterprise-job-heading">
                  <div>
                    <span className="mono">
                      {mapping.definition_id} → {mapping.sensor_id}
                    </span>
                    <h3>{label(mapping.relationship)}</h3>
                  </div>
                  <Badge value={mapping.verification} />
                </div>
                <p>{mapping.physical_explanation}</p>
                <small>
                  Configuration {mapping.configuration_id} · Chamber{" "}
                  {mapping.chamber_id || "Configuration-wide"} · Revision{" "}
                  {mapping.part_revision || "All documented revisions"} ·{" "}
                  {date(mapping.effective_from)} →{" "}
                  {mapping.effective_to
                    ? date(mapping.effective_to)
                    : "open-ended"}
                </small>
                <details>
                  <summary>Supporting evidence and approval</summary>
                  <pre>
                    {JSON.stringify(
                      {
                        evidence: mapping.evidence,
                        confidence: mapping.confidence,
                        proposed_by: mapping.proposed_by,
                        approved_by: mapping.approved_by,
                        approved_at: mapping.approved_at,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </details>
                {!["approved", "verified", "rejected"].includes(
                  mapping.verification,
                ) && (
                  <div className="mapping-review">
                    <label htmlFor={`mapping-note-${mapping.id}`}>
                      Mapping review note
                    </label>
                    <input
                      id={`mapping-note-${mapping.id}`}
                      value={note[mapping.id] || ""}
                      onChange={(event) =>
                        setNote({ ...note, [mapping.id]: event.target.value })
                      }
                    />
                    {["approve", "reject"].map((decision) => (
                      <button
                        key={decision}
                        className="button small"
                        disabled={
                          !token ||
                          (note[mapping.id]?.trim().length || 0) < 10 ||
                          !!action.busy
                        }
                        onClick={() =>
                          action.run(
                            `${enterprisePath}/mappings/${mapping.id}/review`,
                            { decision, note: note[mapping.id] },
                            "Mapping review recorded.",
                          )
                        }
                      >
                        {decision === "approve"
                          ? "Approve mapping"
                          : "Reject mapping"}
                      </button>
                    ))}
                  </div>
                )}
              </article>
            ))}
            {!recordItems(mappings.data).length && (
              <Empty>No component-sensor mapping is registered.</Empty>
            )}
          </div>
        </State>
      </Panel>
      <Panel
        title="Exposure definitions"
        description="Source-specific interval rules · unrelated RF sources are never indiscriminately added"
      >
        <State {...rules} loading={rules.loading && !rules.data}>
          <div className="mapping-card-list">
            {recordItems(rules.data).map((rule: any) => (
              <article className="mapping-card" key={rule.id}>
                <div className="enterprise-job-heading">
                  <div>
                    <span className="mono">{rule.id}</span>
                    <h3>
                      {label(rule.dimension)} · {label(rule.method)} ·{" "}
                      {rule.source_name}
                    </h3>
                  </div>
                  <Badge value={rule.verification} />
                </div>
                <p>
                  {rule.document_reference ||
                    "Controlled documentation not supplied"}
                </p>
                <small>
                  Component {rule.definition_id} · Sensor {rule.sensor_id} ·
                  Configuration {rule.configuration_id} · Aggregation{" "}
                  {label(rule.aggregation)} · Maximum gap{" "}
                  {num(rule.max_gap_seconds)} s
                </small>
                <details>
                  <summary>
                    Effective dates, reset, and rollover definition
                  </summary>
                  <pre>{JSON.stringify(rule, null, 2)}</pre>
                </details>
                {!["approved", "verified", "rejected"].includes(
                  rule.verification,
                ) && (
                  <div className="mapping-review">
                    <label htmlFor={`rule-note-${rule.id}`}>
                      Exposure rule review note
                    </label>
                    <input
                      id={`rule-note-${rule.id}`}
                      value={note[rule.id] || ""}
                      onChange={(event) =>
                        setNote({ ...note, [rule.id]: event.target.value })
                      }
                    />
                    {["approve", "reject"].map((decision) => (
                      <button
                        key={decision}
                        className="button small"
                        disabled={
                          !token ||
                          (note[rule.id]?.trim().length || 0) < 10 ||
                          !!action.busy
                        }
                        onClick={() =>
                          action.run(
                            `${enterprisePath}/exposure-rules/${rule.id}/review`,
                            { decision, note: note[rule.id] },
                            "Exposure definition review recorded.",
                          )
                        }
                      >
                        {decision === "approve"
                          ? "Approve exposure rule"
                          : "Reject exposure rule"}
                      </button>
                    ))}
                  </div>
                )}
              </article>
            ))}
            {!recordItems(rules.data).length && (
              <Empty>No exposure definition is registered.</Empty>
            )}
          </div>
        </State>
      </Panel>
      <Panel
        title="Propose an engineering mapping or exposure rule"
        description="Structured proposals are validated against the documented canonical contracts"
      >
        <div className="enterprise-form">
          <label htmlFor="sensor-proposal-kind">
            Engineering proposal type
          </label>
          <select
            id="sensor-proposal-kind"
            value={kind}
            onChange={(event) => setKind(event.target.value)}
          >
            <option value="mapping">Component-to-sensor mapping</option>
            <option value="rule">Component exposure definition</option>
          </select>
          <label htmlFor="sensor-proposal-json">
            Engineering proposal (JSON)
          </label>
          <textarea
            id="sensor-proposal-json"
            value={payload}
            onChange={(event) => setPayload(event.target.value)}
            rows={6}
            spellCheck={false}
          />
          <small>
            Use the sensor mapping guide and API schema for field names,
            evidence references, revision, configuration, and effective dates.
            Internal-AI proposals remain unverified until engineering review.
          </small>
          <button
            className="button primary"
            disabled={!token || !!action.busy}
            onClick={create}
          >
            Stage engineering proposal
          </button>
          <ViewerNote token={token} />
          {error && (
            <p role="alert" className="enterprise-error">
              {error}
            </p>
          )}
          <ActionFeedback {...action} />
        </div>
      </Panel>
    </>
  );
}
