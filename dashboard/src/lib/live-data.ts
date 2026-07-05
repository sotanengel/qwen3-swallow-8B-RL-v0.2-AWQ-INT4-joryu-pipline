/** 蒸留データのライブ取得 (複数ソース並列取得 → 最新を採用)。 */

const API_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_JORYU_API_URL) ||
  "http://localhost:8000";

function withCacheBust(url: string): string {
  return `${url}${url.includes("?") ? "&" : "?"}t=${Date.now()}`;
}

/** 同一オリジン live route を最優先 (Docker bind mount の fs 直読み)。 */
export function statsFetchUrls(): string[] {
  return [
    "/api/live/stats",
    "/joryu-api/api/dashboard/stats",
    `${API_BASE}/api/dashboard/stats`,
    "/stats.json",
  ];
}

export function responsesFetchUrls(): string[] {
  return [
    "/api/live/responses",
    "/joryu-api/api/dashboard/responses",
    `${API_BASE}/api/dashboard/responses`,
    "/responses.jsonl",
  ];
}

export function curationFetchUrls(): string[] {
  return ["/api/live/curation", "/curation.json"];
}

export async function fetchAllLiveJson(urls: readonly string[]): Promise<unknown[]> {
  const settled = await Promise.all(
    urls.map(async (url) => {
      try {
        const r = await fetch(withCacheBust(url), { cache: "no-store" });
        if (!r.ok) return null;
        return await r.json();
      } catch {
        return null;
      }
    }),
  );
  return settled.filter((row): row is unknown => row !== null);
}

export async function fetchBestLiveText(urls: readonly string[]): Promise<string | null> {
  const settled = await Promise.all(
    urls.map(async (url) => {
      try {
        const r = await fetch(withCacheBust(url), { cache: "no-store" });
        if (!r.ok) return null;
        return await r.text();
      } catch {
        return null;
      }
    }),
  );
  const texts = settled.filter((row): row is string => row !== null);
  if (texts.length === 0) return null;
  return texts.reduce((best, cur) => (cur.length > best.length ? cur : best));
}
