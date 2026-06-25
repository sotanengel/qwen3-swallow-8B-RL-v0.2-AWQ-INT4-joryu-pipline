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

export interface TruncationRetryAlert {
  prompt_preview: string;
  style_id: string | null;
  attempts: number;
  updated_at: string;
}

export interface DistillLiveState {
  active: boolean;
  truncation_retries: TruncationRetryAlert[];
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
  tool_records?: number;
  tool_call_records?: number;
  total_tool_calls?: number;
  tool_call_rate?: number;
  tool_calls_per_record?: number;
  tool_name_counts?: Record<string, number>;
  tool_planned_not_called_count?: number;
  tool_planned_but_not_called_rate?: number;
  distill_live?: DistillLiveState;
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
  tool_records: 0,
  tool_call_records: 0,
  total_tool_calls: 0,
  tool_call_rate: 0,
  tool_calls_per_record: 0,
  tool_name_counts: {},
  tool_planned_not_called_count: 0,
  tool_planned_but_not_called_rate: 0,
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
    tool_records: data.tool_records ?? EMPTY_STATS.tool_records,
    tool_call_records: data.tool_call_records ?? EMPTY_STATS.tool_call_records,
    total_tool_calls: data.total_tool_calls ?? EMPTY_STATS.total_tool_calls,
    tool_call_rate: data.tool_call_rate ?? EMPTY_STATS.tool_call_rate,
    tool_calls_per_record: data.tool_calls_per_record ?? EMPTY_STATS.tool_calls_per_record,
    tool_name_counts: {
      ...EMPTY_STATS.tool_name_counts,
      ...data.tool_name_counts,
    },
    tool_planned_not_called_count:
      data.tool_planned_not_called_count ?? EMPTY_STATS.tool_planned_not_called_count,
    tool_planned_but_not_called_rate:
      data.tool_planned_but_not_called_rate ?? EMPTY_STATS.tool_planned_but_not_called_rate,
    distill_live: data.distill_live,
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

/** ポーリング時に再描画が必要か (_meta.generated_at / total / live アラートで判定)。 */
export function statsDataChanged(prev: JoryuStats, next: JoryuStats): boolean {
  if (prev.total !== next.total) return true;
  if (prev._meta?.generated_at !== next._meta?.generated_at) return true;
  const prevRetries = prev.distill_live?.truncation_retries?.length ?? 0;
  const nextRetries = next.distill_live?.truncation_retries?.length ?? 0;
  if (prevRetries !== nextRetries) return true;
  if (prev.distill_live?.active !== next.distill_live?.active) return true;
  if ((prev.tool_call_rate ?? 0) !== (next.tool_call_rate ?? 0)) return true;
  if ((prev.tool_planned_but_not_called_rate ?? 0) !== (next.tool_planned_but_not_called_rate ?? 0))
    return true;
  return false;
}
