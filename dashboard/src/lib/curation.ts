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

export interface CurationBySampling {
  total: number;
  kept: number;
  keep_rate: number;
}

export interface CurationSamplingStyleCell {
  sampling: string;
  style_id: string;
  total: number;
  kept: number;
  keep_rate: number;
}

export interface CurationByMode {
  total: number;
  kept: number;
  keep_rate: number;
  score_bins: LengthBin[];
}

export interface CurationRejectedSample {
  record_hash?: string | null;
  prompt: string;
  style_id?: string | null;
  mode?: string | null;
  rejected_by: string[];
  final_score?: number | null;
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
  by_sampling: Record<string, CurationBySampling>;
  by_sampling_style: CurationSamplingStyleCell[];
  by_mode: Record<string, CurationByMode>;
  rejected_samples: CurationRejectedSample[];
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
  by_sampling: {},
  by_sampling_style: [],
  by_mode: {},
  rejected_samples: [],
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
    by_sampling: data.by_sampling ?? EMPTY_CURATION.by_sampling,
    by_sampling_style:
      data.by_sampling_style ?? EMPTY_CURATION.by_sampling_style,
    by_mode: data.by_mode ?? EMPTY_CURATION.by_mode,
    rejected_samples: data.rejected_samples ?? EMPTY_CURATION.rejected_samples,
  };
}

export async function loadCuration(_url = "/curation.json"): Promise<CurationStats> {
  try {
    const { fetchAllLiveJson, curationFetchUrls } = await import("./live-data");
    const payloads = await fetchAllLiveJson(curationFetchUrls());
    if (payloads.length === 0) return EMPTY_CURATION;
    return pickNewestCuration(payloads as Partial<CurationStats>[]);
  } catch {
    return EMPTY_CURATION;
  }
}

export function pickNewestCuration(candidates: Partial<CurationStats>[]): CurationStats {
  return candidates.reduce<CurationStats>((best, raw) => {
    const cur = mergeCuration(raw);
    if (cur.total > best.total) return cur;
    if (cur.total < best.total) return best;
    if (cur.accepted > best.accepted) return cur;
    if (cur.accepted < best.accepted) return best;
    const curTs = cur._meta?.generated_at ?? "";
    const bestTs = best._meta?.generated_at ?? "";
    return curTs > bestTs ? cur : best;
  }, EMPTY_CURATION);
}

export function curationDataChanged(
  prev: CurationStats,
  next: CurationStats,
): boolean {
  if (prev.total !== next.total) return true;
  if (prev.accepted !== next.accepted) return true;
  return prev._meta?.generated_at !== next._meta?.generated_at;
}
