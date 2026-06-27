import { parseSseBuffer, type ChatEvent } from "./sse-parse";
import { checkResponse, JobActiveError } from "./api/errors";

export type { ChatEvent } from "./sse-parse";
export { parseSseBuffer, parseSseText } from "./sse-parse";
export { JobActiveError } from "./api/errors";

export type ChatStyle = {
  style_id: string;
  label: string;
};

export type ChatMessage = {
  role: string;
  content: string;
  tool_calls?: Array<{ name: string; arguments: unknown }>;
  name?: string;
  call_id?: string;
};

export type ChatColumnState = {
  style_id: string;
  label: string;
  messages: ChatMessage[];
  turn_index: number;
};

export type ChatSessionState = {
  session_id: string;
  columns: ChatColumnState[];
  title?: string | null;
};

export type ChatSessionListItem = {
  session_id: string;
  title: string | null;
  created_at: number;
  last_updated_at: number;
  turn_count: number;
};

export type ChatSessionListResponse = {
  items: ChatSessionListItem[];
  next_cursor: string | null;
};

const CHAT_BASE = "/api/chat";
export const STREAM_IDLE_TIMEOUT_MS = 60_000;

async function chatFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${CHAT_BASE}${path}`, {
    ...init,
    cache: "no-store",
  });
  await checkResponse(res);
  return res.json() as Promise<T>;
}

export async function fetchStyles(): Promise<ChatStyle[]> {
  return chatFetch<ChatStyle[]>("/styles");
}

export async function createSession(): Promise<ChatSessionState> {
  return chatFetch<ChatSessionState>("/sessions", { method: "POST" });
}

export async function fetchSession(sessionId: string): Promise<ChatSessionState> {
  return chatFetch<ChatSessionState>(`/sessions/${encodeURIComponent(sessionId)}`);
}

export async function fetchSessions(
  limit = 20,
  cursor?: string,
): Promise<ChatSessionListResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set("cursor", cursor);
  return chatFetch<ChatSessionListResponse>(`/sessions?${params.toString()}`);
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetch(`${CHAT_BASE}/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
    cache: "no-store",
  });
  await checkResponse(res);
}

export async function renameSession(sessionId: string, title: string): Promise<ChatSessionListItem> {
  return chatFetch<ChatSessionListItem>(`/sessions/${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
}

async function consumeSse(
  path: string,
  body: { prompt: string },
  onEvent: (event: ChatEvent) => void,
  options?: { signal?: AbortSignal },
): Promise<void> {
  const controller = new AbortController();
  const parentSignal = options?.signal;
  if (parentSignal?.aborted) {
    controller.abort();
  } else {
    parentSignal?.addEventListener("abort", () => controller.abort(), { once: true });
  }

  let idleTimer: ReturnType<typeof setTimeout> | undefined;
  const resetIdleTimer = () => {
    if (idleTimer !== undefined) clearTimeout(idleTimer);
    idleTimer = setTimeout(() => controller.abort(), STREAM_IDLE_TIMEOUT_MS);
  };

  const res = await fetch(`${CHAT_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
    signal: controller.signal,
  });
  await checkResponse(res);
  const reader = res.body?.getReader();
  if (!reader) {
    throw new Error("no response body");
  }
  const decoder = new TextDecoder();
  let buffer = "";
  resetIdleTimer();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      resetIdleTimer();
      buffer += decoder.decode(value, { stream: true });
      const { events, remainder } = parseSseBuffer(buffer);
      buffer = remainder;
      for (const event of events) {
        onEvent(event);
      }
    }
    if (buffer.trim()) {
      const { events } = parseSseBuffer(`${buffer}\n\n`);
      for (const event of events) {
        onEvent(event);
      }
    }
  } finally {
    if (idleTimer !== undefined) clearTimeout(idleTimer);
  }
}

export async function streamMessage(
  sessionId: string,
  prompt: string,
  onEvent: (event: ChatEvent) => void,
  options?: { signal?: AbortSignal },
): Promise<void> {
  return consumeSse(
    `/sessions/${encodeURIComponent(sessionId)}/messages`,
    { prompt },
    onEvent,
    options,
  );
}

export async function streamColumnMessage(
  sessionId: string,
  styleId: string,
  prompt: string,
  onEvent: (event: ChatEvent) => void,
  options?: { signal?: AbortSignal },
): Promise<void> {
  return consumeSse(
    `/sessions/${encodeURIComponent(sessionId)}/columns/${encodeURIComponent(styleId)}/messages`,
    { prompt },
    onEvent,
    options,
  );
}
