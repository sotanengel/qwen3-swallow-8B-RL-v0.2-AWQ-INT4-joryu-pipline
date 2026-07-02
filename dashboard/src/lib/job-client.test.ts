import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  apiFetch,
  createJobClient,
  isActiveStatus,
  statusLabelJa,
} from "./job-client";

type FakeSpec = { count: number };
type FakeRecord = { id: string; kind: string; spec: FakeSpec; status: string };

function parseRecord(data: unknown): FakeRecord {
  const r = data as FakeRecord;
  return {
    id: String(r.id),
    kind: String(r.kind ?? "fake"),
    spec: { count: Number(r.spec?.count ?? 0) },
    status: String(r.status),
  };
}

const originalFetch = globalThis.fetch;

beforeEach(() => {
  globalThis.fetch = originalFetch;
});

afterEach(() => {
  globalThis.fetch = originalFetch;
});

function mockFetch(handler: (url: string, init?: RequestInit) => Response) {
  globalThis.fetch = (async (url: string, init?: RequestInit) => handler(url, init)) as unknown as typeof fetch;
}

describe("apiFetch", () => {
  it("extracts detail from error responses", async () => {
    mockFetch(() =>
      new Response(JSON.stringify({ detail: "bad thing" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(apiFetch("/x")).rejects.toThrow("bad thing");
  });

  it("falls back to statusText when body has no detail", async () => {
    mockFetch(() => new Response("", { status: 502, statusText: "Bad Gateway" }));
    await expect(apiFetch("/x")).rejects.toThrow("Bad Gateway");
  });

  it("returns parsed JSON on success", async () => {
    mockFetch(() =>
      new Response(JSON.stringify({ ok: 1 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(apiFetch<{ ok: number }>("/x")).resolves.toEqual({ ok: 1 });
  });
});

describe("createJobClient", () => {
  const client = createJobClient<FakeSpec, { count: number }, FakeRecord>({
    basePath: "/api/fake",
    parseRecord,
  });

  it("list() GETs basePath and maps rows through parseRecord", async () => {
    const urls: string[] = [];
    mockFetch((url) => {
      urls.push(url);
      return new Response(
        JSON.stringify([
          { id: "a", spec: { count: 1 }, status: "queued" },
          { id: "b", spec: { count: 2 }, status: "running" },
        ]),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });
    const rows = await client.list();
    expect(urls[0]).toContain("/api/fake");
    expect(rows).toHaveLength(2);
    expect(rows[0].id).toBe("a");
    expect(rows[1].spec.count).toBe(2);
  });

  it("create() POSTs body", async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    mockFetch((url, init) => {
      calls.push({ url, init });
      return new Response(
        JSON.stringify({ id: "new", spec: { count: 5 }, status: "queued" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });
    const rec = await client.create({ count: 5 });
    expect(calls[0].init?.method).toBe("POST");
    expect(calls[0].init?.body).toBe(JSON.stringify({ count: 5 }));
    expect(rec.id).toBe("new");
  });

  it("cancel() POSTs to /{id}/cancel", async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    mockFetch((url, init) => {
      calls.push({ url, init });
      return new Response(
        JSON.stringify({ id: "abc", spec: { count: 1 }, status: "cancelled" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });
    const rec = await client.cancel("abc");
    expect(calls[0].url).toContain("/api/fake/abc/cancel");
    expect(calls[0].init?.method).toBe("POST");
    expect(rec.status).toBe("cancelled");
  });

  it("getLogs() includes offset query", async () => {
    const urls: string[] = [];
    mockFetch((url) => {
      urls.push(url);
      return new Response(JSON.stringify({ chunk: "hello", offset: 5 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    const res = await client.getLogs("abc", 42);
    expect(urls[0]).toContain("/api/fake/abc/logs?offset=42");
    expect(res.chunk).toBe("hello");
    expect(res.offset).toBe(5);
  });
});

describe("statusLabelJa", () => {
  it("maps known statuses to Japanese", () => {
    expect(statusLabelJa("queued")).toBe("待機中");
    expect(statusLabelJa("running")).toBe("実行中");
    expect(statusLabelJa("succeeded")).toBe("成功");
    expect(statusLabelJa("failed")).toBe("失敗");
    expect(statusLabelJa("cancelled")).toBe("中止");
  });

  it("passes through unknown statuses", () => {
    expect(statusLabelJa("weird")).toBe("weird");
  });
});

describe("isActiveStatus", () => {
  it("only queued and running are active", () => {
    expect(isActiveStatus("queued")).toBe(true);
    expect(isActiveStatus("running")).toBe(true);
    expect(isActiveStatus("succeeded")).toBe(false);
    expect(isActiveStatus("failed")).toBe(false);
    expect(isActiveStatus("cancelled")).toBe(false);
  });
});

describe("import satisfies vi.mock global type", () => {
  it("keeps vi importable", () => {
    expect(typeof vi).toBe("object");
  });
});
