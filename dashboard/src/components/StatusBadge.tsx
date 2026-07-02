import { statusLabelJa, type BaseJobStatus } from "@/lib/job-client";

export type StatusBadgeProps = {
  status: BaseJobStatus | string;
};

export function StatusBadge({ status }: StatusBadgeProps) {
  return <span className={`badge badge-${status}`}>{statusLabelJa(status)}</span>;
}
