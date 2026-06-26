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
};

const CHAT_BASE = "/api/chat";

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

async function consumeSse(
  path: string,
  body: { prompt: string },
  onEvent: (event: ChatEvent) => void,
): Promise<void> {
  const res = await fetch(`${CHAT_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  await checkResponse(res);
  const reader = res.body?.getReader();
  if (!reader) {
    throw new Error("no response body");
  }
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
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
}

export async function streamMessage(
  sessionId: string,
  prompt: string,
  onEvent: (event: ChatEvent) => void,
): Promise<void> {
  return consumeSse(
    `/sessions/${encodeURIComponent(sessionId)}/messages`,
    { prompt },
    onEvent,
  );
}

export async function streamColumnMessage(
  sessionId: string,
  styleId: string,
  prompt: string,
  onEvent: (event: ChatEvent) => void,
): Promise<void> {
  return consumeSse(
    `/sessions/${encodeURIComponent(sessionId)}/columns/${encodeURIComponent(styleId)}/messages`,
    { prompt },
    onEvent,
  );
}
