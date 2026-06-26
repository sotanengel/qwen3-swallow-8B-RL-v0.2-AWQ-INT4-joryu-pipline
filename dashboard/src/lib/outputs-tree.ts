import { DistilledRecord, recordLooksTruncated } from "./jsonl";

/** styles.yaml と同期した style_id → 表示名マップ */
export const STYLE_LABELS: Record<string, string> = {
  prose: "散文",
  qa_short: "短答",
  dialog: "対話",
  report: "レポート",
};

export const UNCATEGORIZED_LABEL = "(未分類)";
export const DEFAULT_STYLE_LABEL = "(default)";

export interface StyleNode {
  styleId: string;
  label: string;
  count: number;
  thinkingCount: number;
  records: DistilledRecord[];
}

export interface CategoryNode {
  category: string;
  count: number;
  truncatedCount: number;
  latestCreatedAt: string | null;
  styles: StyleNode[];
}

export function normalizeCategory(category: string | null | undefined): string {
  if (!category) return UNCATEGORIZED_LABEL;
  return category;
}

export function normalizeStyleId(styleId: string | null | undefined): string {
  if (!styleId) return DEFAULT_STYLE_LABEL;
  return styleId;
}

export function styleLabel(styleId: string | null | undefined): string {
  const id = normalizeStyleId(styleId);
  if (id === DEFAULT_STYLE_LABEL) return DEFAULT_STYLE_LABEL;
  return STYLE_LABELS[id] ?? id;
}

function maxCreatedAt(a: string | null, b: string | null | undefined): string | null {
  if (!b) return a;
  if (!a) return b;
  return a > b ? a : b;
}

export function buildOutputsTree(records: DistilledRecord[]): CategoryNode[] {
  const categoryMap = new Map<
    string,
    {
      count: number;
      truncatedCount: number;
      latestCreatedAt: string | null;
      styles: Map<
        string,
        { count: number; thinkingCount: number; records: DistilledRecord[] }
      >;
    }
  >();

  for (const record of records) {
    const category = normalizeCategory(record.category);
    const styleId = normalizeStyleId(record.style_id);

    let cat = categoryMap.get(category);
    if (!cat) {
      cat = { count: 0, truncatedCount: 0, latestCreatedAt: null, styles: new Map() };
      categoryMap.set(category, cat);
    }
    cat.count += 1;
    if (recordLooksTruncated(record)) cat.truncatedCount += 1;
    cat.latestCreatedAt = maxCreatedAt(cat.latestCreatedAt, record.created_at);

    let style = cat.styles.get(styleId);
    if (!style) {
      style = { count: 0, thinkingCount: 0, records: [] };
      cat.styles.set(styleId, style);
    }
    style.count += 1;
    if (record.mode === "thinking") style.thinkingCount += 1;
    style.records.push(record);
  }

  return [...categoryMap.entries()]
    .sort(([a], [b]) => a.localeCompare(b, "ja"))
    .map(([category, cat]) => ({
      category,
      count: cat.count,
      truncatedCount: cat.truncatedCount,
      latestCreatedAt: cat.latestCreatedAt,
      styles: [...cat.styles.entries()]
        .sort(([a], [b]) => a.localeCompare(b, "ja"))
        .map(([styleId, style]) => ({
          styleId,
          label: styleLabel(styleId),
          count: style.count,
          thinkingCount: style.thinkingCount,
          records: style.records,
        })),
    }));
}
