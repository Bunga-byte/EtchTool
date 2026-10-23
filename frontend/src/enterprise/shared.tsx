import { useState } from "react";
import { mutate } from "../api";
import { Badge, Empty, Field } from "../components";
import { date, label } from "../utils";
import { evidenceSegments } from "./utils";
import type { EvidenceSpan } from "./utils";

export const enterprisePath = "/api/enterprise";

export function useEnterpriseAction(token: string, after?: () => void) {
  const [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [message, setMessage] = useState("");
  async function run(path: string, body: unknown, messageText: string) {
    setBusy(path);
    setError("");
    setMessage("");
    try {
      const result = await mutate(path, token, body);
      setMessage(result.message || result.note || messageText);
      after?.();
      return result;
    } catch (reason) {
      setError((reason as Error).message);
      return null;
    } finally {
      setBusy("");
    }
  }
  return {
    busy,
    error,
    message,
    run,
    clear: () => {
      setError("");
      setMessage("");
    },
  };
}

export function ActionFeedback({
  error,
  message,
}: {
  error: string;
  message: string;
}) {
  return (
    <>
      {error && (
        <p className="enterprise-error" role="alert">
          {error}
        </p>
      )}
      {message && (
        <p className="enterprise-success" role="status">
          {message}
        </p>
      )}
    </>
  );
}
export function ViewerNote({ token }: { token: string }) {
  return !token ? (
    <p className="enterprise-viewer">
      Read-only viewer. An authorized, source-scoped engineering token is
      required for changes.
    </p>
  ) : null;
}

export function Metadata({
  record,
  fields,
}: {
  record: any;
  fields: [string, string][];
}) {
  return (
    <dl className="field-grid wide-fields">
      {fields.map(([key, name]) => (
        <Field
          key={key}
          name={name}
          value={
            key.endsWith("_at") || key.endsWith("_timestamp")
              ? date(record?.[key])
              : label(record?.[key])
          }
        />
      ))}
    </dl>
  );
}

export function EvidenceText({
  text,
  spans = [],
}: {
  text: string;
  spans?: EvidenceSpan[];
}) {
  return (
    <pre className="original-evidence">
      {evidenceSegments(text, spans).map((segment) =>
        segment.highlighted ? (
          <mark
            key={segment.start}
            data-span-start={segment.start}
            data-span-end={segment.end}
          >
            {segment.text}
          </mark>
        ) : (
          <span key={segment.start}>{segment.text}</span>
        ),
      )}
    </pre>
  );
}

export function DocumentEvidence({
  document,
  claims = [],
}: {
  document: any;
  claims?: any[];
}) {
  const parsed =
    document?.parsed ||
    document?.parsed_document ||
    document?.structured_payload ||
    document;
  const blocks = parsed?.blocks || parsed?.text_blocks || [];
  if (!blocks.length && !parsed?.text && !parsed?.content_text)
    return (
      <Empty>
        No extracted source text is available. Inspect parse errors and
        supported document types.
      </Empty>
    );
  return (
    <div className="document-evidence">
      <div className="evidence-provenance">
        <strong>
          {document.title ||
            document.filename ||
            document.original_id ||
            document.id}
        </strong>
        <Badge
          value={document.parse_status || document.status || "immutable source"}
        />
        <small>
          {document.source_id} · Source record{" "}
          {document.original_id ||
            document.source_record_id ||
            document.source_identifier ||
            "Unknown"}{" "}
          · Revision{" "}
          {document.revision || document.source_revision || "Unknown"}
        </small>
      </div>
      {blocks.length ? (
        blocks.map((block: any, index: number) => {
          const spans = claims
            .flatMap((claim: any) => claim.evidence || claim.spans || [])
            .filter(
              (span: any) =>
                span.block_id === block.id || span.block_index === index,
            )
            .map((span: any) => ({
              start: (span.start ?? span.start_offset) - (block.start || 0),
              end: (span.end ?? span.end_offset) - (block.start || 0),
              quote: span.quote || span.text,
            }));
          return (
            <section className="evidence-block" key={block.id || index}>
              <div>
                <span>
                  Block {index + 1} · global offsets {block.start}–{block.end}
                </span>
                {block.page != null && <span>Page {block.page}</span>}
                {block.row != null && <span>Row {block.row}</span>}
                {block.sheet && <span>Sheet {block.sheet}</span>}
                <span>
                  {block.locator ||
                    block.location ||
                    block.kind ||
                    "Extracted text"}
                </span>
              </div>
              <EvidenceText
                text={block.text || block.content || ""}
                spans={spans}
              />
            </section>
          );
        })
      ) : (
        <EvidenceText text={parsed.text || parsed.content_text} />
      )}
    </div>
  );
}
