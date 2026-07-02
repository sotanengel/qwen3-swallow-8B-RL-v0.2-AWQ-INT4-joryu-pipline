import {
  apiFetch,
  createJobClient,
  isActiveStatus,
  statusLabelJa,
  type BaseJobStatus,
  type LogResponse,
} from "./job-client";

export type JobStatus = BaseJobStatus;

/** Python `joryu.jobs.models.DistillJobSpec` と同一フィールド。 */
export type DistillJobSpec = {
  count: number;
  duration: string;
  style: string[];
  temperature: string;
  top_p: string;
  config: string;
  tool_ids: string[];
  tool_loop: boolean;
  max_turns: number | null;
};

export type JobRecord = {
  id: string;
  kind: string;
  spec: DistillJobSpec;
  status: JobStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  exit_code: number | null;
  error: string | null;
};

export type JobOptions = {
  styles: Array<{ id: string; label: string }>;
  tools: Array<{ id: string; description: string }>;
  defaults: {
    config: string;
  };
};

export type CreateJobRequest = {
  count?: number;
  duration?: string;
  style?: string[];
  temperature?: string;
  top_p?: string;
  config?: string;
  tool_ids?: string[];
  tool_loop?: boolean;
  max_turns?: number | null;
};

export type DurationUnit = "h" | "m";

export type { LogResponse };

export function formatJobDuration(value: number | "", unit: DurationUnit): string {
  if (value === "" || value <= 0) {
    return "";
  }
  return `${value}${unit}`;
}

export function defaultJobSelections(options: JobOptions): {
  styles: string[];
  toolIds: string[];
  toolLoop: true;
} {
  return {
    styles: options.styles.map((s) => s.id),
    toolIds: options.tools.map((t) => t.id),
    toolLoop: true,
  };
}

export function parseJobRecord(data: unknown): JobRecord {
  const row = data as JobRecord;
  return {
    id: String(row.id),
    kind: String(row.kind ?? "distill"),
    spec: {
      count: Number(row.spec?.count ?? 0),
      duration: String(row.spec?.duration ?? ""),
      style: Array.isArray(row.spec?.style) ? row.spec.style.map(String) : [],
      temperature: String(row.spec?.temperature ?? ""),
      top_p: String(row.spec?.top_p ?? ""),
      config: String(row.spec?.config ?? "config.yaml"),
      tool_ids: Array.isArray(row.spec?.tool_ids) ? row.spec.tool_ids.map(String) : [],
      tool_loop: Boolean(row.spec?.tool_loop),
      max_turns:
        row.spec?.max_turns === null || row.spec?.max_turns === undefined
          ? null
          : Number(row.spec.max_turns),
    },
    status: row.status,
    created_at: String(row.created_at),
    started_at: row.started_at ?? null,
    finished_at: row.finished_at ?? null,
    exit_code: row.exit_code ?? null,
    error: row.error ?? null,
  };
}

const distillClient = createJobClient<
  DistillJobSpec,
  CreateJobRequest,
  JobRecord
>({
  basePath: "/api/jobs",
  parseRecord: parseJobRecord,
});

export async function loadJobOptions(): Promise<JobOptions> {
  return apiFetch<JobOptions>("/api/jobs/options");
}

export const listJobs = () => distillClient.list();
export const createJob = (body: CreateJobRequest) => distillClient.create(body);
export const cancelJob = (id: string) => distillClient.cancel(id);
export const getJobLogs = (id: string, offset = 0) =>
  distillClient.getLogs(id, offset);

export function statusLabel(status: JobStatus): string {
  return statusLabelJa(status);
}

export function isJobActive(status: JobStatus): boolean {
  return isActiveStatus(status);
}
