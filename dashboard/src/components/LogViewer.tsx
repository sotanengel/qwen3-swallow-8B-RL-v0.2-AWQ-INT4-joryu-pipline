"use client";

import { useEffect, useRef } from "react";

export type LogViewerProps = {
  logs: string;
  title?: string;
  emptyLabel?: string;
};

/**
 * ジョブログを表示する `<pre>` パネル。ログが末尾追加されたら自動でスクロール。
 */
export function LogViewer({
  logs,
  title,
  emptyLabel = "(ログなし)",
}: LogViewerProps) {
  const ref = useRef<HTMLPreElement>(null);

  useEffect(() => {
    if (ref.current) {
      ref.current.scrollTop = ref.current.scrollHeight;
    }
  }, [logs]);

  return (
    <>
      {title && <h2>{title}</h2>}
      <pre ref={ref} className="snippet log-panel" data-testid="log-viewer">
        {logs || emptyLabel}
      </pre>
    </>
  );
}
