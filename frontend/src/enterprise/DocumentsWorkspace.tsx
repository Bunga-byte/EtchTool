import { useEffect, useState } from "react";
import { FileText, Search } from "lucide-react";
import { useApi } from "../api";
import { Badge, Empty, Notice, Panel, State } from "../components";
import { date, label } from "../utils";
import { DocumentEvidence, enterprisePath, Metadata } from "./shared";
import { proposalClaims, recordItems } from "./utils";
import { FieldMappingPreview } from "./FieldMappingPreview";

export function DocumentsWorkspace({
  selected,
  setSelected,
  onProposal,
  token,
}: {
  selected: string;
  setSelected: (id: string) => void;
  onProposal: (id: string) => void;
  token: string;
}) {
  const api = useApi(`${enterprisePath}/documents`),
    detail = useApi(
      selected
        ? `${enterprisePath}/documents/${encodeURIComponent(selected)}`
        : null,
    ),
    [query, setQuery] = useState(""),
    items = recordItems(api.data);
  useEffect(() => {
    if (!selected && items[0]) setSelected(items[0].id);
  }, [api.data, selected, setSelected]);
  const d = detail.data?.document || detail.data,
    proposals = detail.data?.proposals || [],
    filtered = items.filter((item: any) =>
      [
        item.title,
        item.filename,
        item.source_id,
        item.original_id,
        item.id,
      ].some((value) =>
        String(value || "")
          .toLowerCase()
          .includes(query.toLowerCase()),
      ),
    );
  return (
    <State {...api} loading={api.loading && !api.data}>
      <div className="enterprise-split">
        <Panel
          title="Retrieved source documents"
          description="Original identifiers and content revisions remain immutable"
        >
          <label className="search-box enterprise-search">
            <Search size={15} />
            <input
              aria-label="Search original documents"
              placeholder="Source, document ID, or title…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
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
                  <FileText size={15} />
                  <strong>{item.title || item.filename || item.id}</strong>
                </div>
                <small>
                  {item.source_id} · {item.original_id || item.source_record_id}
                </small>
                <small>
                  Source revision{" "}
                  {item.revision || item.source_revision || "Unknown"} ·{" "}
                  {date(item.ingested_at)}
                </small>
                <Badge
                  value={item.parse_status || item.status || "retrieved"}
                />
              </button>
            ))}
            {!filtered.length && (
              <Empty>
                No source document matches. Run a bounded ingestion job to
                retrieve synthetic evidence.
              </Empty>
            )}
          </div>
        </Panel>
        <div>
          <State
            {...detail}
            loading={
              detail.loading || (!detail.error && !!d && d.id !== selected)
            }
          >
            {d ? (
              <>
                <Panel
                  title="Original source evidence"
                  description="Extracted text preserves page, row, block, and span locators"
                >
                  <Metadata
                    record={d}
                    fields={[
                      ["source_id", "Source"],
                      ["original_id", "Original source ID"],
                      ["revision", "Source revision"],
                      ["content_hash", "Content fingerprint"],
                      ["recorded_at", "Source recorded timestamp"],
                      ["effective_at", "Source effective timestamp"],
                      ["ingested_at", "Ingestion timestamp"],
                      ["parser_version", "Parser version"],
                      ["mime_type", "Media type"],
                      ["parse_status", "Parse status"],
                    ]}
                  />
                  <DocumentEvidence
                    document={d}
                    claims={proposals.flatMap(proposalClaims)}
                  />
                </Panel>
                <FieldMappingPreview key={d.id} document={d} token={token} />
                {!!(d.parsed?.issues || d.parse_errors || d.errors)?.length && (
                  <Notice kind="warning">
                    Parse issues:{" "}
                    {label(d.parsed?.issues || d.parse_errors || d.errors)}
                  </Notice>
                )}
                <Panel
                  title="Extracted engineering proposals"
                  description="Extraction is an unverified interpretation until an authorized engineering decision"
                >
                  <div className="enterprise-linked-proposals">
                    {proposals.map((proposal: any) => (
                      <button
                        key={proposal.id}
                        className="enterprise-proposal-link"
                        onClick={() => onProposal(proposal.id)}
                      >
                        <div>
                          <strong>
                            {label(proposal.kind || proposal.type)}
                          </strong>
                          <small className="mono">{proposal.id}</small>
                        </div>
                        <Badge value={proposal.status} />
                        <span>Review proposal →</span>
                      </button>
                    ))}
                    {!proposals.length && (
                      <Empty>
                        No proposal is linked to this document. Inspect the
                        parsing job and extraction errors.
                      </Empty>
                    )}
                  </div>
                </Panel>
              </>
            ) : (
              <Empty>
                Select a retrieved source document to inspect its evidence.
              </Empty>
            )}
          </State>
        </div>
      </div>
    </State>
  );
}
