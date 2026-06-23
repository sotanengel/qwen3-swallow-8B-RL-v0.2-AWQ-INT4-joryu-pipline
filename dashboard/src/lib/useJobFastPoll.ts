"use client";

import { useEffect, useState } from "react";

import { isCurateJobActive, listCurateJobs } from "@/lib/curate-jobs";
import { isJobActive, listJobs } from "@/lib/jobs";

export type JobFastPollKind = "distill" | "curate";

async function hasActiveJob(kind: JobFastPollKind): Promise<boolean> {
  if (kind === "curate") {
    const jobs = await listCurateJobs();
    return jobs.some((j) => isCurateJobActive(j.status));
  }
  const jobs = await listJobs();
  return jobs.some(
    (j) => (j.kind ?? "distill") === "distill" && isJobActive(j.status),
  );
}

/** 指定種別のジョブが queued/running のとき true（ポーリング加速用）。 */
export function useJobFastPoll(kind: JobFastPollKind): boolean {
  const [fastPoll, setFastPoll] = useState(false);

  useEffect(() => {
    const check = async () => {
      try {
        setFastPoll(await hasActiveJob(kind));
      } catch {
        /* API 未起動時は通常ポーリング */
      }
    };
    void check();
    const timer = setInterval(() => void check(), 3000);
    return () => clearInterval(timer);
  }, [kind]);

  return fastPoll;
}

/** 蒸留ジョブが queued/running のとき true（stats ポーリング加速用）。 */
export function useDistillJobFastPoll(): boolean {
  return useJobFastPoll("distill");
}

/** 高品質抽出ジョブが queued/running のとき true（curation ポーリング加速用）。 */
export function useCurateJobFastPoll(): boolean {
  return useJobFastPoll("curate");
}
