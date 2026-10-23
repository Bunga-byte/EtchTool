import { useEffect, useState } from "react";
import { Play, RotateCcw } from "lucide-react";
import { useApi } from "../api";
import { Badge, Empty, Notice, Panel, State } from "../components";
import { date, label, formatNumber as num, toUTC } from "../utils";
import {
  ActionFeedback,
  enterprisePath,
  useEnterpriseAction,
  ViewerNote,
} from "./shared";
import { parseJsonObject, recordItems } from "./utils";

export function JobsWorkspace({
  token,
  selectedSource,
  onDocuments,
}: {
  token: string;
  selectedSource: string;
  onDocuments: () => void;
}) {
  const sources = useApi(`${enterprisePath}/sources`),
    api = useApi(`${enterprisePath}/jobs`),
    deadLetters = useApi(`${enterprisePath}/dead-letters`),
    [source, setSource] = useState(selectedSource),
    [kind, setKind] = useState("backfill"),
    [start, setStart] = useState("2026-01-01T00:00"),
    [end, setEnd] = useState("2026-02-01T00:00"),
    [query, setQuery] = useState("{}"),
    [inputError, setInputError] = useState("");
  const action = useEnterpriseAction(token, () => {
      api.reload();
      deadLetters.reload();
    }),
    items = recordItems(api.data),
    sourceItems = recordItems(sources.data);
  useEffect(() => {
    if (!source && sourceItems[0]) setSource(sourceItems[0].id);
  }, [sources.data, source]);
  async function create() {
    setInputError("");
    try {
      const parsed = parseJsonObject(query, "Job query");
      if (!start || !end || new Date(toUTC(end)) <= new Date(toUTC(start)))
        throw new Error(
          "Choose an end after the start of the bounded UTC window.",
        );
      await action.run(
        `${enterprisePath}/jobs`,
        {
          source_id: source,
          kind,
          window_start: toUTC(start),
          window_end: toUTC(end),
          query: parsed,
        },
        "Bounded ingestion job created. Run a processing pass to retrieve the authorized synthetic records.",
      );
    } catch (reason) {
      setInputError((reason as Error).message);
    }
  }
  return (
    <>
      <Panel
        title="Create bounded ingestion job"
        description="Persistent checkpoints and idempotent processing · no unrestricted source polling"
      >
        <div className="enterprise-form">
          <Notice>
            Only registered connector capabilities and authorized
            equipment/collection scopes are eligible. A processing pass is
            bounded; durable checkpoints allow resumption.
          </Notice>
          <div className="enterprise-form-grid">
            <label>
              Ingestion source
              <select
                aria-label="Ingestion source"
                value={source}
                onChange={(event) => setSource(event.target.value)}
              >
                {sourceItems.map((item: any) => (
                  <option key={item.id} value={item.id}>
                    {item.name || item.id}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Job kind
              <select
                aria-label="Job kind"
                value={kind}
                onChange={(event) => setKind(event.target.value)}
              >
                <option value="backfill">Historical backfill</option>
                <option value="incremental">Incremental synchronization</option>
                <option value="reprocess">
                  Reprocess stored source version
                </option>
              </select>
            </label>
            <label>
              Window start (UTC)
              <input
                aria-label="Job window start (UTC)"
                type="datetime-local"
                value={start}
                onChange={(event) => setStart(event.target.value)}
              />
            </label>
            <label>
              Window end (UTC)
              <input
                aria-label="Job window end (UTC)"
                type="datetime-local"
                value={end}
                onChange={(event) => setEnd(event.target.value)}
              />
            </label>
          </div>
          <label htmlFor="enterprise-job-query">Scoped query (JSON)</label>
          <textarea
            id="enterprise-job-query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            rows={3}
            spellCheck={false}
          />
          <small>
            Use connector-supported query fields only. Scope is checked by the
            server; this field cannot grant authorization.
          </small>
          <button
            className="button primary"
            disabled={!token || !source || !!action.busy}
            onClick={create}
          >
            Create ingestion job
          </button>
          <ViewerNote token={token} />
          {inputError && (
            <p role="alert" className="enterprise-error">
              {inputError}
            </p>
          )}
          <ActionFeedback {...action} />
        </div>
      </Panel>
      <Panel
        title="Ingestion job register"
        description="Checkpoints, retries, rejected records, and dead-letter visibility"
        action={
          <button className="text-link" onClick={onDocuments}>
            Inspect retrieved documents
          </button>
        }
      >
        <State {...api} loading={api.loading && !api.data}>
          <div className="enterprise-job-list">
            {items.map((job: any) => (
              <article className="enterprise-job" key={job.id}>
                <div className="enterprise-job-heading">
                  <div>
                    <span className="mono">{job.id}</span>
                    <h3>
                      {label(job.kind)} · {job.source_id}
                    </h3>
                  </div>
                  <Badge value={job.status} />
                </div>
                <dl className="field-grid wide-fields">
                  <div className="field">
                    <dt>Window</dt>
                    <dd>
                      {date(job.window_start)} → {date(job.window_end)}
                    </dd>
                  </div>
                  <div className="field">
                    <dt>Discovered / processed / rejected</dt>
                    <dd>
                      {num(
                        job.discovered ??
                          job.records_discovered ??
                          job.metrics?.discovered,
                        0,
                      )}{" "}
                      /{" "}
                      {num(
                        job.processed ??
                          job.records_processed ??
                          job.metrics?.processed,
                        0,
                      )}{" "}
                      /{" "}
                      {num(
                        job.rejected ??
                          job.records_rejected ??
                          job.metrics?.rejected,
                        0,
                      )}
                    </dd>
                  </div>
                  <div className="field">
                    <dt>Attempts / next retry</dt>
                    <dd>
                      {num(job.attempts ?? job.attempt_count, 0)} ·{" "}
                      {date(job.next_attempt_at || job.next_retry_at)}
                    </dd>
                  </div>
                </dl>
                {(job.error || job.last_error) && (
                  <p className="enterprise-error">
                    {label(job.error || job.last_error)}
                  </p>
                )}
                <JobCheckpoint id={job.id} />
                <div className="enterprise-job-actions">
                  <button
                    className="button small"
                    disabled={
                      !token ||
                      !!action.busy ||
                      !["pending", "retry_wait"].includes(job.status)
                    }
                    onClick={() =>
                      action.run(
                        `${enterprisePath}/jobs/${job.id}/run`,
                        {},
                        "Processing pass finished. Inspect the durable state, checkpoint, and any errors below.",
                      )
                    }
                  >
                    <Play size={13} />
                    Run processing pass
                  </button>
                  <button
                    className="button small"
                    disabled={
                      !token ||
                      !!action.busy ||
                      ![
                        "failed",
                        "retry_wait",
                        "dead_letter",
                        "partial_failure",
                        "succeeded_with_errors",
                      ].includes(job.status)
                    }
                    onClick={() =>
                      action.run(
                        `${enterprisePath}/jobs/${job.id}/retry`,
                        {},
                        "Retry requested within the connector backoff policy.",
                      )
                    }
                  >
                    <RotateCcw size={13} />
                    Retry failed job
                  </button>
                </div>
              </article>
            ))}
            {!items.length && (
              <Empty>
                No ingestion jobs have been created for your authorized scope.
              </Empty>
            )}
          </div>
        </State>
      </Panel>
      <Panel
        title="Ingestion error and dead-letter queue"
        description="Failure isolation preserves source evidence; retries create bounded reprocessing jobs"
      >
        <State
          {...deadLetters}
          loading={deadLetters.loading && !deadLetters.data}
        >
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Stage / error</th>
                  <th>Job / source version</th>
                  <th>Recorded</th>
                  <th>Recovery</th>
                </tr>
              </thead>
              <tbody>
                {recordItems(deadLetters.data).map((letter: any) => (
                  <tr key={letter.id}>
                    <td>
                      {label(letter.stage)} · {label(letter.error_code)}
                      <div className="cell-sub claim-value">
                        {letter.error_detail}
                      </div>
                    </td>
                    <td className="mono">
                      {letter.job_id}
                      <div className="cell-sub">
                        {letter.source_version_id ||
                          "Retrieval failed before content staging"}
                      </div>
                    </td>
                    <td>{date(letter.created_at)}</td>
                    <td>
                      <button
                        className="button small"
                        disabled={
                          !token || !!letter.resolved_at || !!action.busy
                        }
                        onClick={() =>
                          action.run(
                            `${enterprisePath}/dead-letters/${letter.id}/retry`,
                            {},
                            "Bounded reprocessing job created for the selected error record.",
                          )
                        }
                      >
                        Reprocess error record
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!recordItems(deadLetters.data).length && (
            <Empty>
              No dead-letter record is present in your authorized source scope.
            </Empty>
          )}
        </State>
      </Panel>
    </>
  );
}

function JobCheckpoint({ id }: { id: string }) {
  const [open, setOpen] = useState(false),
    api = useApi(
      open ? `${enterprisePath}/jobs/${encodeURIComponent(id)}` : null,
    );
  return (
    <details onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>Checkpoint, operational metrics, and errors</summary>
      {open && (
        <State {...api}>
          <pre>
            {JSON.stringify(
              {
                checkpoints: api.data?.checkpoints,
                cursor: api.data?.cursor,
                metrics: api.data?.metrics,
                error: api.data?.error,
                next_attempt_at: api.data?.next_attempt_at,
              },
              null,
              2,
            )}
          </pre>
        </State>
      )}
    </details>
  );
}
