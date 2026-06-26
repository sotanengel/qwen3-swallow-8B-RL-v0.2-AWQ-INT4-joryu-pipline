import { describe, expect, it } from "vitest";

import { applyChatEvent, type ColumnUiState } from "@/components/ChatColumn";

const baseColumn = (): ColumnUiState => ({
  style_id: "prose",
  label: "散文",
  messages: [],
  turn_index: 0,
});

describe("applyChatEvent", () => {
  it("appends streaming tokens", () => {
    const next = applyChatEvent([baseColumn()], {
      type: "token",
      column: "prose",
      delta: "hello",
    });
    expect(next[0]?.streamingText).toBe("hello");
    expect(next[0]?.isStreaming).toBe(true);
  });

  it("records tool_call and tool_result", () => {
    let cols = applyChatEvent([baseColumn()], {
      type: "tool_call",
      column: "prose",
      call_id: "c1",
      name: "search",
      arguments: { query: "x" },
    });
    cols = applyChatEvent(cols, {
      type: "tool_result",
      column: "prose",
      call_id: "c1",
      content: "result",
    });
    expect(cols[0]?.toolCalls).toHaveLength(1);
    expect(cols[0]?.toolCalls?.[0]?.result).toBe("result");
  });

  it("finalizes column on column_done", () => {
    let cols = applyChatEvent([baseColumn()], {
      type: "token",
      column: "prose",
      delta: "answer",
    });
    cols = applyChatEvent(cols, {
      type: "column_done",
      column: "prose",
      finish_reason: "stop",
      record_id: "abc",
    });
    expect(cols[0]?.turn_index).toBe(1);
    expect(cols[0]?.messages.at(-1)?.content).toBe("answer");
  });
});
