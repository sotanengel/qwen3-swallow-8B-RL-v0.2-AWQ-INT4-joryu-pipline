import { describe, expect, it } from "vitest";

import { parseJobRecord, statusLabel } from "./jobs";

describe("parseJobRecord", () => {
  it("normalizes API payload", () => {
    const job = parseJobRecord({
      id: "abc",
      spec: { count: 3, style: ["polite"], mode: "thinking" },
      status: "queued",
      created_at: "2025-01-01T00:00:00+00:00",
    });
    expect(job.id).toBe("abc");
    expect(job.spec.count).toBe(3);
    expect(job.spec.style).toEqual(["polite"]);
    expect(job.status).toBe("queued");
  });
});

describe("statusLabel", () => {
  it("maps known statuses", () => {
    expect(statusLabel("running")).toBe("実行中");
    expect(statusLabel("succeeded")).toBe("成功");
  });
});
