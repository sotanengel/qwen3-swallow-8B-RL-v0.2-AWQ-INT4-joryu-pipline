"use client";

import { useCallback, useEffect, useState } from "react";

export type UseJobListOptions = {
  intervalMs?: number;
};

/**
 * ジョブ一覧を取得し、アクティブジョブがある間だけ intervalMs 間隔で再取得する。
 * 返り値は [rows, refresh, error].
 */
export function useJobList<Row>(
  loader: () => Promise<Row[]>,
  isActive: (row: Row) => boolean,
  options: UseJobListOptions = {},
): [Row[], () => Promise<void>, string | null] {
  const { intervalMs = 3000 } = options;
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await loader();
      setRows(next);
      setError(null);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    }
    // loader を dep に入れると呼び出し側で毎回作り直すたびに再取得が走るため意図的に外す
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const hasActive = rows.some(isActive);
    if (!hasActive) return;
    const timer = setInterval(() => void refresh(), intervalMs);
    return () => clearInterval(timer);
  }, [rows, isActive, refresh, intervalMs]);

  return [rows, refresh, error];
}
