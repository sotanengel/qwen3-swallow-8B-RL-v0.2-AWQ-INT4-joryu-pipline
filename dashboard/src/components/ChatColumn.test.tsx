import { describe, expect, it } from "vitest";

import { applyChatEvent, type ColumnUiState } from "@/components/ChatColumn";

const baseColumn = (): ColumnUiState => ({
  style_id: "prose",
  label: "散文",
  messages: [],
  turn_index: 0,
});

describe("applyChatEvent", () => {
  it("sets streaming state on column_start", () => {
    const next = applyChatEvent([baseColumn()], {
      type: "column_start",
      column: "prose",
    });
    expect(next[0]?.isStreaming).toBe(true);
    expect(next[0]?.streamingText).toBe("");
  });

  it("sets streaming state on turn_start", () => {
    const next = applyChatEvent([baseColumn()], {
      type: "turn_start",
      column: "prose",
      turn: 1,
    });
    expect(next[0]?.isStreaming).toBe(true);
  });

  it("finalizes only the target column on column_done", () => {
    const cols: ColumnUiState[] = [
      { ...baseColumn(), style_id: "prose", label: "散文" },
      { ...baseColumn(), style_id: "qa_short", label: "短答" },
    ];
    let updated = applyChatEvent(cols, {
      type: "token",
      column: "prose",
      delta: "done-first",
    });
    updated = applyChatEvent(updated, {
      type: "column_done",
      column: "prose",
      finish_reason: "stop",
      record_id: "abc",
    });
    expect(updated[0]?.turn_index).toBe(1);
    expect(updated[0]?.isStreaming).toBe(false);
    expect(updated[1]?.turn_index).toBe(0);
    expect(updated[1]?.isStreaming).toBeUndefined();
  });

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

  it("applyChatEvent on done resolves stuck isStreaming columns", () => {
    const cols: ColumnUiState[] = [
      { ...baseColumn(), isStreaming: true, streamingText: "partial" },
      { ...baseColumn(), style_id: "qa_short", label: "短答", isStreaming: true },
    ];
    const next = applyChatEvent(cols, { type: "done", session_id: "s1" });
    expect(next[0]?.isStreaming).toBe(false);
    expect(next[1]?.isStreaming).toBe(false);
    expect(next[0]?.messages.at(-1)?.content).toBe("partial");
    expect(next[1]?.messages.at(-1)?.content).toBe("(応答が途中で切れました)");
  });

  it("clears streaming state on column error event", () => {
    let cols = applyChatEvent([{ ...baseColumn(), isStreaming: true }], {
      type: "error",
      column: "prose",
      message: "boom",
    });
    expect(cols[0]?.isStreaming).toBe(false);
    expect(cols[0]?.messages.at(-1)?.content).toBe("boom");
  });
});
