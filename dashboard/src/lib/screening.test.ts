import { describe, expect, it } from "vitest";

import { pickBestScreening } from "./screening";

describe("pickBestScreening", () => {
  it("prefers the candidate with the larger total", () => {
    const best = pickBestScreening([
      { total: 1, label_distribution: {} },
      { total: 5, label_distribution: { ok: { count: 5, rate: 1 } } },
    ]);
    expect(best.total).toBe(5);
  });

  it("breaks ties with generated_at metadata", () => {
    const best = pickBestScreening([
      { total: 3, _meta: { generated_at: "2026-01-01T00:00:00Z" } },
      { total: 3, _meta: { generated_at: "2026-01-02T00:00:00Z" } },
    ]);
    expect(best._meta?.generated_at).toBe("2026-01-02T00:00:00Z");
  });
});
