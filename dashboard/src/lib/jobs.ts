export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

/** Python `joryu.jobs.models.DistillJobSpec` と同一フィールド。 */
export type DistillJobSpec = {
  count: number;
  duration: string;
  mode: string | null;
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
  modes: string[];
  styles: Array<{ id: string; label: string }>;
  tools: Array<{ id: string; description: string }>;
  defaults: {
    config: string;
    mode: string;
  };
};

export type CreateJobRequest = {
  count?: number;
  duration?: string;
  mode?: string | null;
  style?: string[];
  temperature?: string;
  top_p?: string;
  config?: string;
  tool_ids?: string[];
  tool_loop?: boolean;
  max_turns?: number | null;
};

export type LogResponse = {
  chunk: string;
  offset: number;
};

const API_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_JORYU_API_URL) ||
  "http://localhost:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export function parseJobRecord(data: unknown): JobRecord {
  const row = data as JobRecord;
  return {
    id: String(row.id),
    kind: String(row.kind ?? "distill"),
    spec: {
      count: Number(row.spec?.count ?? 0),
      duration: String(row.spec?.duration ?? ""),
      mode: row.spec?.mode ?? null,
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

export async function loadJobOptions(): Promise<JobOptions> {
  return apiFetch<JobOptions>("/api/jobs/options");
}

export async function listJobs(): Promise<JobRecord[]> {
  const rows = await apiFetch<unknown[]>("/api/jobs");
  return rows.map(parseJobRecord);
}

export async function createJob(body: CreateJobRequest): Promise<JobRecord> {
  const row = await apiFetch<unknown>("/api/jobs", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return parseJobRecord(row);
}

export async function getJob(id: string): Promise<JobRecord> {
  return parseJobRecord(await apiFetch<unknown>(`/api/jobs/${id}`));
}

export async function getJobLogs(id: string, offset = 0): Promise<LogResponse> {
  return apiFetch<LogResponse>(`/api/jobs/${id}/logs?offset=${offset}`);
}

export async function cancelJob(id: string): Promise<JobRecord> {
  const row = await apiFetch<unknown>(`/api/jobs/${id}/cancel`, { method: "POST" });
  return parseJobRecord(row);
}

export function statusLabel(status: JobStatus): string {
  switch (status) {
    case "queued":
      return "待機中";
    case "running":
      return "実行中";
    case "succeeded":
      return "成功";
    case "failed":
      return "失敗";
    case "cancelled":
      return "中止";
    default:
      return status;
  }
}

export function isJobActive(status: JobStatus): boolean {
  return status === "queued" || status === "running";
}
