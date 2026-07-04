"use client";

import type { ReactNode } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { JOB_LIST_DISPLAY_LIMIT, isActiveStatus } from "@/lib/job-client";

export type JobRowLike = {
  id: string;
  status: string;
  created_at: string;
  finished_at?: string | null;
};

export type JobTableColumn<Row> = {
  key: string;
  header: string;
  render: (row: Row) => ReactNode;
};

export type JobTableProps<Row extends JobRowLike> = {
  jobs: Row[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onCancel: (row: Row) => void | Promise<void>;
  cancellingId?: string | null;
  extraColumns?: JobTableColumn<Row>[];
  cancelConfirmMessage?: string;
  emptyLabel?: string;
};

export function JobTable<Row extends JobRowLike>({
  jobs,
  selectedId,
  onSelect,
  onCancel,
  cancellingId,
  extraColumns = [],
  cancelConfirmMessage = "このジョブを停止しますか？",
  emptyLabel = "ジョブはまだありません。",
}: JobTableProps<Row>) {
  if (jobs.length === 0) {
    return <p className="muted">{emptyLabel}</p>;
  }

  const visibleJobs = jobs.slice(0, JOB_LIST_DISPLAY_LIMIT);

  const handleCancel = (row: Row) => {
    if (!isActiveStatus(row.status)) return;
    if (typeof window !== "undefined" && !window.confirm(cancelConfirmMessage)) {
      return;
    }
    void onCancel(row);
  };

  return (
    <table>
      <thead>
        <tr>
          <th>状態</th>
          <th>ID</th>
          {extraColumns.map((c) => (
            <th key={c.key}>{c.header}</th>
          ))}
          <th>作成</th>
          <th>終了</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        {visibleJobs.map((job) => (
          <tr
            key={job.id}
            className={`job-row-clickable${selectedId === job.id ? " row-selected" : ""}`}
            onClick={() => onSelect(job.id)}
            data-testid="job-row"
          >
            <td>
              <StatusBadge status={job.status} />
            </td>
            <td title={job.id}>{job.id.slice(0, 8)}…</td>
            {extraColumns.map((c) => (
              <td key={c.key}>{c.render(job)}</td>
            ))}
            <td>{new Date(job.created_at).toLocaleString()}</td>
            <td>
              {job.finished_at
                ? new Date(job.finished_at).toLocaleString()
                : "—"}
            </td>
            <td>
              {isActiveStatus(job.status) ? (
                <button
                  type="button"
                  className="danger-btn"
                  disabled={cancellingId === job.id}
                  onClick={(event) => {
                    event.stopPropagation();
                    handleCancel(job);
                  }}
                  data-testid="cancel-btn"
                >
                  {cancellingId === job.id ? "停止中…" : "停止"}
                </button>
              ) : (
                "—"
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
