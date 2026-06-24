import { describe, expect, it, vi } from "vitest";

import { EMPTY_STATS, loadStats, mergeStats, pickNewestStats, sortByCount, statsDataChanged } from "./stats";

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

describe("pickNewestStats", () => {
  it("prefers higher total", () => {
    const best = pickNewestStats([
      { total: 3, _meta: { generated_at: "t2" } },
      { total: 5, _meta: { generated_at: "t1" } },
    ]);
    expect(best.total).toBe(5);
  });

  it("breaks ties with generated_at", () => {
    const best = pickNewestStats([
      { total: 5, _meta: { generated_at: "t1" } },
      { total: 5, _meta: { generated_at: "t2" } },
    ]);
    expect(best._meta?.generated_at).toBe("t2");
  });
});

describe("loadStats", () => {
  it("fetches all sources in parallel and picks the newest stats", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).startsWith("/api/live/stats")) {
        return { ok: true, json: async () => ({ total: 5, _meta: { generated_at: "t2" } }) };
      }
      if (String(url).includes("/api/dashboard/stats")) {
        return { ok: true, json: async () => ({ total: 3, _meta: { generated_at: "t1" } }) };
      }
      return { ok: false, json: async () => ({}) };
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await loadStats();

    expect(result.total).toBe(5);
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("returns empty stats when all sources fail", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);

    const result = await loadStats();
    expect(result.total).toBe(0);
    expect(fetchMock).toHaveBeenCalledTimes(4);
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
