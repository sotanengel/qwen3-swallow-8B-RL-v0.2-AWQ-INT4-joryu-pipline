/** SSE イベントパーサ（テスト可能な純関数）。 */

export type ChatEvent =
  | { type: "token"; column: string; delta: string }
  | { type: "tool_call"; column: string; call_id: string; name: string; arguments: unknown }
  | { type: "tool_result"; column: string; call_id: string; content: string }
  | { type: "column_done"; column: string; finish_reason: string; record_id: string }
  | { type: "done"; session_id: string }
  | { type: "error"; column?: string; message: string };

export function parseSseBuffer(buffer: string): { events: ChatEvent[]; remainder: string } {
  const events: ChatEvent[] = [];
  const parts = buffer.split("\n\n");
  const remainder = parts.pop() ?? "";
  for (const block of parts) {
    const trimmed = block.trim();
    if (!trimmed) continue;
    let eventType = "";
    let dataLine = "";
    for (const line of trimmed.split("\n")) {
      if (line.startsWith("event: ")) {
        eventType = line.slice(7);
      } else if (line.startsWith("data: ")) {
        dataLine = line.slice(6);
      }
    }
    if (!eventType || !dataLine) continue;
    try {
      const payload = JSON.parse(dataLine) as Record<string, unknown>;
      events.push({ type: eventType, ...payload } as ChatEvent);
    } catch {
      events.push({ type: "error", message: `invalid SSE JSON: ${dataLine}` });
    }
  }
  return { events, remainder };
}

export function parseSseText(text: string): ChatEvent[] {
  const { events } = parseSseBuffer(text.endsWith("\n\n") ? text : `${text}\n\n`);
  return events;
}
