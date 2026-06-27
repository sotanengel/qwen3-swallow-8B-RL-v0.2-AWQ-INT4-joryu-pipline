import type { DistilledRecord } from "./jsonl";

export type ToolTimelineEvent =
  | {
      kind: "call";
      id: string;
      name: string;
      arguments: unknown;
    }
  | {
      kind: "result";
      id: string;
      name: string;
      content: string;
    }
  | {
      kind: "error";
      id: string;
      name: string;
      message: string;
    };

type Turn = {
  role?: string;
  name?: string;
  content?: string;
  tool_calls?: Array<{ name?: string; arguments?: unknown }>;
};

function callId(name: string, index: number): string {
  return `${name}-${index}`;
}

/** JSONL レコードからツール実行タイムラインを構築する。 */
export function extractToolEvents(record: DistilledRecord): ToolTimelineEvent[] {
  const events: ToolTimelineEvent[] = [];
  const turns = (record as DistilledRecord & { turns?: Turn[] }).turns ?? [];
  let index = 0;

  for (const turn of turns) {
    if (turn.role === "assistant" && turn.tool_calls?.length) {
      for (const tc of turn.tool_calls) {
        const name = tc.name ?? "unknown";
        const id = callId(name, index++);
        events.push({
          kind: "call",
          id,
          name,
          arguments: tc.arguments ?? {},
        });
      }
    }
    if (turn.role === "tool") {
      const name = turn.name ?? "unknown";
      const id = callId(name, Math.max(0, index - 1));
      const content = turn.content ?? "";
      if (content.startsWith("error:")) {
        events.push({
          kind: "error",
          id,
          name,
          message: content.slice("error:".length).trim(),
        });
      } else {
        events.push({ kind: "result", id, name, content });
      }
    }
  }

  const toolCalls =
    (record as DistilledRecord & { tool_calls?: Array<{ name?: string; arguments?: unknown }> })
      .tool_calls ?? [];
  if (events.length === 0 && toolCalls.length > 0) {
    toolCalls.forEach((tc, i) => {
      events.push({
        kind: "call",
        id: callId(tc.name ?? "unknown", i),
        name: tc.name ?? "unknown",
        arguments: tc.arguments ?? {},
      });
    });
  }

  return events;
}

export function toolEventPending(event: ToolTimelineEvent, events: ToolTimelineEvent[]): boolean {
  if (event.kind !== "call") return false;
  return !events.some(
    (other) =>
      other.id === event.id && (other.kind === "result" || other.kind === "error"),
  );
}
