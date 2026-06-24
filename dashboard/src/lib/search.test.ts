import { describe, expect, it, vi, afterEach } from "vitest";

import { parseSearchResponse, searchRanked, searchStatusUrl } from "./search";

describe("searchStatusUrl", () => {
  it("returns proxied API path", () => {
    expect(searchStatusUrl()).toBe("/joryu-api/api/dashboard/search/status");
  });
});

describe("parseSearchResponse", () => {
  it("parses valid search response", () => {
    const data = parseSearchResponse({
      total: 1,
      index_status: "ready",
      hits: [
        {
          record_key: "abc",
          score: 1.5,
          snippet: "桜について",
          snippet_field: "answer",
          record: { prompt: "桜", answer: "花" },
        },
      ],
    });
    expect(data.total).toBe(1);
    expect(data.hits[0].record_key).toBe("abc");
    expect(data.hits[0].record.prompt).toBe("桜");
  });

  it("returns empty for invalid payload", () => {
    expect(parseSearchResponse(null).total).toBe(0);
    expect(parseSearchResponse({}).hits).toEqual([]);
  });
});

describe("searchRanked", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("calls search API and returns parsed result", async () => {
    const mockResponse = {
      total: 1,
      index_status: "ready",
      hits: [
        {
          record_key: "x",
          score: 2,
          snippet: "test",
          snippet_field: "prompt",
          record: { prompt: "P", answer: "A" },
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockResponse,
      }),
    );

    const result = await searchRanked({ query: "P", mode: "all", category: "", limit: 10, offset: 0 });
    expect(result.total).toBe(1);
    expect(fetch).toHaveBeenCalled();
  });

  it("returns unavailable on fetch failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network")));
    const result = await searchRanked({ query: "x", mode: "all", category: "", limit: 10, offset: 0 });
    expect(result.index_status).toBe("unavailable");
    expect(result.total).toBe(0);
  });
});
