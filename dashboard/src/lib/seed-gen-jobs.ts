export type SeedGenJobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export type SeedGenMode = "create" | "check";

export type SeedGenJobSpec = {
  bank: string;
  domains_config: string;
  domain: string;
  target_total: number;
  mode: SeedGenMode;
  resume: boolean;
  sim_threshold: number;
  batch_size: number;
  config: string;
};

export type SeedGenJobRecord = {
  id: string;
  kind: string;
  spec: SeedGenJobSpec;
  status: SeedGenJobStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  exit_code: number | null;
  error: string | null;
};

export type DomainProgress = {
  key: string;
  target: number;
  current: number;
  ratio: number;
};

export type SeedGenStatus = {
  bank_total: number;
  target_total: number;
  domains: DomainProgress[];
  state_updated_at: string | null;
  running_job_ids: string[];
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

export function parseSeedGenJobRecord(data: unknown): SeedGenJobRecord {
  const row = data as SeedGenJobRecord;
  return {
    id: String(row.id),
    kind: String(row.kind ?? "seed_gen"),
    spec: {
      bank: String(row.spec?.bank ?? ""),
      domains_config: String(row.spec?.domains_config ?? ""),
      domain: String(row.spec?.domain ?? ""),
      target_total: Number(row.spec?.target_total ?? 230000),
      mode: (row.spec?.mode === "check" ? "check" : "create") as SeedGenMode,
      resume: Boolean(row.spec?.resume),
      sim_threshold: Number(row.spec?.sim_threshold ?? 0.85),
      batch_size: Number(row.spec?.batch_size ?? 8),
      config: String(row.spec?.config ?? "config.yaml"),
    },
    status: row.status,
    created_at: String(row.created_at),
    started_at: row.started_at ?? null,
    finished_at: row.finished_at ?? null,
    exit_code: row.exit_code ?? null,
    error: row.error ?? null,
  };
}

export async function loadSeedGenStatus(): Promise<SeedGenStatus> {
  return apiFetch<SeedGenStatus>("/api/seed-gen/status");
}

export async function listSeedGenJobs(): Promise<SeedGenJobRecord[]> {
  const rows = await apiFetch<unknown[]>("/api/seed-gen/jobs");
  return rows.map(parseSeedGenJobRecord);
}

export async function createSeedGenJob(body: Partial<SeedGenJobSpec>): Promise<SeedGenJobRecord> {
  const row = await apiFetch<unknown>("/api/seed-gen/jobs", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return parseSeedGenJobRecord(row);
}

export async function getSeedGenJobLogs(id: string, offset = 0): Promise<{ chunk: string; offset: number }> {
  return apiFetch(`/api/seed-gen/jobs/${id}/logs?offset=${offset}`);
}

export async function cancelSeedGenJob(id: string): Promise<SeedGenJobRecord> {
  const row = await apiFetch<unknown>(`/api/seed-gen/jobs/${id}/cancel`, { method: "POST" });
  return parseSeedGenJobRecord(row);
}

export async function appendManualPrompt(prompt: string, domain: string): Promise<{ id: string; domain: string }> {
  return apiFetch("/api/seed-gen/prompts", {
    method: "POST",
    body: JSON.stringify({ prompt, domain }),
  });
}

export function isSeedGenJobActive(status: SeedGenJobStatus): boolean {
  return status === "queued" || status === "running";
}

export function seedGenModeLabel(mode: SeedGenMode): string {
  return mode === "check" ? "チェック" : "作成";
}

export function seedGenStatusLabel(status: SeedGenJobStatus): string {
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
