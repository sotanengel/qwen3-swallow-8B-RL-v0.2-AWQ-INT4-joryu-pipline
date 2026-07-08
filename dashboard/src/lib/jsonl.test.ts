import { describe, expect, it } from "vitest";

import {
  findRecordById,
  formatRecordMarkdown,
  inferRecordMode,
  jsonlDataChanged,
  loadCuratedJsonl,
  parseJsonl,
  recordId,
  recordLooksTruncated,
  recordsToJsonl,
  searchRecords,
  truncateText,
} from "./jsonl";

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

const THINKING_RECORD = {
  prompt: "桜の特徴",
  answer: "美しい花です",
  mode: "thinking" as const,
  category: "国語",
  style_id: "default",
  created_at: "2026-01-01T00:00:00Z",
  config_hash: "abc123",
  thinking_trace: "桜について考える…",
  model: "qwen3",
};

const NOTHINKING_RECORD = {
  prompt: "1+1",
  answer: "2",
  mode: "nothinking" as const,
  category: "数学",
  created_at: "2026-01-02T00:00:00Z",
};

describe("recordId", () => {
  it("returns the same id for the same record", () => {
    expect(recordId(THINKING_RECORD)).toBe(recordId(THINKING_RECORD));
  });

  it("returns different ids for different records", () => {
    expect(recordId(THINKING_RECORD)).not.toBe(recordId(NOTHINKING_RECORD));
  });

  it("matches distilled (mode missing) and curated (mode inferred) records", () => {
    // 蒸留 JSONL は mode 欠落、curate は thinking_trace から mode=thinking を補完する。
    const distilled = {
      prompt: "同一プロンプト",
      answer: "同一回答",
      category: "国語",
      style_id: "prose",
      created_at: "2026-07-04T01:13:00.454682+00:00",
      config_hash: "sha256-abc",
      thinking_trace: "考える",
    };
    const curated = { ...distilled, mode: "thinking" as const };
    expect(recordId(distilled)).toBe(recordId(curated));
  });
});

describe("inferRecordMode", () => {
  it("returns explicit mode when present", () => {
    expect(inferRecordMode({ prompt: "p", answer: "a", mode: "nothinking" })).toBe("nothinking");
  });

  it("infers nothinking from no_think_fallback_used", () => {
    expect(
      inferRecordMode({ prompt: "p", answer: "a", no_think_fallback_used: true }),
    ).toBe("nothinking");
  });

  it("defaults to thinking otherwise", () => {
    expect(inferRecordMode({ prompt: "p", answer: "a" })).toBe("thinking");
    expect(inferRecordMode({ prompt: "p", answer: "a", thinking_trace: "x" })).toBe("thinking");
  });
});

describe("findRecordById", () => {
  const recs = [THINKING_RECORD, NOTHINKING_RECORD];

  it("finds a record by id", () => {
    const id = recordId(THINKING_RECORD);
    expect(findRecordById(recs, id)).toEqual(THINKING_RECORD);
  });

  it("returns undefined when not found", () => {
    expect(findRecordById(recs, "nonexistent")).toBeUndefined();
  });
});

describe("recordLooksTruncated", () => {
  it("detects finish_reason length", () => {
    expect(recordLooksTruncated({ ...NOTHINKING_RECORD, finish_reason: "length" })).toBe(true);
  });

  it("detects heuristic header truncation", () => {
    expect(
      recordLooksTruncated({
        ...NOTHINKING_RECORD,
        answer: "導入\n\n## 1. 章",
      }),
    ).toBe(true);
  });
});

describe("truncateText", () => {
  it("returns short text unchanged", () => {
    expect(truncateText("hello", 80)).toBe("hello");
  });

  it("truncates long text with ellipsis", () => {
    const long = "あ".repeat(100);
    const result = truncateText(long, 80);
    expect(result).toHaveLength(81);
    expect(result.endsWith("…")).toBe(true);
  });
});

describe("formatRecordMarkdown", () => {
  it("includes metadata and answer sections", () => {
    const md = formatRecordMarkdown(NOTHINKING_RECORD);
    expect(md).toContain("## メタデータ");
    expect(md).toContain("**category**: 数学");
    expect(md).toContain("## プロンプト");
    expect(md).toContain("1+1");
    expect(md).toContain("## 回答");
    expect(md).toContain("2");
    expect(md).not.toContain("## 思考過程");
  });

  it("includes thinking section when thinking_trace is present", () => {
    const md = formatRecordMarkdown(THINKING_RECORD);
    expect(md).toContain("## 思考過程");
    expect(md).toContain("桜について考える…");
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

describe("recordsToJsonl", () => {
  it("serializes records as newline-delimited json", () => {
    const recs = parseJsonl(SAMPLE);
    const text = recordsToJsonl(recs);
    expect(text.split("\n").filter(Boolean)).toHaveLength(3);
    expect(text.endsWith("\n")).toBe(true);
  });

  it("returns empty string for no records", () => {
    expect(recordsToJsonl([])).toBe("");
  });
});

describe("loadCuratedJsonl", () => {
  it("parses curated responses from live fetch", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async () =>
      new Response(
        `${JSON.stringify({ prompt: "hq", answer: "ok" })}\n`,
        { status: 200 },
      )) as unknown as typeof fetch;
    try {
      const rows = await loadCuratedJsonl();
      expect(rows).toHaveLength(1);
      expect(rows[0].prompt).toBe("hq");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
