import { describe, expect, it } from "vitest";
import { evidenceSegments, parseJsonObject } from "./utils";

describe("original engineering evidence", () => {
  it("marks only the exact supported quote without changing original source text", () => {
    const source = "Removed SYN-A; installed SYN-B.";
    const segments = evidenceSegments(source, [
      { start: 8, end: 13, quote: "SYN-A" },
    ]);
    expect(segments.map((segment) => segment.text).join("")).toBe(source);
    expect(
      segments
        .filter((segment) => segment.highlighted)
        .map((segment) => segment.text),
    ).toEqual(["SYN-A"]);
  });
  it("does not highlight a mismatched quote or out-of-bounds extraction", () => {
    const segments = evidenceSegments("serial A", [
      { start: 0, end: 8, quote: "serial B" },
      { start: 5, end: 100 },
    ]);
    expect(segments.some((segment) => segment.highlighted)).toBe(false);
  });
  it("uses Python-compatible Unicode code point offsets", () => {
    const segments = evidenceSegments("🔧 serial A", [
      { start: 9, end: 10, quote: "A" },
    ]);
    expect(segments.find((segment) => segment.highlighted)?.text).toBe("A");
  });
  it("retains overlapping source spans without duplicate text", () => {
    const segments = evidenceSegments("abcdefgh", [
      { start: 1, end: 5 },
      { start: 3, end: 7 },
    ]);
    expect(segments.map((segment) => segment.text).join("")).toBe("abcdefgh");
    expect(
      segments
        .filter((segment) => segment.highlighted)
        .map((segment) => segment.text)
        .join(""),
    ).toBe("bcdefg");
  });
});
describe("operator-entered structured configuration", () => {
  it("accepts explicit structured corrections and rejects scalars or arrays", () => {
    expect(parseJsonObject('{"serial":"SYN-B"}', "Corrections")).toEqual({
      serial: "SYN-B",
    });
    expect(() => parseJsonObject("[]", "Corrections")).toThrow(
      "Corrections must be a JSON object.",
    );
    expect(() => parseJsonObject("invalid", "Query")).toThrow(
      "Query must be valid JSON.",
    );
  });
});
