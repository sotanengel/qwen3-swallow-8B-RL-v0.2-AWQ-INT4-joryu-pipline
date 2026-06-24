import { describe, expect, it, vi } from "vitest";

import {
  curationFetchUrls,
  fetchLiveJson,
  fetchLiveText,
  responsesFetchUrls,
  statsFetchUrls,
} from "./live-data";

describe("statsFetchUrls", () => {
  it("lists API, live route, and static paths in priority order", () => {
    const urls = statsFetchUrls();
    expect(urls[0]).toContain("/api/dashboard/stats");
    expect(urls[1]).toBe("/api/live/stats");
    expect(urls[2]).toBe("/stats.json");
  });
});

describe("fetchLiveJson", () => {
  it("returns first successful response", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ total: 3 }) });
    vi.stubGlobal("fetch", fetchMock);

    const res = await fetchLiveJson(["/a", "/b"]);
    expect(res).not.toBeNull();
    expect(await res!.json()).toEqual({ total: 3 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("appends cache-bust query to each URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);

    await fetchLiveJson(["/stats.json"]);

    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toMatch(/^\/stats\.json\?t=\d+$/);
  });
});

describe("fetchLiveText", () => {
  it("returns text from first ok response", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, text: async () => "line\n" });
    vi.stubGlobal("fetch", fetchMock);

    const text = await fetchLiveText(responsesFetchUrls().slice(2, 3));
    expect(text).toBe("line\n");
  });

  it("returns null when all sources fail", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false });
    vi.stubGlobal("fetch", fetchMock);

    expect(await fetchLiveText(["/missing.jsonl"])).toBeNull();
  });
});

describe("curationFetchUrls", () => {
  it("includes live route before static file", () => {
    expect(curationFetchUrls()).toEqual(["/api/live/curation", "/curation.json"]);
  });
});
