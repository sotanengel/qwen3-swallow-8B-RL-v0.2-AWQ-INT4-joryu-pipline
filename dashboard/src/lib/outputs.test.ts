import { describe, expect, it } from "vitest";

describe("deleteOutput", () => {
  it("DELETEs one record and returns the response", async () => {
    const { deleteOutput } = await import("./outputs");
    const calls: { url: string; init?: RequestInit }[] = [];
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      return new Response(JSON.stringify({ deleted: 1, remaining: 2 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as unknown as typeof fetch;
    try {
      const res = await deleteOutput("abc123");
      expect(res.deleted).toBe(1);
      expect(res.remaining).toBe(2);
      expect(calls).toHaveLength(1);
      expect(calls[0].url).toContain("/api/dashboard/responses/abc123");
      expect(calls[0].init?.method).toBe("DELETE");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("throws on API error", async () => {
    const { deleteOutput } = await import("./outputs");
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async () =>
      new Response(JSON.stringify({ detail: "record not found: x" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      })) as unknown as typeof fetch;
    try {
      await expect(deleteOutput("x")).rejects.toThrow("record not found: x");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

describe("deleteAllOutputs", () => {
  it("DELETEs all records and returns the response", async () => {
    const { deleteAllOutputs } = await import("./outputs");
    const calls: { url: string; init?: RequestInit }[] = [];
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      return new Response(JSON.stringify({ deleted: 5, remaining: 0 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as unknown as typeof fetch;
    try {
      const res = await deleteAllOutputs();
      expect(res.deleted).toBe(5);
      expect(res.remaining).toBe(0);
      expect(calls).toHaveLength(1);
      expect(calls[0].url).toContain("/api/dashboard/responses");
      expect(calls[0].url).not.toContain("/api/dashboard/responses/");
      expect(calls[0].init?.method).toBe("DELETE");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
