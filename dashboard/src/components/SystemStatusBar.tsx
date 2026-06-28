"use client";

import { useEffect, useState } from "react";

import {
  EMPTY_SYSTEM_STATUS,
  SystemStatus,
  formatSystemStatusLine,
  loadSystemStatus,
} from "@/lib/system";

export function SystemStatusBar() {
  const [status, setStatus] = useState<SystemStatus>(EMPTY_SYSTEM_STATUS);

  useEffect(() => {
    let source: EventSource | null = null;
    let cancelled = false;

    loadSystemStatus()
      .then((snap) => {
        if (!cancelled) setStatus(snap);
      })
      .catch(() => undefined);

    try {
      source = new EventSource("/joryu-api/api/system/models/stream");
      source.onmessage = (event) => {
        try {
          setStatus(JSON.parse(event.data) as SystemStatus);
        } catch {
          /* ignore malformed SSE */
        }
      };
    } catch {
      const id = setInterval(() => {
        loadSystemStatus()
          .then((snap) => setStatus(snap))
          .catch(() => undefined);
      }, 5000);
      return () => {
        cancelled = true;
        clearInterval(id);
      };
    }

    return () => {
      cancelled = true;
      source?.close();
    };
  }, []);

  return (
    <div className="system-status" data-testid="system-status">
      LLM: {formatSystemStatusLine(status)}
    </div>
  );
}
