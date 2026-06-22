// joryu-curate が出力する dashboard/public/curation.json のスキーマと型。
// 入力欠損時にも壊れないようすべて optional + デフォルト fallback。

import type { LengthBin } from "./stats";

export interface RubricAvg {
  accuracy?: number;
  completeness?: number;
  fluency?: number;
  instruction_following?: number;
  safety?: number;
}

export interface CurationByStyle {
  total: number;
  kept: number;
  keep_rate: number;
}

export interface CurationStats {
  total: number;
  accepted: number;
  rejected: number;
  keep_rate: number;
  score_bins: LengthBin[];
  rejected_reasons_top: Array<[string, number]>;
  rubric_avg: RubricAvg;
  rubric_count: number;
  by_style: Record<string, CurationByStyle>;
  _meta?: {
    source_path?: string;
    generated_at?: string;
  };
}

export const EMPTY_CURATION: CurationStats = {
  total: 0,
  accepted: 0,
  rejected: 0,
  keep_rate: 0,
  score_bins: [],
  rejected_reasons_top: [],
  rubric_avg: {},
  rubric_count: 0,
  by_style: {},
};

export function mergeCuration(data: Partial<CurationStats>): CurationStats {
  return {
    ...EMPTY_CURATION,
    ...data,
    score_bins: data.score_bins ?? EMPTY_CURATION.score_bins,
    rejected_reasons_top:
      data.rejected_reasons_top ?? EMPTY_CURATION.rejected_reasons_top,
    rubric_avg: data.rubric_avg ?? EMPTY_CURATION.rubric_avg,
    by_style: data.by_style ?? EMPTY_CURATION.by_style,
  };
}

export async function loadCuration(
  url = "/curation.json",
): Promise<CurationStats> {
  try {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) return EMPTY_CURATION;
    const data = (await r.json()) as Partial<CurationStats>;
    return mergeCuration(data);
  } catch {
    return EMPTY_CURATION;
  }
}

export function curationDataChanged(
  prev: CurationStats,
  next: CurationStats,
): boolean {
  if (prev.total !== next.total) return true;
  if (prev.accepted !== next.accepted) return true;
  return prev._meta?.generated_at !== next._meta?.generated_at;
}
