"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type UseIntervalPollOptions<T> = {
  enabled?: boolean;
  intervalMs?: number;
  shouldUpdate?: (prev: T, next: T) => boolean;
};

export function useIntervalPoll<T>(
  load: () => Promise<T>,
  initial: T,
  options: UseIntervalPollOptions<T> = {},
): T {
  const { enabled = true, intervalMs = 3000, shouldUpdate } = options;
  const [data, setData] = useState<T>(initial);
  const loadRef = useRef(load);
  const shouldUpdateRef = useRef(shouldUpdate);

  loadRef.current = load;
  shouldUpdateRef.current = shouldUpdate;

  const refresh = useCallback(async () => {
    if (typeof document !== "undefined" && document.visibilityState !== "visible") {
      return;
    }
    try {
      const next = await loadRef.current();
      setData((prev) => {
        const cmp = shouldUpdateRef.current;
        if (cmp && !cmp(prev, next)) {
          return prev;
        }
        return next;
      });
    } catch {
      /* ignore transient fetch errors during polling */
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;

    refresh();
    const timer = setInterval(refresh, intervalMs);

    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        refresh();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [enabled, intervalMs, refresh]);

  return data;
}
