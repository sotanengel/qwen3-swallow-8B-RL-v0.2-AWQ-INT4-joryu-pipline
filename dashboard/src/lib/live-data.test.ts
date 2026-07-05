import { describe, expect, it, vi } from "vitest";

import {
  curationFetchUrls,
  fetchAllLiveJson,
  fetchBestLiveText,
  responsesFetchUrls,
  statsFetchUrls,
} from "./live-data";

describe("statsFetchUrls", () => {
  it("lists live route first, then proxy, direct API, and static", () => {
    const urls = statsFetchUrls();
    expect(urls[0]).toBe("/api/live/stats");
    expect(urls[1]).toBe("/joryu-api/api/dashboard/stats");
    expect(urls[2]).toContain("/api/dashboard/stats");
    expect(urls[3]).toBe("/stats.json");
  });
});

describe("fetchAllLiveJson", () => {
  it("returns all successful payloads", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, json: async () => ({}) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ total: 3 }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ total: 5 }) });
    vi.stubGlobal("fetch", fetchMock);

    const rows = await fetchAllLiveJson(["/a", "/b", "/c"]);
    expect(rows).toEqual([{ total: 3 }, { total: 5 }]);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("appends cache-bust query to each URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);

    await fetchAllLiveJson(["/stats.json"]);

    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toMatch(/^\/stats\.json\?t=\d+$/);
  });
});

describe("fetchBestLiveText", () => {
  it("returns the longest text among sources", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, text: async () => "a\n" })
      .mockResolvedValueOnce({ ok: true, text: async () => "a\nb\nc\n" });
    vi.stubGlobal("fetch", fetchMock);

    const text = await fetchBestLiveText(responsesFetchUrls().slice(0, 2));
    expect(text).toBe("a\nb\nc\n");
  });

  it("returns null when all sources fail", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false });
    vi.stubGlobal("fetch", fetchMock);

    expect(await fetchBestLiveText(["/missing.jsonl"])).toBeNull();
  });
});

describe("responsesFetchUrls", () => {
  it("includes live route and proxy paths", () => {
    const urls = responsesFetchUrls();
    expect(urls[0]).toBe("/api/live/responses");
    expect(urls[1]).toBe("/joryu-api/api/dashboard/responses");
  });
});

describe("curationFetchUrls", () => {
  it("includes live route before static file", () => {
    expect(curationFetchUrls()).toEqual(["/api/live/curation", "/curation.json"]);
  });
});
