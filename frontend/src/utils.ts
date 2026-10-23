export const formatNumber = (value: unknown, digits = 1): string =>
  typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("en-US", { maximumFractionDigits: digits })
    : "Unknown";
export const label = (value: unknown): string =>
  value == null || value === ""
    ? "Unknown"
    : typeof value === "object"
      ? JSON.stringify(value)
      : String(value).replace(/_/g, " ");
export const date = (value: unknown): string => {
  if (!value) return "Not recorded";
  const d = new Date(String(value));
  return Number.isNaN(d.valueOf())
    ? String(value)
    : d.toLocaleString("en-US", {
        timeZone: "UTC",
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }) + " UTC";
};
export const asItems = (data: any): any[] =>
  Array.isArray(data) ? data : Array.isArray(data?.items) ? data.items : [];
export const matches = (record: any, query: string): boolean =>
  !query.trim() ||
  [
    record.name,
    record.part_number,
    record.serial_number,
    record.revision,
    record.subsystem,
    record.tool_name,
    record.chamber_name,
  ].some((x) =>
    String(x ?? "")
      .toLowerCase()
      .includes(query.trim().toLowerCase()),
  );
export const completeness = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value)
    ? Math.max(0, Math.min(1, value))
    : null;
export const toUTC = (localInput: string): string =>
  localInput ? localInput + (localInput.length === 16 ? ":00Z" : "Z") : "";
