import { describe, expect, it } from "vitest";

import { jsonlDataChanged, parseJsonl, searchRecords } from "./jsonl";

const SAMPLE = [
  JSON.stringify({ prompt: "桜の特徴", answer: "美しい花", mode: "thinking", category: "国語" }),
  JSON.stringify({ prompt: "1+1", answer: "2", mode: "nothinking", category: "数学" }),
  "not-json",
  "",
  JSON.stringify({ prompt: "雪の歌", answer: "白銀", mode: "thinking", category: "国語" }),
].join("\n");

describe("parseJsonl", () => {
  it("parses valid lines and skips garbage", () => {
    const recs = parseJsonl(SAMPLE);
    expect(recs).toHaveLength(3);
    expect(recs[0].prompt).toBe("桜の特徴");
  });

  it("returns empty for empty input", () => {
    expect(parseJsonl("")).toEqual([]);
  });
});

describe("searchRecords", () => {
  const recs = parseJsonl(SAMPLE);

  it("matches prompt text case-insensitively", () => {
    const r = searchRecords(recs, { query: "桜" });
    expect(r).toHaveLength(1);
    expect(r[0].prompt).toBe("桜の特徴");
  });

  it("matches answer text", () => {
    const r = searchRecords(recs, { query: "白銀" });
    expect(r).toHaveLength(1);
  });

  it("filters by mode", () => {
    const r = searchRecords(recs, { query: "", mode: "thinking" });
    expect(r).toHaveLength(2);
  });

  it("filters by category", () => {
    const r = searchRecords(recs, { query: "", category: "数学" });
    expect(r).toHaveLength(1);
  });

  it("combines filters and query", () => {
    const r = searchRecords(recs, { query: "歌", mode: "thinking", category: "国語" });
    expect(r).toHaveLength(1);
    expect(r[0].prompt).toBe("雪の歌");
  });

  it("empty query returns all", () => {
    expect(searchRecords(recs, { query: "" })).toHaveLength(3);
  });
});

describe("jsonlDataChanged", () => {
  it("detects length changes", () => {
    const prev = parseJsonl(SAMPLE);
    const next = [...prev, { prompt: "new", answer: "x" }];
    expect(jsonlDataChanged(prev, next)).toBe(true);
  });

  it("returns false for identical data", () => {
    const rows = parseJsonl(SAMPLE);
    expect(jsonlDataChanged(rows, rows)).toBe(false);
  });
});
