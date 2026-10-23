import { describe, expect, it } from "vitest";
import {
  asItems,
  completeness,
  date,
  formatNumber,
  label,
  matches,
  toUTC,
} from "./utils";

describe("engineering presentation boundaries", () => {
  it("preserves missing values as unknown instead of reporting zero exposure", () => {
    expect(formatNumber(null)).toBe("Unknown");
    expect(formatNumber(undefined)).toBe("Unknown");
    expect(formatNumber(Number.NaN)).toBe("Unknown");
    expect(formatNumber(0)).toBe("0");
    expect(label("")).toBe("Unknown");
  });
  it("keeps exposure completeness unknown when the source provides no coverage", () => {
    expect(completeness(null)).toBeNull();
    expect(completeness(undefined)).toBeNull();
    expect(completeness(0.75)).toBe(0.75);
  });
  it("interprets a historical UTC control independently of workstation timezone", () => {
    expect(toUTC("2026-01-15T12:30")).toBe("2026-01-15T12:30:00Z");
    expect(toUTC("2026-01-15T12:30:25")).toBe("2026-01-15T12:30:25Z");
    expect(toUTC("")).toBe("");
  });
  it("labels audit timestamps explicitly as UTC and preserves absent timestamps", () => {
    expect(date("2026-01-15T12:30:00Z")).toContain("12:30 UTC");
    expect(date(null)).toBe("Not recorded");
  });
  it("finds serialized identities, part revisions and locations without requiring all fields", () => {
    const component = {
      name: "Synthetic match assembly",
      serial_number: "SYN-002",
      revision: "DEMO-C",
      tool_name: "Demo tool 2",
    };
    expect(matches(component, " syn-002 ")).toBe(true);
    expect(matches(component, "demo-c")).toBe(true);
    expect(matches(component, "TOOL 2")).toBe(true);
    expect(matches(component, "SYN-001")).toBe(false);
    expect(matches({}, "missing")).toBe(false);
  });
  it("does not manufacture table rows when a collection is unavailable", () => {
    expect(asItems(null)).toEqual([]);
    expect(asItems({ items: null })).toEqual([]);
    expect(asItems({ items: [{ id: "synthetic" }] })).toEqual([
      { id: "synthetic" },
    ]);
  });
});
