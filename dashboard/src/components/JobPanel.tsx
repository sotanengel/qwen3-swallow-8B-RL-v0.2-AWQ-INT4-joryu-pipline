"use client";

import type { ReactNode } from "react";

import { JobTable, type JobRowLike, type JobTableColumn } from "@/components/JobTable";
import { LogViewer } from "@/components/LogViewer";

export type JobPanelProps<Row extends JobRowLike> = {
  /** タイトル (省略可) */
  title?: string;
  /** サブタイトル */
  subtitle?: ReactNode;
  /** 投入フォーム */
  form: ReactNode;
  /** エラーメッセージ */
  error?: string | null;
  /** ジョブ一覧 */
  jobs: Row[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onCancel: (row: Row) => void | Promise<void>;
  cancellingId?: string | null;
  extraColumns?: JobTableColumn<Row>[];
  cancelConfirmMessage?: string;
  emptyJobsLabel?: string;
  jobsHeader?: string;
  /** 表示するログ */
  logs: string;
  logTitle?: string;
};

export function JobPanel<Row extends JobRowLike>({
  title,
  subtitle,
  form,
  error,
  jobs,
  selectedId,
  onSelect,
  onCancel,
  cancellingId,
  extraColumns,
  cancelConfirmMessage,
  emptyJobsLabel,
  jobsHeader = "ジョブ一覧",
  logs,
  logTitle,
}: JobPanelProps<Row>) {
  return (
    <>
      <section className="section">
        {title && <h2>{title}</h2>}
        {subtitle && <p className="section-subtitle">{subtitle}</p>}
        {error && <p className="error-banner">{error}</p>}
        {form}
      </section>

      <section className="section">
        <h2>{jobsHeader}</h2>
        <JobTable<Row>
          jobs={jobs}
          selectedId={selectedId}
          onSelect={onSelect}
          onCancel={onCancel}
          cancellingId={cancellingId}
          extraColumns={extraColumns}
          cancelConfirmMessage={cancelConfirmMessage}
          emptyLabel={emptyJobsLabel}
        />
      </section>

      {selectedId && (
        <section className="section">
          <LogViewer
            logs={logs}
            title={logTitle ?? `ログ — ${selectedId.slice(0, 8)}…`}
          />
        </section>
      )}
    </>
  );
}
