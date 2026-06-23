import { describe, expect, it } from "vitest";

import { curateStatusLabel, isCurateJobActive, parseCurateJobRecord } from "./curate-jobs";

describe("parseCurateJobRecord", () => {
  it("normalizes curate job payload", () => {
    const row = parseCurateJobRecord({
      id: "abc",
      kind: "curate",
      spec: { config: "config.yaml", skip_llm: true, threshold: 0.7 },
      status: "queued",
      created_at: "2026-01-01T00:00:00Z",
      started_at: null,
      finished_at: null,
      exit_code: null,
      error: null,
    });
    expect(row.kind).toBe("curate");
    expect(row.spec.skip_llm).toBe(true);
    expect(row.spec.threshold).toBe(0.7);
  });
});

describe("curateStatusLabel", () => {
  it("maps running status", () => {
    expect(curateStatusLabel("running")).toBe("実行中");
  });
});

describe("isCurateJobActive", () => {
  it("returns true for queued and running", () => {
    expect(isCurateJobActive("queued")).toBe(true);
    expect(isCurateJobActive("running")).toBe(true);
    expect(isCurateJobActive("succeeded")).toBe(false);
  });
});
