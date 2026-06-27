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

export async function loadScreening(): Promise<ScreeningStats> {
  const res = await fetch("/screening.json", { cache: "no-store" });
  if (!res.ok) {
    return EMPTY_SCREENING;
  }
  const data = (await res.json()) as ScreeningStats;
  return { ...EMPTY_SCREENING, ...data };
}
