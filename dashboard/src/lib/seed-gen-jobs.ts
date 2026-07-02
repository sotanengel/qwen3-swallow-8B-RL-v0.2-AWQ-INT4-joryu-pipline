import {
  apiFetch,
  createJobClient,
  isActiveStatus,
  statusLabelJa,
  type BaseJobStatus,
} from "./job-client";

export type SeedGenJobStatus = BaseJobStatus;

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

const seedGenClient = createJobClient<
  SeedGenJobSpec,
  Partial<SeedGenJobSpec>,
  SeedGenJobRecord
>({
  basePath: "/api/seed-gen/jobs",
  parseRecord: parseSeedGenJobRecord,
});

export async function loadSeedGenStatus(): Promise<SeedGenStatus> {
  return apiFetch<SeedGenStatus>("/api/seed-gen/status");
}

export const listSeedGenJobs = () => seedGenClient.list();
export const createSeedGenJob = (body: Partial<SeedGenJobSpec>) =>
  seedGenClient.create(body);
export const cancelSeedGenJob = (id: string) => seedGenClient.cancel(id);
export const getSeedGenJobLogs = (id: string, offset = 0) =>
  seedGenClient.getLogs(id, offset);

export async function appendManualPrompt(
  prompt: string,
  domain: string,
): Promise<{ id: string; domain: string }> {
  return apiFetch("/api/seed-gen/prompts", {
    method: "POST",
    body: JSON.stringify({ prompt, domain }),
  });
}

export function isSeedGenJobActive(status: SeedGenJobStatus): boolean {
  return isActiveStatus(status);
}

export function seedGenModeLabel(mode: SeedGenMode): string {
  return mode === "check" ? "チェック" : "作成";
}

export function seedGenStatusLabel(status: SeedGenJobStatus): string {
  return statusLabelJa(status);
}
