import {
  apiFetch,
  createJobClient,
  isActiveStatus,
  statusLabelJa,
  type BaseJobStatus,
  type LogResponse,
} from "./job-client";

export type CurateJobStatus = BaseJobStatus;

export type CurateJobSpec = {
  config: string;
  skip_llm: boolean;
  threshold: number | null;
  screening: boolean;
  prompt_bank: boolean;
  src: string;
};

export type CurateJobRecord = {
  id: string;
  kind: string;
  spec: CurateJobSpec;
  status: CurateJobStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  exit_code: number | null;
  error: string | null;
};

export type CurateJobOptions = {
  defaults: { config: string; skip_llm: boolean };
  input_ready: boolean;
  vllm_available: boolean;
};

export type CreateCurateJobRequest = {
  skip_llm?: boolean;
  threshold?: number | null;
  config?: string;
  screening?: boolean;
  prompt_bank?: boolean;
  src?: string;
};

export type { LogResponse };

export function parseCurateJobRecord(data: unknown): CurateJobRecord {
  const row = data as CurateJobRecord;
  return {
    id: String(row.id),
    kind: String(row.kind ?? "curate"),
    spec: {
      config: String(row.spec?.config ?? "config.yaml"),
      skip_llm: Boolean(row.spec?.skip_llm),
      threshold:
        row.spec?.threshold === null || row.spec?.threshold === undefined
          ? null
          : Number(row.spec.threshold),
      screening: Boolean(row.spec?.screening),
      prompt_bank: Boolean(row.spec?.prompt_bank),
      src: String(row.spec?.src ?? ""),
    },
    status: row.status,
    created_at: String(row.created_at),
    started_at: row.started_at ?? null,
    finished_at: row.finished_at ?? null,
    exit_code: row.exit_code ?? null,
    error: row.error ?? null,
  };
}

const curateClient = createJobClient<
  CurateJobSpec,
  CreateCurateJobRequest,
  CurateJobRecord
>({
  basePath: "/api/curate/jobs",
  parseRecord: parseCurateJobRecord,
});

export async function loadCurateJobOptions(): Promise<CurateJobOptions> {
  return apiFetch<CurateJobOptions>("/api/curate/jobs/options");
}

export const listCurateJobs = () => curateClient.list();
export const createCurateJob = (body: CreateCurateJobRequest) =>
  curateClient.create(body);
export const cancelCurateJob = (id: string) => curateClient.cancel(id);
export const getCurateJobLogs = (id: string, offset = 0) =>
  curateClient.getLogs(id, offset);

export function isCurateJobActive(status: CurateJobStatus): boolean {
  return isActiveStatus(status);
}

export function curateStatusLabel(status: CurateJobStatus): string {
  return statusLabelJa(status);
}
