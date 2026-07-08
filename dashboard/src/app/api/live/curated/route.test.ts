import { afterEach, describe, expect, it, vi } from "vitest";

const readFileMock = vi.hoisted(() => vi.fn());

vi.mock("fs/promises", () => ({
  readFile: readFileMock,
}));

afterEach(() => {
  vi.clearAllMocks();
});

describe("GET /api/live/curated", () => {
  it("returns high_quality jsonl with no-store headers", async () => {
    readFileMock.mockResolvedValue('{"prompt":"hq","answer":"ok"}\n');
    const { GET } = await import("./route");
    const res = await GET();
    expect(res.headers.get("cache-control")).toContain("no-store");
    expect(res.headers.get("content-type")).toContain("application/x-ndjson");
    expect(await res.text()).toContain("hq");
  });

  it("returns empty body when file is missing", async () => {
    readFileMock.mockRejectedValue(new Error("ENOENT"));
    const { GET } = await import("./route");
    const res = await GET();
    expect(await res.text()).toBe("");
  });
});
