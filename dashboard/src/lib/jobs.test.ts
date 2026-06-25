import { describe, expect, it } from "vitest";

import { parseJobRecord, statusLabel } from "./jobs";

describe("parseJobRecord", () => {
  it("normalizes API payload", () => {
    const job = parseJobRecord({
      id: "abc",
      kind: "distill",
      spec: {
        count: 3,
        style: ["prose"],
        mode: "thinking",
        tool_ids: ["search"],
        tool_loop: true,
        max_turns: 4,
      },
      status: "queued",
      created_at: "2025-01-01T00:00:00+00:00",
    });
    expect(job.id).toBe("abc");
    expect(job.kind).toBe("distill");
    expect(job.spec.count).toBe(3);
    expect(job.spec.style).toEqual(["prose"]);
    expect(job.spec.tool_ids).toEqual(["search"]);
    expect(job.spec.tool_loop).toBe(true);
    expect(job.spec.max_turns).toBe(4);
    expect(job.status).toBe("queued");
  });

  it("defaults tool fields when omitted", () => {
    const job = parseJobRecord({
      id: "abc",
      spec: { count: 1 },
      status: "queued",
      created_at: "2025-01-01T00:00:00+00:00",
    });
    expect(job.spec.tool_ids).toEqual([]);
    expect(job.spec.tool_loop).toBe(false);
    expect(job.spec.max_turns).toBeNull();
  });

  it("defaults kind to distill when omitted", () => {
    const job = parseJobRecord({
      id: "abc",
      spec: { count: 1 },
      status: "queued",
      created_at: "2025-01-01T00:00:00+00:00",
    });
    expect(job.kind).toBe("distill");
  });
});

describe("statusLabel", () => {
  it("maps known statuses", () => {
    expect(statusLabel("running")).toBe("実行中");
    expect(statusLabel("succeeded")).toBe("成功");
    expect(statusLabel("cancelled")).toBe("中止");
  });
});

describe("isJobActive", () => {
  it("only queued and running are active", async () => {
    const { isJobActive } = await import("./jobs");
    expect(isJobActive("queued")).toBe(true);
    expect(isJobActive("running")).toBe(true);
    expect(isJobActive("succeeded")).toBe(false);
    expect(isJobActive("failed")).toBe(false);
    expect(isJobActive("cancelled")).toBe(false);
  });
});

describe("cancelJob", () => {
  it("POSTs to the cancel endpoint and returns the parsed record", async () => {
    const { cancelJob } = await import("./jobs");
    const calls: { url: string; init?: RequestInit }[] = [];
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      return new Response(
        JSON.stringify({
          id: "abc",
          spec: { count: 1 },
          status: "cancelled",
          created_at: "2025-01-01T00:00:00+00:00",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }) as unknown as typeof fetch;
    try {
      const rec = await cancelJob("abc");
      expect(rec.status).toBe("cancelled");
      expect(calls).toHaveLength(1);
      expect(calls[0].url).toContain("/api/jobs/abc/cancel");
      expect(calls[0].init?.method).toBe("POST");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
