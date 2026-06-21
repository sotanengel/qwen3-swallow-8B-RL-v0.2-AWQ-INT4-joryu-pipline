// JSONL ストリーミングパーサ + 検索フィルタ。

export interface DistilledRecord {
  prompt: string;
  category?: string | null;
  style_id?: string | null;
  mode?: "thinking" | "nothinking" | null;
  system_prompt?: string;
  sampling?: Record<string, number>;
  thinking_trace?: string | null;
  reasoning?: string;
  answer: string;
  model?: string;
  config_hash?: string;
  created_at?: string;
}

export function parseJsonl(text: string): DistilledRecord[] {
  const out: DistilledRecord[] = [];
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      const obj = JSON.parse(trimmed) as DistilledRecord;
      if (typeof obj === "object" && obj && typeof obj.prompt === "string") {
        out.push(obj);
      }
    } catch {
      // 壊れ行は無視 (resume-safe writer の中断行など)
    }
  }
  return out;
}

export interface SearchFilters {
  query: string;
  mode?: "thinking" | "nothinking" | "all";
  category?: string;
}

export function searchRecords(
  records: DistilledRecord[],
  filters: SearchFilters,
): DistilledRecord[] {
  const q = filters.query.trim().toLowerCase();
  return records.filter((r) => {
    if (filters.mode && filters.mode !== "all" && r.mode !== filters.mode) {
      return false;
    }
    if (filters.category && r.category !== filters.category) {
      return false;
    }
    if (!q) return true;
    return (
      r.prompt.toLowerCase().includes(q) ||
      r.answer.toLowerCase().includes(q) ||
      (r.thinking_trace ?? "").toLowerCase().includes(q)
    );
  });
}

export async function loadJsonl(url = "/responses.jsonl"): Promise<DistilledRecord[]> {
  try {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) return [];
    const text = await r.text();
    return parseJsonl(text);
  } catch {
    return [];
  }
}

/** ポーリング時に再描画が必要か (件数または末尾レコードで判定)。 */
export function jsonlDataChanged(
  prev: DistilledRecord[],
  next: DistilledRecord[],
): boolean {
  if (prev.length !== next.length) return true;
  if (prev.length === 0) return false;
  const prevLast = prev[prev.length - 1];
  const nextLast = next[next.length - 1];
  return (
    prevLast.created_at !== nextLast.created_at ||
    prevLast.prompt !== nextLast.prompt ||
    prevLast.answer !== nextLast.answer
  );
}
