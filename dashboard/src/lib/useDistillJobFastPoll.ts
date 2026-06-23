"use client";

import { useEffect, useState } from "react";

import { isJobActive, listJobs } from "@/lib/jobs";

/** 蒸留ジョブが queued/running のとき true（stats ポーリング加速用）。 */
export function useDistillJobFastPoll(): boolean {
  const [fastPoll, setFastPoll] = useState(false);

  useEffect(() => {
    const check = async () => {
      try {
        const jobs = await listJobs();
        setFastPoll(jobs.some((j) => isJobActive(j.status)));
      } catch {
        /* API 未起動時は通常ポーリング */
      }
    };
    void check();
    const timer = setInterval(() => void check(), 3000);
    return () => clearInterval(timer);
  }, []);

  return fastPoll;
}
