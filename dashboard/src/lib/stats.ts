// joryu-stats CLI が出力する dashboard/public/stats.json のスキーマと型。
// 入力欠損時にも壊れないようすべて optional にしてある (fallback で空にしてある)。

export interface LengthBin {
  lo: number;
  hi: number | null;
  count: number;
}

export interface LengthSummary {
  count: number;
  mean: number;
  max: number;
  min: number;
  bins: LengthBin[];
}

export interface JoryuStats {
  total: number;
  models: Record<string, number>;
  modes: Record<string, number>;
  categories: Record<string, number>;
  styles: Record<string, number>;
  answer_length: LengthSummary;
  thinking_length: LengthSummary;
  sampling: {
    temperature: Record<string, number>;
    top_p: Record<string, number>;
  };
  timeline_daily: Record<string, number>;
  _meta?: {
    source_path?: string;
    generated_at?: string;
  };
}

export const EMPTY_STATS: JoryuStats = {
  total: 0,
  models: {},
  modes: {},
  categories: {},
  styles: {},
  answer_length: { count: 0, mean: 0, max: 0, min: 0, bins: [] },
  thinking_length: { count: 0, mean: 0, max: 0, min: 0, bins: [] },
  sampling: { temperature: {}, top_p: {} },
  timeline_daily: {},
};

export function sortByCount(
  obj: Record<string, number>,
  topN = 20,
): Array<{ key: string; count: number }> {
  return Object.entries(obj)
    .map(([key, count]) => ({ key, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, topN);
}

/** stats.json の部分欠損でも描画が壊れないようネストをマージする。 */
export function mergeStats(data: Partial<JoryuStats>): JoryuStats {
  return {
    ...EMPTY_STATS,
    ...data,
    answer_length: {
      ...EMPTY_STATS.answer_length,
      ...data.answer_length,
      bins: data.answer_length?.bins ?? EMPTY_STATS.answer_length.bins,
    },
    thinking_length: {
      ...EMPTY_STATS.thinking_length,
      ...data.thinking_length,
      bins: data.thinking_length?.bins ?? EMPTY_STATS.thinking_length.bins,
    },
    sampling: {
      temperature: {
        ...EMPTY_STATS.sampling.temperature,
        ...data.sampling?.temperature,
      },
      top_p: {
        ...EMPTY_STATS.sampling.top_p,
        ...data.sampling?.top_p,
      },
    },
    timeline_daily: {
      ...EMPTY_STATS.timeline_daily,
      ...data.timeline_daily,
    },
  };
}

export async function loadStats(_url = "/stats.json"): Promise<JoryuStats> {
  try {
    const { fetchAllLiveJson, statsFetchUrls } = await import("./live-data");
    const payloads = await fetchAllLiveJson(statsFetchUrls());
    if (payloads.length === 0) return EMPTY_STATS;
    return pickNewestStats(payloads as Partial<JoryuStats>[]);
  } catch {
    return EMPTY_STATS;
  }
}

/** 複数ソースから取得した stats のうち total / generated_at が最新のものを選ぶ。 */
export function pickNewestStats(candidates: Partial<JoryuStats>[]): JoryuStats {
  return candidates.reduce<JoryuStats>((best, raw) => {
    const cur = mergeStats(raw);
    if (cur.total > best.total) return cur;
    if (cur.total < best.total) return best;
    const curTs = cur._meta?.generated_at ?? "";
    const bestTs = best._meta?.generated_at ?? "";
    return curTs > bestTs ? cur : best;
  }, EMPTY_STATS);
}

/** ポーリング時に再描画が必要か (_meta.generated_at または total で判定)。 */
export function statsDataChanged(prev: JoryuStats, next: JoryuStats): boolean {
  if (prev.total !== next.total) return true;
  return prev._meta?.generated_at !== next._meta?.generated_at;
}
