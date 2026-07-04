// screening.json の型とローダ

export interface ScreeningLabelBucket {
  count: number;
  rate: number;
}

export interface ScreeningStats {
  total: number;
  label_distribution: Record<string, ScreeningLabelBucket>;
  rule_violation_rates: Record<string, number>;
  llm_health_averages: Record<string, number>;
  llm_health_count: number;
  evaluator_models: Record<string, number>;
  judge_comparison: Record<string, unknown> | null;
  _meta?: {
    source_path?: string;
    generated_at?: string;
  };
}

export const EMPTY_SCREENING: ScreeningStats = {
  total: 0,
  label_distribution: {},
  rule_violation_rates: {},
  llm_health_averages: {},
  llm_health_count: 0,
  evaluator_models: {},
  judge_comparison: null,
};

export function screeningDataChanged(
  prev: ScreeningStats,
  next: ScreeningStats,
): boolean {
  return JSON.stringify(prev) !== JSON.stringify(next);
}

export function mergeScreening(data: Partial<ScreeningStats>): ScreeningStats {
  return {
    ...EMPTY_SCREENING,
    ...data,
    label_distribution: data.label_distribution ?? EMPTY_SCREENING.label_distribution,
    rule_violation_rates: data.rule_violation_rates ?? EMPTY_SCREENING.rule_violation_rates,
    llm_health_averages: data.llm_health_averages ?? EMPTY_SCREENING.llm_health_averages,
    evaluator_models: data.evaluator_models ?? EMPTY_SCREENING.evaluator_models,
  };
}

export function pickBestScreening(candidates: Partial<ScreeningStats>[]): ScreeningStats {
  return candidates.reduce<ScreeningStats>((best, raw) => {
    const cur = mergeScreening(raw);
    if (cur.total > best.total) return cur;
    if (cur.total < best.total) return best;
    const curTs = cur._meta?.generated_at ?? "";
    const bestTs = best._meta?.generated_at ?? "";
    return curTs > bestTs ? cur : best;
  }, EMPTY_SCREENING);
}

export async function loadScreening(): Promise<ScreeningStats> {
  try {
    const { fetchAllLiveJson, screeningFetchUrls } = await import("./live-data");
    const payloads = await fetchAllLiveJson(screeningFetchUrls());
    if (payloads.length === 0) return EMPTY_SCREENING;
    return pickBestScreening(payloads as Partial<ScreeningStats>[]);
  } catch {
    return EMPTY_SCREENING;
  }
}
