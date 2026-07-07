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
  (typeof window !== "undefined" ? "/joryu-api" : "http://localhost:8000");

/** FastAPI の HTTPException.detail (文字列 or オブジェクト) を人が読めるメッセージに整形する。 */
export function formatApiErrorDetail(detail: unknown): string | null {
  if (detail === null || detail === undefined) return null;
  if (typeof detail === "string") return detail.length > 0 ? detail : null;
  if (typeof detail !== "object") return String(detail);

  const obj = detail as Record<string, unknown>;
  const code = typeof obj.error === "string" ? obj.error : null;
  if (code) {
    const target = typeof obj.target === "string" ? obj.target : null;
    const required = typeof obj.required === "string" ? obj.required : null;
    const active = typeof obj.active === "string" ? obj.active : null;
    switch (code) {
      case "job_active":
        return "他のジョブが実行中です。完了を待つか中止してください。";
      case "wrong_profile":
        return `モデルプロファイルが不一致です (必要: ${required ?? "?"} / 現在: ${active ?? "なし"})。`;
      case "profile_switching":
        return `モデルプロファイル切替中です (対象: ${target ?? "?"})。しばらく待って再実行してください。`;
      case "profile_starting":
        return `モデルプロファイル起動中です (対象: ${target ?? "?"} / 必要: ${required ?? "?"})。しばらく待って再実行してください。`;
      default:
        return code;
    }
  }
  try {
    return JSON.stringify(detail);
  } catch {
    return String(detail);
  }
}

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
      const body = (await res.json()) as { detail?: unknown };
      const formatted = formatApiErrorDetail(body.detail);
      if (formatted) detail = formatted;
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
