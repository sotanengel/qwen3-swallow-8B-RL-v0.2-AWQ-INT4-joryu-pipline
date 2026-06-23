export type CurateJobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export type CurateJobSpec = {
  config: string;
  skip_llm: boolean;
  threshold: number | null;
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
    },
    status: row.status,
    created_at: String(row.created_at),
    started_at: row.started_at ?? null,
    finished_at: row.finished_at ?? null,
    exit_code: row.exit_code ?? null,
    error: row.error ?? null,
  };
}

export async function loadCurateJobOptions(): Promise<CurateJobOptions> {
  return apiFetch<CurateJobOptions>("/api/curate/jobs/options");
}

export async function listCurateJobs(): Promise<CurateJobRecord[]> {
  const rows = await apiFetch<unknown[]>("/api/curate/jobs");
  return rows.map(parseCurateJobRecord);
}

export async function createCurateJob(body: CreateCurateJobRequest): Promise<CurateJobRecord> {
  const row = await apiFetch<unknown>("/api/curate/jobs", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return parseCurateJobRecord(row);
}

export async function getCurateJobLogs(id: string, offset = 0): Promise<LogResponse> {
  return apiFetch<LogResponse>(`/api/curate/jobs/${id}/logs?offset=${offset}`);
}

export async function cancelCurateJob(id: string): Promise<CurateJobRecord> {
  const row = await apiFetch<unknown>(`/api/curate/jobs/${id}/cancel`, { method: "POST" });
  return parseCurateJobRecord(row);
}

export function isCurateJobActive(status: CurateJobStatus): boolean {
  return status === "queued" || status === "running";
}

export function curateStatusLabel(status: CurateJobStatus): string {
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
