"use client";

import { useEffect, useState } from "react";

import type { LogResponse } from "./job-client";

export type UseJobLogsOptions = {
  intervalMs?: number;
};

/**
 * jobId が変わったら 0 から取り直し、offset を持ち回して差分 chunk を末尾に連結する。
 * jobId=null のときはポーリング停止・ログ空。
 */
export function useJobLogs(
  jobId: string | null,
  getLogs: (id: string, offset: number) => Promise<LogResponse>,
  options: UseJobLogsOptions = {},
): string {
  const { intervalMs = 3000 } = options;
  const [logs, setLogs] = useState("");

  useEffect(() => {
    if (!jobId) {
      setLogs("");
      return;
    }

    let cancelled = false;
    let offset = 0;
    setLogs("");

    const poll = async () => {
      try {
        const res = await getLogs(jobId, offset);
        if (cancelled) return;
        if (res.chunk) {
          setLogs((prev) => prev + res.chunk);
        }
        offset = res.offset;
      } catch {
        /* ignore transient errors */
      }
    };

    void poll();
    const timer = setInterval(() => void poll(), intervalMs);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
    // getLogs はキャプチャした関数として使う。ジョブ切替以外で再構築させない。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, intervalMs]);

  return logs;
}
