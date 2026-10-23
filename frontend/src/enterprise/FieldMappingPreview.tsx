import { useState } from "react";
import { mutate } from "../api";
import { Badge, Empty, Notice, Panel } from "../components";
import { label } from "../utils";
import { DocumentEvidence, enterprisePath } from "./shared";
import { parseJsonObject, proposalClaims } from "./utils";

/** A source-authorized extraction dry run; no proposal or canonical mutation. */
export function FieldMappingPreview({
  document,
  token,
}: {
  document: any;
  token: string;
}) {
  const [mapping, setMapping] = useState("{}"),
    [result, setResult] = useState<any>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function preview() {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const fieldMapping = parseJsonObject(mapping, "Field mapping");
      if (
        Object.entries(fieldMapping).some(
          ([source, target]) =>
            !source.trim() || typeof target !== "string" || !target.trim(),
        )
      )
        throw new Error(
          "Map each nonempty source label to a nonempty canonical field name. Values must be strings.",
        );
      const response = await mutate(
        `${enterprisePath}/sources/${encodeURIComponent(document.source_id)}/mapping-preview`,
        token,
        { source_version_id: document.id, field_mapping: fieldMapping },
      );
      if (
        response.dry_run !== true ||
        response.canonical_records_changed !== false
      )
        throw new Error(
          "The response did not confirm a read-only dry run. Inspect the server contract before proceeding.",
        );
      setResult(response);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel
      title="Field mapping preview"
      description="Run deterministic extraction against retained source text without saving or promoting records"
    >
      <div className="enterprise-form">
        <label htmlFor="document-field-mapping">Field mapping (JSON)</label>
        <textarea
          id="document-field-mapping"
          value={mapping}
          onChange={(event) => setMapping(event.target.value)}
          rows={4}
          spellCheck={false}
        />
        <small>
          Map source labels to canonical extraction fields, for example{" "}
          {
            '{"New serial":"component_serial","Old serial":"old_component_serial"}'
          }
          . An empty object uses the parser’s built-in label mappings.
          Unsupported canonical targets are rejected.
        </small>
        <button
          className="button"
          disabled={busy || !document.id || !document.source_id}
          onClick={preview}
        >
          {busy ? "Previewing extraction…" : "Preview field mapping"}
        </button>
        {error && (
          <p className="enterprise-error" role="alert">
            {error}
          </p>
        )}
      </div>
      {result && (
        <>
          <Notice>
            <strong>Read-only dry run.</strong> No canonical records changed.
            These preview proposals are not saved or approved.
          </Notice>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Proposed record kind</th>
                  <th>Canonical claim</th>
                  <th>Extracted value</th>
                  <th>Verification / extraction issues</th>
                </tr>
              </thead>
              <tbody>
                {(result.proposals || []).flatMap(
                  (proposal: any, index: number) =>
                    proposalClaims(proposal).map((claim: any) => (
                      <tr key={`${index}-${claim.field}`}>
                        <td>{label(proposal.kind)}</td>
                        <td>{label(claim.field)}</td>
                        <td className="claim-value">{label(claim.value)}</td>
                        <td>
                          <Badge
                            value={proposal.verification || "unverified"}
                          />
                          <div className="cell-sub claim-value">
                            {proposal.issues?.length
                              ? proposal.issues.join(" · ")
                              : "No extraction issues reported"}
                          </div>
                        </td>
                      </tr>
                    )),
                )}
              </tbody>
            </table>
          </div>
          {!result.proposals?.length && (
            <Empty>
              No supported engineering proposal was extracted with this mapping.
              Inspect source labels, required fields, and parser issues.
            </Empty>
          )}
          <details className="mapping-preview-evidence">
            <summary>
              Inspect preview evidence spans in the original text
            </summary>
            <DocumentEvidence
              document={document}
              claims={(result.proposals || []).flatMap(proposalClaims)}
            />
            <pre>{JSON.stringify(result.proposals, null, 2)}</pre>
          </details>
        </>
      )}
    </Panel>
  );
}
