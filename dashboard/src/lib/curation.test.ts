import { describe, expect, it } from "vitest";

import {
  EMPTY_CURATION,
  curationDataChanged,
  mergeCuration,
} from "./curation";

describe("EMPTY_CURATION", () => {
  it("has zero counters", () => {
    expect(EMPTY_CURATION.total).toBe(0);
    expect(EMPTY_CURATION.accepted).toBe(0);
    expect(EMPTY_CURATION.rubric_avg).toEqual({});
  });
});

describe("mergeCuration", () => {
  it("keeps defaults when partial keys missing", () => {
    const merged = mergeCuration({ total: 10, accepted: 4 });
    expect(merged.total).toBe(10);
    expect(merged.accepted).toBe(4);
    expect(merged.rejected_reasons_top).toEqual([]);
    expect(merged.by_style).toEqual({});
  });

  it("preserves rejected_reasons_top tuples", () => {
    const merged = mergeCuration({
      total: 2,
      accepted: 1,
      rejected_reasons_top: [["LEN-A", 1]],
    });
    expect(merged.rejected_reasons_top).toEqual([["LEN-A", 1]]);
  });
});

describe("curationDataChanged", () => {
  it("detects total change", () => {
    const prev = mergeCuration({ total: 1 });
    const next = mergeCuration({ total: 2 });
    expect(curationDataChanged(prev, next)).toBe(true);
  });

  it("detects generated_at change", () => {
    const prev = mergeCuration({ total: 1, _meta: { generated_at: "t1" } });
    const next = mergeCuration({ total: 1, _meta: { generated_at: "t2" } });
    expect(curationDataChanged(prev, next)).toBe(true);
  });

  it("returns false when unchanged", () => {
    const prev = mergeCuration({ total: 1, _meta: { generated_at: "t1" } });
    const next = mergeCuration({ total: 1, _meta: { generated_at: "t1" } });
    expect(curationDataChanged(prev, next)).toBe(false);
  });
});
