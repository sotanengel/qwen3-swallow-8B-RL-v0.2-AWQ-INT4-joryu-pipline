/** BM25 ランキング検索 API クライアント。 */

import { DistilledRecord } from "./jsonl";

const API_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_JORYU_API_URL) ||
  "http://localhost:8000";

export type SearchIndexStatus = "ready" | "building" | "empty" | "unavailable";

export interface SearchHit {
  record_key: string;
  score: number;
  snippet: string;
  snippet_field: string;
  record: DistilledRecord;
}

export interface SearchResponse {
  total: number;
  index_status: SearchIndexStatus;
  hits: SearchHit[];
}

export interface SearchRequest {
  query: string;
  mode: "all" | "thinking" | "nothinking";
  category: string;
  limit: number;
  offset: number;
}

export function searchStatusUrl(): string {
  return "/joryu-api/api/dashboard/search/status";
}

export function searchApiUrls(): string[] {
  return [
    "/joryu-api/api/dashboard/search",
    `${API_BASE}/api/dashboard/search`,
  ];
}

export function parseSearchResponse(raw: unknown): SearchResponse {
  if (!raw || typeof raw !== "object") {
    return { total: 0, index_status: "unavailable", hits: [] };
  }
  const obj = raw as Record<string, unknown>;
  const hitsRaw = Array.isArray(obj.hits) ? obj.hits : [];
  const hits: SearchHit[] = hitsRaw
    .filter((h): h is Record<string, unknown> => !!h && typeof h === "object")
    .map((h) => ({
      record_key: String(h.record_key ?? ""),
      score: typeof h.score === "number" ? h.score : 0,
      snippet: String(h.snippet ?? ""),
      snippet_field: String(h.snippet_field ?? ""),
      record: (h.record ?? { prompt: "", answer: "" }) as DistilledRecord,
    }));

  const status = obj.index_status;
  const index_status: SearchIndexStatus =
    status === "ready" ||
    status === "building" ||
    status === "empty" ||
    status === "unavailable"
      ? status
      : "unavailable";

  return {
    total: typeof obj.total === "number" ? obj.total : hits.length,
    index_status,
    hits,
  };
}

export async function searchRanked(req: SearchRequest): Promise<SearchResponse> {
  const body = JSON.stringify(req);
  for (const url of searchApiUrls()) {
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        body,
      });
      if (!res.ok) continue;
      return parseSearchResponse(await res.json());
    } catch {
      /* try next */
    }
  }
  return { total: 0, index_status: "unavailable", hits: [] };
}

export async function fetchSearchStatus(): Promise<{
  index_status: SearchIndexStatus;
  record_count: number;
  stale: boolean;
}> {
  const urls = [searchStatusUrl(), `${API_BASE}/api/dashboard/search/status`];
  for (const url of urls) {
    try {
      const res = await fetch(`${url}?t=${Date.now()}`, { cache: "no-store" });
      if (!res.ok) continue;
      const data = (await res.json()) as Record<string, unknown>;
      const status = data.index_status;
      return {
        index_status:
          status === "ready" ||
          status === "building" ||
          status === "empty" ||
          status === "unavailable"
            ? status
            : "unavailable",
        record_count: typeof data.record_count === "number" ? data.record_count : 0,
        stale: Boolean(data.stale),
      };
    } catch {
      /* try next */
    }
  }
  return { index_status: "unavailable", record_count: 0, stale: false };
}
