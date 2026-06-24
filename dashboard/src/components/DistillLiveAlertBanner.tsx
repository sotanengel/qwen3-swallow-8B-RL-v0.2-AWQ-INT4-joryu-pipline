"use client";

import { useDistillJobFastPoll } from "@/lib/useDistillJobFastPoll";
import { useIntervalPoll } from "@/lib/useIntervalPoll";
import { EMPTY_STATS, loadStats, statsDataChanged } from "@/lib/stats";

export function DistillLiveAlertBanner() {
  const fastPoll = useDistillJobFastPoll();
  const stats = useIntervalPoll(loadStats, EMPTY_STATS, {
    shouldUpdate: statsDataChanged,
    intervalMs: 3000,
    fastPoll,
  });

  const retries = stats.distill_live?.truncation_retries ?? [];
  if (retries.length === 0) {
    return null;
  }

  return (
    <div className="truncation-warning distill-live-alert" role="alert">
      <strong>蒸留再試行アラート:</strong> 同一条件の再生成が 3 回以上続いている項目が{" "}
      {retries.length} 件あります。プロンプト長や <code>num_predict</code>{" "}
      の見直しを検討してください。
    </div>
  );
}
