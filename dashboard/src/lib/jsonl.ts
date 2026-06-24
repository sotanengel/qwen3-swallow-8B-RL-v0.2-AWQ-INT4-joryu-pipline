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
  finish_reason?: string | null;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
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

export async function loadJsonl(_url = "/responses.jsonl"): Promise<DistilledRecord[]> {
  try {
    const { fetchLiveText, responsesFetchUrls } = await import("./live-data");
    const text = await fetchLiveText(responsesFetchUrls());
    if (text === null) return [];
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

const RECORD_KEY_SEP = "\x1e";

/** レコードの安定キー文字列を構築する。 */
export function recordKey(r: DistilledRecord): string {
  return [
    r.prompt,
    r.category ?? "",
    r.mode ?? "",
    r.style_id ?? "",
    r.created_at ?? "",
    r.config_hash ?? "",
  ].join(RECORD_KEY_SEP);
}

/** FNV-1a 32-bit ハッシュ (決定論的・URL 安全な base36 文字列)。 */
function fnv1aHash(text: string): string {
  let hash = 2166136261;
  for (let i = 0; i < text.length; i++) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}

/** レコードの URL 用 ID を生成する。 */
export function recordId(r: DistilledRecord): string {
  return fnv1aHash(recordKey(r));
}

/** ID からレコードを検索する。 */
export function findRecordById(
  records: DistilledRecord[],
  id: string,
): DistilledRecord | undefined {
  return records.find((r) => recordId(r) === id);
}

/** レコードが途中打ち切りか判定する (finish_reason 優先、なければヒューリスティック)。 */
export function recordLooksTruncated(r: DistilledRecord): boolean {
  if (r.finish_reason === "length") return true;
  if (r.finish_reason === "stop") return false;
  return answerLooksTruncated(r.answer);
}

const END_OK = /[。！？.!?」』）)\]]\s*$/;
const HEADER_LINE = /^#{1,6}\s+\S/;

function answerLooksTruncated(answer: string): boolean {
  const ans = answer.trim();
  if (!ans) return true;
  if (END_OK.test(ans)) return false;
  const last = ans.split("\n").pop()?.trim() ?? "";
  if (HEADER_LINE.test(last)) return true;
  if (last.includes("|") && !last.endsWith("|")) return true;
  if (/[、，,：:]\s*$/.test(last)) return true;
  if (/[\u4e00-\u9fff]$/.test(last) && ans.length > 200) return true;
  return false;
}

/** テキストを指定長で切り詰める。 */
export function truncateText(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return `${text.slice(0, maxLen)}…`;
}

function formatMetaLine(label: string, value: string | null | undefined): string | null {
  if (value == null || value === "") return null;
  return `- **${label}**: ${value}`;
}

/** レコードを Markdown 文書に整形する。 */
export function formatRecordMarkdown(r: DistilledRecord): string {
  const metaLines = [
    formatMetaLine("category", r.category),
    formatMetaLine("mode", r.mode),
    formatMetaLine("style_id", r.style_id),
    formatMetaLine("model", r.model),
    formatMetaLine("config_hash", r.config_hash),
    formatMetaLine("created_at", r.created_at),
    formatMetaLine("finish_reason", r.finish_reason),
    r.prompt_tokens != null ? `- **prompt_tokens**: ${r.prompt_tokens}` : null,
    r.completion_tokens != null ? `- **completion_tokens**: ${r.completion_tokens}` : null,
    recordLooksTruncated(r) ? "- **truncated**: はい（生成上限で切断の可能性）" : null,
    r.sampling && Object.keys(r.sampling).length > 0
      ? `- **sampling**: ${JSON.stringify(r.sampling)}`
      : null,
  ].filter((line): line is string => line !== null);

  const sections = [
    "## メタデータ",
    metaLines.join("\n"),
    "## プロンプト",
    r.prompt,
  ];

  const thinking = r.thinking_trace?.trim();
  if (thinking) {
    sections.push("## 思考過程", thinking);
  }

  sections.push("## 回答", r.answer);
  return sections.join("\n\n");
}
