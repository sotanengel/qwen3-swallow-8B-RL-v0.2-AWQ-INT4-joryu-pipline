import { describe, expect, it } from "vitest";

import { EMPTY_STATS, sortByCount } from "./stats";

describe("EMPTY_STATS", () => {
  it("has total 0", () => {
    expect(EMPTY_STATS.total).toBe(0);
    expect(EMPTY_STATS.categories).toEqual({});
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
