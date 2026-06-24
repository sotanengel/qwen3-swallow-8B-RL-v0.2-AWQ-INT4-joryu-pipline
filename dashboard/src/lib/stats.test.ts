import { describe, expect, it, vi } from "vitest";

import { EMPTY_STATS, loadStats, mergeStats, sortByCount, statsDataChanged } from "./stats";

describe("EMPTY_STATS", () => {
  it("has total 0", () => {
    expect(EMPTY_STATS.total).toBe(0);
    expect(EMPTY_STATS.categories).toEqual({});
  });
});

describe("mergeStats", () => {
  it("keeps nested defaults when partial stats omit bins or sampling", () => {
    const merged = mergeStats({
      total: 3,
      answer_length: { count: 3, mean: 10, max: 20, min: 5, bins: [] },
      sampling: { temperature: { "0.7": 2 } },
    });
    expect(merged.total).toBe(3);
    expect(merged.answer_length.bins).toEqual([]);
    expect(merged.thinking_length.bins).toEqual([]);
    expect(merged.sampling.temperature).toEqual({ "0.7": 2 });
    expect(merged.sampling.top_p).toEqual({});
  });
});

describe("sortByCount", () => {
  it("orders descending and applies topN", () => {
    const out = sortByCount({ a: 1, b: 5, c: 3, d: 10 }, 2);
    expect(out).toEqual([
      { key: "d", count: 10 },
      { key: "b", count: 5 },
    ]);
  });

  it("handles empty map", () => {
    expect(sortByCount({})).toEqual([]);
  });
});

describe("loadStats", () => {
  it("prefers API dashboard stats with cache-bust", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ total: 1 }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await loadStats();

    expect(result.total).toBe(1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toMatch(/\/api\/dashboard\/stats\?t=\d+$/);
  });

  it("falls back through live sources when API is unavailable", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false })
      .mockResolvedValueOnce({ ok: false })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ total: 2 }) });
    vi.stubGlobal("fetch", fetchMock);

    const result = await loadStats();

    expect(result.total).toBe(2);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    const lastUrl = String(fetchMock.mock.calls[2][0]);
    expect(lastUrl).toMatch(/^\/stats\.json\?t=\d+$/);
  });
});

describe("statsDataChanged", () => {
  it("returns true when total changes", () => {
    const prev = mergeStats({ total: 1 });
    const next = mergeStats({ total: 2 });
    expect(statsDataChanged(prev, next)).toBe(true);
  });

  it("returns true when generated_at changes", () => {
    const prev = mergeStats({ total: 1, _meta: { generated_at: "t1" } });
    const next = mergeStats({ total: 1, _meta: { generated_at: "t2" } });
    expect(statsDataChanged(prev, next)).toBe(true);
  });

  it("returns false when unchanged", () => {
    const prev = mergeStats({ total: 1, _meta: { generated_at: "t1" } });
    const next = mergeStats({ total: 1, _meta: { generated_at: "t1" } });
    expect(statsDataChanged(prev, next)).toBe(false);
  });
});
