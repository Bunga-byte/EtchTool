import { useEffect, useState } from "react";
import { useApi } from "../api";
import { Badge, Empty, Notice, Panel, State } from "../components";
import { date, label, toUTC } from "../utils";
import {
  ActionFeedback,
  enterprisePath,
  useEnterpriseAction,
  ViewerNote,
} from "./shared";
import { parseJsonObject, recordItems } from "./utils";

export function IdentityWorkspace({ token }: { token: string }) {
  const api = useApi(`${enterprisePath}/aliases`),
    sources = useApi(`${enterprisePath}/sources`),
    [source, setSource] = useState(""),
    [entityType, setEntityType] = useState("tool"),
    [external, setExternal] = useState(""),
    [canonical, setCanonical] = useState(""),
    [start, setStart] = useState("2026-01-01T00:00"),
    [end, setEnd] = useState(""),
    [evidence, setEvidence] = useState("{}"),
    [note, setNote] = useState(""),
    [error, setError] = useState("");
  const sourceItems = recordItems(sources.data),
    action = useEnterpriseAction(token, api.reload),
    items = recordItems(api.data);
  useEffect(() => {
    if (!source && sourceItems[0]) setSource(sourceItems[0].id);
  }, [sources.data, source]);
  async function create() {
    setError("");
    try {
      const reference = parseJsonObject(evidence, "Alias evidence");
      if (!Object.keys(reference).length)
        throw new Error("Provide an explicit supporting source reference.");
      await action.run(
        `${enterprisePath}/aliases`,
        {
          source_id: source,
          entity_type: entityType,
          external_id: external,
          canonical_id: canonical,
          valid_from: toUTC(start),
          valid_to: end ? toUTC(end) : null,
          evidence: [reference],
          note,
        },
        "Effective-dated identity mapping recorded. Matching remains source-scoped and auditable.",
      );
    } catch (reason) {
      setError((reason as Error).message);
    }
  }
  return (
    <>
      <Notice>
        <strong>Exact identity resolution.</strong> Equipment aliases,
        serialized identities, and physical positions are mapped explicitly.
        Similar part descriptions are not sufficient to merge components.
      </Notice>
      <Panel
        title="Source-scoped identity mappings"
        description="Effective intervals and supporting evidence preserve cross-system distinctions"
      >
        <State {...api} loading={api.loading && !api.data}>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Source / entity</th>
                  <th>External identifier</th>
                  <th>Canonical identifier</th>
                  <th>Effective interval</th>
                  <th>Verification</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item: any) => (
                  <tr key={item.id}>
                    <td>
                      {item.source_id}
                      <div className="cell-sub">{label(item.entity_type)}</div>
                    </td>
                    <td className="mono">{item.external_id}</td>
                    <td className="mono">{item.canonical_id}</td>
                    <td>
                      {date(item.valid_from)}
                      <div className="cell-sub">
                        Until{" "}
                        {item.valid_to ? date(item.valid_to) : "open-ended"}
                      </div>
                    </td>
                    <td>
                      <Badge value={item.verification_status} />
                      <details>
                        <summary>Matching evidence</summary>
                        <pre>{JSON.stringify(item.evidence, null, 2)}</pre>
                      </details>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!items.length && (
            <Empty>No identity mapping is authorized for this scope.</Empty>
          )}
        </State>
      </Panel>
      <Panel
        title="Register an evidence-backed alias"
        description="Canonical entity existence, authorization, and overlap are checked by the server"
      >
        <div className="enterprise-form">
          <div className="enterprise-form-grid">
            <label>
              Alias source
              <select
                aria-label="Alias source"
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
              Entity type
              <select
                aria-label="Alias entity type"
                value={entityType}
                onChange={(event) => setEntityType(event.target.value)}
              >
                <option value="tool">Tool</option>
                <option value="chamber">Chamber</option>
                <option value="component">Serialized component</option>
                <option value="position">Physical position</option>
                <option value="definition">Component definition</option>
              </select>
            </label>
            <label>
              External identifier
              <input
                aria-label="Alias external identifier"
                value={external}
                onChange={(event) => setExternal(event.target.value)}
              />
            </label>
            <label>
              Canonical identifier
              <input
                aria-label="Alias canonical identifier"
                value={canonical}
                onChange={(event) => setCanonical(event.target.value)}
              />
            </label>
            <label>
              Valid from (UTC)
              <input
                aria-label="Alias valid from (UTC)"
                type="datetime-local"
                value={start}
                onChange={(event) => setStart(event.target.value)}
              />
            </label>
            <label>
              Valid to (UTC, optional)
              <input
                aria-label="Alias valid to (UTC)"
                type="datetime-local"
                value={end}
                onChange={(event) => setEnd(event.target.value)}
              />
            </label>
          </div>
          <label htmlFor="alias-evidence">
            Supporting evidence (JSON reference)
          </label>
          <textarea
            id="alias-evidence"
            value={evidence}
            onChange={(event) => setEvidence(event.target.value)}
            rows={3}
            spellCheck={false}
          />
          <label htmlFor="alias-review-note">
            Identity mapping review note
          </label>
          <textarea
            id="alias-review-note"
            rows={2}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Explain the exact source evidence linking these identities…"
          />
          <button
            className="button primary"
            disabled={
              !token ||
              !external.trim() ||
              !canonical.trim() ||
              !start ||
              note.trim().length < 10 ||
              !!action.busy
            }
            onClick={create}
          >
            Register identity mapping
          </button>
          <ViewerNote token={token} />
          {error && (
            <p className="enterprise-error" role="alert">
              {error}
            </p>
          )}
          <ActionFeedback {...action} />
        </div>
      </Panel>
    </>
  );
}
