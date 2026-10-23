import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { useApi } from "../api";
import { Badge, Empty, Notice, Panel, State } from "../components";
import { date, label } from "../utils";
import {
  ActionFeedback,
  DocumentEvidence,
  enterprisePath,
  Metadata,
  useEnterpriseAction,
  ViewerNote,
} from "./shared";
import { parseJsonObject, proposalClaims, recordItems } from "./utils";

export function ProposalsWorkspace({
  token,
  selected,
  setSelected,
  onDocument,
}: {
  token: string;
  selected: string;
  setSelected: (id: string) => void;
  onDocument: (id: string) => void;
}) {
  const api = useApi(`${enterprisePath}/proposals`),
    preview = useApi(
      selected
        ? `${enterprisePath}/proposals/${encodeURIComponent(selected)}/preview`
        : null,
    ),
    history = useApi(
      selected
        ? `${enterprisePath}/proposals/${encodeURIComponent(selected)}`
        : null,
    ),
    [filter, setFilter] = useState(""),
    [decision, setDecision] = useState("approve"),
    [note, setNote] = useState(""),
    [corrections, setCorrections] = useState("{}"),
    [inputError, setInputError] = useState("");
  const action = useEnterpriseAction(token, () => {
      api.reload();
      preview.reload();
      history.reload();
    }),
    items = recordItems(api.data),
    d = preview.data,
    proposal = d?.proposal || d,
    document = d?.document || d?.source_document,
    claims = proposalClaims(proposal),
    rows = claims,
    filtered = items.filter((item: any) =>
      [
        item.id,
        item.kind,
        item.status,
        item.document_id,
        item.source_version_id,
      ].some((value) =>
        String(value || "")
          .toLowerCase()
          .includes(filter.toLowerCase()),
      ),
    );
  useEffect(() => {
    if (!selected && items[0]) setSelected(items[0].id);
  }, [api.data, selected, setSelected]);
  useEffect(() => {
    setNote("");
    setCorrections("{}");
    setDecision("approve");
    setInputError("");
    action.clear();
  }, [selected]);
  async function review() {
    setInputError("");
    try {
      const body: any = { decision, note };
      if (decision === "correct")
        body.corrections = parseJsonObject(corrections, "Corrections");
      const result = await action.run(
        `${enterprisePath}/proposals/${encodeURIComponent(selected)}/review`,
        body,
        "Engineering review recorded with original evidence retained.",
      );
      if (result) {
        if (
          decision === "correct" &&
          (result.corrected_proposal_id || result.id || result.proposal?.id)
        )
          setSelected(
            result.corrected_proposal_id || result.id || result.proposal.id,
          );
        window.dispatchEvent(new Event("frip-refresh"));
      }
    } catch (reason) {
      setInputError((reason as Error).message);
    }
  }
  return (
    <State {...api} loading={api.loading && !api.data}>
      <div className="enterprise-split">
        <Panel
          title="Engineering review queue"
          description="Staged facts, identity matches, and conflicts"
        >
          <label className="search-box enterprise-search">
            <Search size={15} />
            <input
              aria-label="Search engineering proposals"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder="Proposal, kind, status, document…"
            />
          </label>
          <div className="enterprise-record-picker">
            {filtered.map((item: any) => (
              <button
                key={item.id}
                className={selected === item.id ? "selected" : ""}
                onClick={() => setSelected(item.id)}
              >
                <div>
                  <strong>
                    {label(item.kind || item.type || "Engineering proposal")}
                  </strong>
                  <Badge value={item.status} />
                </div>
                <small className="mono">{item.id}</small>
                <small>
                  Document{" "}
                  {item.document_id || item.source_version_id || "Unknown"} ·{" "}
                  {label(item.verification_status || item.extraction_method)}
                </small>
              </button>
            ))}
            {!filtered.length && (
              <Empty>
                No proposal is available. Ingest a synthetic maintenance or
                inventory source first.
              </Empty>
            )}
          </div>
        </Panel>
        <div>
          <State
            {...preview}
            loading={
              preview.loading ||
              (!preview.error && !!proposal && proposal.id !== selected)
            }
          >
            {proposal ? (
              <>
                <Panel
                  title="Proposed canonical change"
                  description="Preview exact claims, identity matches, and validation before approving"
                >
                  <Metadata
                    record={proposal}
                    fields={[
                      ["id", "Proposal ID"],
                      ["kind", "Canonical destination"],
                      ["status", "Review status"],
                      ["extraction_method", "Extraction method"],
                      ["extraction_version", "Extraction version"],
                      ["created_at", "Proposed timestamp"],
                    ]}
                  />
                  <Notice kind="warning">
                    Extracted claims are unverified engineering interpretations.
                    Approval is an audited canonical transaction; an alarm or
                    replacement does not prove hardware failure.
                  </Notice>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Extracted claim</th>
                          <th>Proposed value</th>
                          <th>Evidence locator</th>
                          <th>Verification</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((claim: any, index: number) => (
                          <tr key={index}>
                            <td>
                              {label(
                                claim.field || claim.name || claim.fact_type,
                              )}
                            </td>
                            <td className="claim-value">
                              {label(claim.value)}
                            </td>
                            <td className="claim-evidence-quote">
                              {Array.isArray(claim.evidence) &&
                              claim.evidence.length
                                ? claim.evidence.map((span: any, i: number) => (
                                    <div key={i}>
                                      <q>{span.quote}</q>
                                      <small>
                                        {span.locator} · block {span.block_id} ·
                                        [{span.start}, {span.end})
                                      </small>
                                      <small>
                                        Source {span.original_id} · revision{" "}
                                        {span.revision} ·{" "}
                                        {span.page != null
                                          ? `page ${span.page}`
                                          : ""}
                                        {span.row != null
                                          ? ` row ${span.row}`
                                          : ""}
                                      </small>
                                    </div>
                                  ))
                                : "No exact span supplied"}
                            </td>
                            <td>
                              <Badge
                                value={
                                  claim.verification_status ||
                                  claim.status ||
                                  "unverified"
                                }
                              />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="proposal-checks">
                    <h3>Identity matching & conflict checks</h3>
                    <p>
                      {label(
                        d?.match_status ||
                          proposal.match_status ||
                          d?.validation?.status ||
                          "Review server validation below",
                      )}
                    </p>
                    <pre>
                      {JSON.stringify(
                        {
                          matches:
                            d?.matched_entities ||
                            d?.matches ||
                            proposal.matched_entities ||
                            proposal.matches,
                          conflicts: d?.conflicts || proposal.conflicts,
                          validation:
                            d?.validation_errors ||
                            d?.validation ||
                            proposal.validation_errors ||
                            proposal.validation,
                          warnings: d?.warnings,
                        },
                        null,
                        2,
                      )}
                    </pre>
                  </div>
                  {d?.can_approve === false && (
                    <Notice kind="warning">
                      Canonical approval is blocked by the current validation or
                      identity conflict. Inspect the preserved sources, register
                      the correct mapping, or correct/reject the proposal; the
                      server will revalidate every decision.
                    </Notice>
                  )}
                  {!!d?.planned_changes?.length && (
                    <div className="planned-change-list">
                      <h3>Preview of canonical changes</h3>
                      {d.planned_changes.map((change: any, index: number) => (
                        <div key={index}>
                          <strong>
                            {label(change.action)} · {label(change.entity)}
                          </strong>
                          <p>{label(change.details)}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </Panel>
                {document && (
                  <Panel
                    title="Original evidence beside extracted claims"
                    description="Highlighted spans must match the retained source text exactly"
                    action={
                      <button
                        className="text-link"
                        onClick={() =>
                          onDocument(document.id || proposal.document_id)
                        }
                      >
                        Open document record
                      </button>
                    }
                  >
                    <DocumentEvidence document={document} claims={claims} />
                  </Panel>
                )}
                <Panel
                  title="Review proposed engineering record"
                  description="The server enforces source, equipment, collection, and role boundaries"
                >
                  <div className="enterprise-form">
                    <label htmlFor="proposal-review-decision">
                      Engineering review decision
                    </label>
                    <select
                      id="proposal-review-decision"
                      value={decision}
                      onChange={(event) => setDecision(event.target.value)}
                    >
                      <option value="approve">
                        Approve validated canonical change
                      </option>
                      <option value="reject">Reject proposal</option>
                      <option value="correct">
                        Correct extracted fields and review
                      </option>
                    </select>
                    <label htmlFor="proposal-review-note">
                      Engineering review note
                    </label>
                    <textarea
                      id="proposal-review-note"
                      value={note}
                      onChange={(event) => setNote(event.target.value)}
                      rows={3}
                      placeholder="Cite the original evidence and explain your engineering decision…"
                    />
                    {decision === "correct" && (
                      <>
                        <label htmlFor="proposal-corrections">
                          Corrected fields (JSON)
                        </label>
                        <textarea
                          id="proposal-corrections"
                          value={corrections}
                          onChange={(event) =>
                            setCorrections(event.target.value)
                          }
                          rows={5}
                          spellCheck={false}
                        />
                        <small>
                          Use canonical field names from the proposed record.
                          Corrections are validated and audited; unsupported or
                          unsafe changes are rejected.
                        </small>
                      </>
                    )}
                    <button
                      className="button primary"
                      disabled={
                        !token ||
                        (decision === "approve" && d?.can_approve === false) ||
                        note.trim().length < 10 ||
                        !!action.busy ||
                        ["approved", "rejected", "superseded"].includes(
                          proposal.status,
                        )
                      }
                      onClick={review}
                    >
                      {action.busy
                        ? "Recording review…"
                        : "Submit engineering review"}
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
                  title="Engineering decision history"
                  description="Reviewer identity, evidence-based notes, and retained before/after decisions"
                >
                  <State
                    {...history}
                    loading={
                      history.loading ||
                      (!history.error &&
                        !!history.data &&
                        history.data.id !== selected)
                    }
                  >
                    <div className="record-list">
                      {(history.data?.reviews || []).map((record: any) => (
                        <div className="record" key={record.id}>
                          <div>
                            <strong>
                              {label(record.decision)} · {record.actor}
                            </strong>
                            <p>{record.note}</p>
                            <small>{date(record.created_at)}</small>
                            <details>
                              <summary>Audited before / after record</summary>
                              <pre>
                                {JSON.stringify(record.before_after, null, 2)}
                              </pre>
                            </details>
                          </div>
                        </div>
                      ))}
                      {!history.data?.reviews?.length && (
                        <Empty>
                          No engineering decision has been recorded for this
                          proposal.
                        </Empty>
                      )}
                    </div>
                  </State>
                </Panel>
              </>
            ) : (
              <Empty>
                Select a proposed record to inspect its original evidence and
                validation.
              </Empty>
            )}
          </State>
        </div>
      </div>
    </State>
  );
}
