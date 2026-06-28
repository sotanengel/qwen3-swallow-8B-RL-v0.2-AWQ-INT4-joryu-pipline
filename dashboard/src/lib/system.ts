/** ModelProfile FSM 状態 (SSE / snapshot)。 */

export type ProfileStatus = {
  name: string;
  ready: boolean;
  port: number;
  service: string;
  kind: string;
};

export type SystemStatus = {
  status: string;
  active: string | null;
  target: string | null;
  error: string | null;
  progress: string | null;
  ready: boolean;
  profiles: ProfileStatus[];
};

export const EMPTY_SYSTEM_STATUS: SystemStatus = {
  status: "stopped",
  active: null,
  target: null,
  error: null,
  progress: null,
  ready: false,
  profiles: [],
};

export async function loadSystemStatus(): Promise<SystemStatus> {
  const res = await fetch("/joryu-api/api/system/models", { cache: "no-store" });
  if (!res.ok) {
    return EMPTY_SYSTEM_STATUS;
  }
  return (await res.json()) as SystemStatus;
}

export function formatSystemStatusLine(status: SystemStatus): string {
  if (status.error) {
    return `error: ${status.error}`;
  }
  if (status.status === "switching" && status.active && status.target) {
    return `switching ${status.active}→${status.target}${status.progress ? ` (${status.progress})` : ""}`;
  }
  if (status.status === "starting" && status.target) {
    return `starting ${status.target}${status.progress ? ` (${status.progress})` : ""}`;
  }
  if (status.active) {
    const activeProfile = status.profiles.find((p) => p.name === status.active);
    const ready = activeProfile?.ready ? "ready" : "not ready";
    return `active=${status.active} ${ready}`;
  }
  return `status=${status.status}`;
}

export function profileReady(status: SystemStatus, name: string): boolean {
  return status.profiles.find((p) => p.name === name)?.ready ?? false;
}
