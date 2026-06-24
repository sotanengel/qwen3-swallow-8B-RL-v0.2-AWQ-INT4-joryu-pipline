export type DeleteOutputResponse = {
  deleted: number;
  remaining: number;
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

export async function deleteOutput(id: string): Promise<DeleteOutputResponse> {
  return apiFetch<DeleteOutputResponse>(`/api/dashboard/responses/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export async function deleteAllOutputs(): Promise<DeleteOutputResponse> {
  return apiFetch<DeleteOutputResponse>("/api/dashboard/responses", {
    method: "DELETE",
  });
}
