export type EvidenceSpan = { start: number; end: number; quote?: string };

/** Source offsets are Unicode code points, matching the Python extraction API. */
export function evidenceSegments(text: string, spans: EvidenceSpan[]) {
  const points = Array.from(text);
  const valid = spans.filter(
    (span) =>
      Number.isInteger(span.start) &&
      Number.isInteger(span.end) &&
      span.start >= 0 &&
      span.end > span.start &&
      span.end <= points.length &&
      (span.quote == null ||
        points.slice(span.start, span.end).join("") === span.quote),
  );
  const boundaries = [
    ...new Set([
      0,
      points.length,
      ...valid.flatMap((span) => [span.start, span.end]),
    ]),
  ].sort((a, b) => a - b);
  return boundaries.slice(0, -1).map((start, index) => ({
    start,
    end: boundaries[index + 1],
    text: points.slice(start, boundaries[index + 1]).join(""),
    highlighted: valid.some(
      (span) => span.start <= start && span.end >= boundaries[index + 1],
    ),
  }));
}

export function parseJsonObject(
  value: string,
  label = "Configuration",
): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error(`${label} must be valid JSON.`);
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
    throw new Error(`${label} must be a JSON object.`);
  return parsed as Record<string, unknown>;
}

export const recordItems = (value: any): any[] =>
  Array.isArray(value) ? value : Array.isArray(value?.items) ? value.items : [];
export function scopeLabel(value: unknown): string {
  return Array.isArray(value)
    ? value.length
      ? value.join(", ")
      : "No scope supplied"
    : value == null
      ? "Not configured"
      : typeof value === "object"
        ? JSON.stringify(value)
        : String(value);
}

export function proposalClaims(proposal: any): any[] {
  if (Array.isArray(proposal?.claims)) return proposal.claims;
  if (Array.isArray(proposal?.facts)) return proposal.facts;
  const payload =
    proposal?.payload ||
    proposal?.proposed_record ||
    proposal?.canonical_payload ||
    {};
  return Object.entries(payload).map(([field, value]) => ({
    field,
    value,
    evidence: proposal?.evidence?.[field] || [],
    verification_status:
      proposal?.status === "approved"
        ? "human_reviewed_synthetic"
        : proposal?.verification || "unverified",
  }));
}
