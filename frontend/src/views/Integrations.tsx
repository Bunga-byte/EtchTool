import { ChevronDown, Database, Upload } from "lucide-react";
import { useState } from "react";
import { mutate, useApi } from "../api";
import { Badge, Empty, Field, Notice, Panel, State } from "../components";
import { asItems, date, label, formatNumber as num } from "../utils";
import { EnterpriseWorkspace } from "../enterprise/EnterpriseWorkspace";

export function Integrations({ token }: { token: string }) {
  const [workspace, setWorkspace] = useState("files");
  return (
    <>
      <div
        className="integration-workspace-tabs"
        role="tablist"
        aria-label="Integration management workspaces"
      >
        <button
          role="tab"
          aria-selected={workspace === "files"}
          className={workspace === "files" ? "active" : ""}
          onClick={() => setWorkspace("files")}
        >
          File adapters & quality
        </button>
        <button
          role="tab"
          aria-selected={workspace === "enterprise"}
          className={workspace === "enterprise" ? "active" : ""}
          onClick={() => setWorkspace("enterprise")}
        >
          Enterprise handoff workspace
        </button>
      </div>
      {workspace === "files" ? (
        <FileIntegrations token={token} />
      ) : (
        <EnterpriseWorkspace token={token} />
      )}
    </>
  );
}

function FileIntegrations({ token }: { token: string }) {
  const api = useApi("/api/integrations");
  const quality = useApi("/api/quality");
  const [expanded, setExpanded] = useState("");
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [decisions, setDecisions] = useState<Record<string, string>>({});
  const [messages, setMessages] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState("");
  const connectors = asItems(api.data);
  const conflicts = asItems(quality.data?.conflicts || quality.data);

  async function resolve(id: string) {
    setSaving(id);
    try {
      const result = await mutate(`/api/quality/${id}/resolve`, token, {
        decision: decisions[id] || "defer",
        note: notes[id],
      });
      setMessages((m) => ({
        ...m,
        [id]:
          result.note ||
          (result.status === "unresolved"
            ? "Review recorded. Conflict remains unresolved pending more evidence."
            : "Source decision recorded. Physical installation state remains contested pending approved lifecycle correction."),
      }));
      quality.reload();
      window.dispatchEvent(new Event("frip-refresh"));
    } catch (e) {
      setMessages((m) => ({ ...m, [id]: (e as Error).message }));
    } finally {
      setSaving("");
    }
  }

  return (
    <State {...api} loading={api.loading && !api.data}>
      <Notice>
        <strong>No Samsung or Lam enterprise system is connected.</strong>{" "}
        File-backed adapters ingest typed synthetic fixtures. Real integration
        requires approved internal schemas, authentication, authorization, and
        engineering review.
      </Notice>
      <div className="connector-grid">
        {connectors.map((c: any, i: number) => (
          <article className="panel connector-card" key={c.id || i}>
            <div className="connector-header">
              <span className="connector-icon">
                <Database size={21} />
              </span>
              <Badge value={c.status || "file-backed"} />
            </div>
            <h2>{c.name || c.source || c.id}</h2>
            <p>
              {c.description ||
                c.scope ||
                "Independent adapter boundary for authorized future sources."}
            </p>
            <dl className="connector-stats">
              <Field
                name="Source mode"
                value={label(c.mode || c.kind || "Synthetic file")}
              />
              <Field
                name="Imported records"
                value={num(c.record_count ?? c.records ?? c.count, 0)}
              />
              <Field
                name="Last ingestion"
                value={date(c.last_sync || c.last_ingestion)}
              />
              <Field name="Enterprise connection" value="Not connected" />
            </dl>
            <button
              className="text-link"
              aria-expanded={expanded === String(c.id || i)}
              onClick={() =>
                setExpanded(
                  expanded === String(c.id || i) ? "" : String(c.id || i),
                )
              }
            >
              Adapter details <ChevronDown size={14} />
            </button>
            {expanded === String(c.id || i) && (
              <div className="adapter-details">
                <p>
                  <strong>Schema:</strong>{" "}
                  {label(
                    c.schema_version || c.schema || "Typed CSV / JSON records",
                  )}
                </p>
                <p>
                  <strong>Authorization:</strong>{" "}
                  {label(
                    c.authorization ||
                      "Source-scoped editor/admin access required for import",
                  )}
                </p>
                <p>
                  <strong>Quality:</strong>{" "}
                  {label(
                    c.errors ||
                      c.mapping_errors ||
                      "Schema validation and deduplication on ingestion",
                  )}
                </p>
                <p>
                  Production endpoint, approved field mapping, identity mapping,
                  source of authority, retention, and synchronization contract
                  must be supplied internally.
                </p>
              </div>
            )}
          </article>
        ))}
      </div>
      <SyntheticImport
        token={token}
        connectors={connectors}
        onImported={() => {
          api.reload();
          quality.reload();
        }}
      />
      <Panel
        title="Source reconciliation queue"
        description="Conflicting claims remain visible; arrival time does not establish authority"
      >
        <State {...quality}>
          {conflicts.length ? (
            <div className="conflict-list">
              {conflicts.map((c: any) => {
                const claims = c.claims ||
                  c.records || [
                    { source: c.source_a, value: c.value_a, ...c.record_a },
                    { source: c.source_b, value: c.value_b, ...c.record_b },
                  ];
                return (
                  <div className="conflict-card" key={c.id}>
                    <div className="conflict-heading">
                      <div>
                        <span className="eyebrow">{c.id}</span>
                        <h3>
                          {c.title ||
                            c.description ||
                            label(c.field) ||
                            "Conflicting source records"}
                        </h3>
                      </div>
                      <Badge value={c.status || "unresolved"} />
                    </div>
                    <p>
                      {c.detail ||
                        c.reason ||
                        c.message ||
                        "Preserved source records disagree about physical installation state."}
                    </p>
                    <div className="claim-grid">
                      {claims.map((r: any, i: number) => (
                        <div key={i}>
                          <strong>
                            Claim {i === 0 ? "A" : "B"} ·{" "}
                            {label(r.source || r.source_system)}
                          </strong>
                          <p className="mono">
                            {label(r.value || r.claim || r.record)}
                          </p>
                          <small>
                            Effective {date(r.effective_at || r.timestamp)}
                          </small>
                        </div>
                      ))}
                    </div>
                    <details>
                      <summary>Inspect original conflict metadata</summary>
                      <pre>{JSON.stringify(c, null, 2)}</pre>
                    </details>
                    {c.status !== "resolved" && (
                      <div className="conflict-review">
                        <label htmlFor={`decision-${c.id}`}>
                          Source decision
                        </label>
                        <select
                          id={`decision-${c.id}`}
                          value={decisions[c.id] || "defer"}
                          onChange={(e) =>
                            setDecisions({
                              ...decisions,
                              [c.id]: e.target.value,
                            })
                          }
                        >
                          <option value="defer">
                            Defer · evidence insufficient
                          </option>
                          <option value="accept_a">Accept claim A</option>
                          <option value="accept_b">Accept claim B</option>
                        </select>
                        <label htmlFor={`conflict-${c.id}`}>
                          Reconciliation note
                        </label>
                        <input
                          id={`conflict-${c.id}`}
                          value={notes[c.id] || ""}
                          onChange={(e) =>
                            setNotes({ ...notes, [c.id]: e.target.value })
                          }
                          placeholder="Document the authoritative evidence…"
                        />
                        <button
                          className="button small"
                          disabled={
                            !token ||
                            (notes[c.id]?.trim().length || 0) < 10 ||
                            saving === c.id
                          }
                          onClick={() => resolve(c.id)}
                        >
                          {saving === c.id ? "Recording…" : "Record resolution"}
                        </button>
                        {!token && (
                          <small>Authorized editor access required.</small>
                        )}
                      </div>
                    )}
                    {messages[c.id] && <p role="status">{messages[c.id]}</p>}
                  </div>
                );
              })}
            </div>
          ) : (
            <Empty>No source conflicts reported.</Empty>
          )}
        </State>
      </Panel>
      {!!quality.data?.issues?.length && (
        <Panel
          title="Data-quality observations"
          description="Known gaps and unverified specifications"
        >
          <div className="record-list">
            {quality.data.issues.map((issue: any, i: number) => (
              <div className="record" key={i}>
                <div>
                  <strong>{label(issue.code)}</strong>
                  <p>{issue.message}</p>
                  {issue.chamber_id && <small>{issue.chamber_id}</small>}
                </div>
              </div>
            ))}
          </div>
        </Panel>
      )}
      <Notice>
        Raw imports are retained for audit and deduplication. Source priority
        must be explicitly approved before conflicting values can be reconciled.
      </Notice>
    </State>
  );
}

function SyntheticImport({
  token,
  connectors,
  onImported,
}: {
  token: string;
  connectors: any[];
  onImported: () => void;
}) {
  const [source, setSource] = useState("maintenance");
  const [contents, setContents] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");

  async function importRecords() {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const parsed = JSON.parse(contents);
      const records = Array.isArray(parsed) ? parsed : parsed.records;
      if (!Array.isArray(records) || !records.length)
        throw new Error(
          "Supply a JSON record array or an object with a nonempty records array.",
        );
      if (records.length > 10000)
        throw new Error("Batches are limited to 10,000 records.");
      if (records.some((r: any) => r.synthetic !== true))
        throw new Error(
          "Every record must attest synthetic: true. Do not upload enterprise or production data.",
        );
      const response = await mutate(
        `/api/integrations/${source}/import`,
        token,
        { records, page_size: 1000 },
      );
      setResult(response);
      onImported();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function readFile(file: File | undefined) {
    if (!file) return;
    if (file.size > 4_000_000) {
      setError("Use a JSON file under 4 MB.");
      return;
    }
    setContents(await file.text());
    setResult(null);
    setError("");
  }

  return (
    <Panel
      title="Import synthetic source records"
      description="Validated JSON batches are staged for audit; they do not overwrite physical equipment history"
    >
      <div className="import-form">
        <Notice>
          Import only fictional FRIP interchange records. Approved field
          mappings and reconciliation are required before staged records become
          domain changes. See repository fixtures for examples.
        </Notice>
        <div className="import-controls">
          <label htmlFor="import-source">
            Adapter source
            <select
              id="import-source"
              value={source}
              onChange={(e) => setSource(e.target.value)}
            >
              {connectors.map((c: any) => (
                <option key={c.id} value={c.id}>
                  {c.name || c.id}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor="import-file">
            Synthetic JSON file
            <input
              id="import-file"
              type="file"
              accept=".json,application/json"
              onChange={(e) => readFile(e.target.files?.[0])}
            />
          </label>
        </div>
        <label htmlFor="import-records">JSON records</label>
        <textarea
          id="import-records"
          rows={5}
          value={contents}
          onChange={(e) => setContents(e.target.value)}
          placeholder='[{"source_id":"SYN-…", "synthetic":true, …}]'
          spellCheck={false}
        />
        <button
          className="button primary"
          onClick={importRecords}
          disabled={!token || !contents.trim() || busy}
        >
          <Upload size={15} />
          {busy ? "Validating batch…" : "Validate and stage records"}
        </button>
        {!token && (
          <small>
            Viewer mode. A source-authorized editor/admin token is required for
            import.
          </small>
        )}
        {error && (
          <p className="inline-error" role="alert">
            {error}
          </p>
        )}
        {result && (
          <div className="import-result" role="status">
            <strong>
              {result.records?.length || 0} records staged ·{" "}
              {result.duplicates || 0} duplicates · {result.errors?.length || 0}{" "}
              validation errors
            </strong>
            <p>{result.materialization}</p>
            {result.next_cursor && (
              <p>
                Additional records remain in the batch. Use the paginated API
                workflow documented in the integration guide to continue from
                the returned cursor.
              </p>
            )}
            <details>
              <summary>Inspect ingestion result and row errors</summary>
              <pre>{JSON.stringify(result, null, 2)}</pre>
            </details>
          </div>
        )}
      </div>
    </Panel>
  );
}
