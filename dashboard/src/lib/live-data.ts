/** 蒸留データのライブ取得 (API → Next Route → 静的ファイルの順で試行)。 */

const API_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_JORYU_API_URL) ||
  "http://localhost:8000";

function withCacheBust(url: string): string {
  return `${url}${url.includes("?") ? "&" : "?"}t=${Date.now()}`;
}

export function statsFetchUrls(): string[] {
  return [`${API_BASE}/api/dashboard/stats`, "/api/live/stats", "/stats.json"];
}

export function responsesFetchUrls(): string[] {
  return [
    `${API_BASE}/api/dashboard/responses`,
    "/api/live/responses",
    "/responses.jsonl",
  ];
}

export function curationFetchUrls(): string[] {
  return ["/api/live/curation", "/curation.json"];
}

export async function fetchLiveJson(urls: readonly string[]): Promise<Response | null> {
  for (const url of urls) {
    try {
      const r = await fetch(withCacheBust(url), { cache: "no-store" });
      if (r.ok) return r;
    } catch {
      /* try next source */
    }
  }
  return null;
}

export async function fetchLiveText(urls: readonly string[]): Promise<string | null> {
  for (const url of urls) {
    try {
      const r = await fetch(withCacheBust(url), { cache: "no-store" });
      if (r.ok) return await r.text();
    } catch {
      /* try next source */
    }
  }
  return null;
}
