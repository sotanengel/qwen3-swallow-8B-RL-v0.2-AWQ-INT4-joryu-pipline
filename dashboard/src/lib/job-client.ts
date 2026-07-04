export type BaseJobStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export type LogResponse = {
  chunk: string;
  offset: number;
};

/** ダッシュボード各ページのジョブ一覧テーブル表示上限 */
export const JOB_LIST_DISPLAY_LIMIT = 5;

const API_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_JORYU_API_URL) ||
  "http://localhost:8000";

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
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

export function statusLabelJa(status: BaseJobStatus | string): string {
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

export function isActiveStatus(status: BaseJobStatus | string): boolean {
  return status === "queued" || status === "running";
}

export interface JobClientOptions<Spec, CreateBody, Record, Status extends string> {
  /** e.g. "/api/jobs", "/api/seed-gen/jobs", "/api/curate/jobs" */
  basePath: string;
  /** Parse raw API row into a normalized record */
  parseRecord: (data: unknown) => Record;
  /** Optional: for shared type inference */
  _spec?: Spec;
  _createBody?: CreateBody;
  _status?: Status;
}

export interface JobClient<CreateBody, Record> {
  list: () => Promise<Record[]>;
  create: (body: CreateBody) => Promise<Record>;
  cancel: (id: string) => Promise<Record>;
  getLogs: (id: string, offset?: number) => Promise<LogResponse>;
}

export function createJobClient<
  Spec,
  CreateBody,
  Record,
  Status extends string = BaseJobStatus,
>(
  options: JobClientOptions<Spec, CreateBody, Record, Status>,
): JobClient<CreateBody, Record> {
  const { basePath, parseRecord } = options;

  return {
    async list() {
      const rows = await apiFetch<unknown[]>(basePath);
      return rows.map(parseRecord);
    },
    async create(body: CreateBody) {
      const row = await apiFetch<unknown>(basePath, {
        method: "POST",
        body: JSON.stringify(body),
      });
      return parseRecord(row);
    },
    async cancel(id: string) {
      const row = await apiFetch<unknown>(`${basePath}/${id}/cancel`, {
        method: "POST",
      });
      return parseRecord(row);
    },
    async getLogs(id: string, offset = 0) {
      return apiFetch<LogResponse>(`${basePath}/${id}/logs?offset=${offset}`);
    },
  };
}
