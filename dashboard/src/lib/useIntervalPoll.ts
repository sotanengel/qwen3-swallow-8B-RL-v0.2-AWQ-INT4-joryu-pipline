"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const ADAPTIVE_FAST_MS = 1000;
const ADAPTIVE_DURATION_MS = 30_000;

export type UseIntervalPollOptions<T> = {
  enabled?: boolean;
  intervalMs?: number;
  /** ジョブ API 等で明示的に 1 秒ポーリングを有効化 */
  fastPoll?: boolean;
  shouldUpdate?: (prev: T, next: T) => boolean;
};

export function useIntervalPoll<T>(
  load: () => Promise<T>,
  initial: T,
  options: UseIntervalPollOptions<T> = {},
): T {
  const { enabled = true, intervalMs = 3000, fastPoll = false, shouldUpdate } = options;
  const [data, setData] = useState<T>(initial);
  const [fastUntil, setFastUntil] = useState(0);
  const loadRef = useRef(load);
  const shouldUpdateRef = useRef(shouldUpdate);

  loadRef.current = load;
  shouldUpdateRef.current = shouldUpdate;

  const effectiveInterval =
    fastPoll || Date.now() < fastUntil ? ADAPTIVE_FAST_MS : intervalMs;

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
        if (cmp && cmp(prev, next)) {
          setFastUntil(Date.now() + ADAPTIVE_DURATION_MS);
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
    const timer = setInterval(refresh, effectiveInterval);

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
  }, [enabled, effectiveInterval, refresh]);

  return data;
}
