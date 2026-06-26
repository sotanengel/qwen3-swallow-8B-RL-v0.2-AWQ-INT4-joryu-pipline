"use client";

import { FormEvent, useState } from "react";

import type { ChatColumnState, ChatEvent } from "@/lib/chat";

export type ToolCallDisplay = {
  call_id: string;
  name: string;
  arguments: unknown;
  result?: string;
};

export type ColumnUiState = ChatColumnState & {
  streamingText?: string;
  toolCalls?: ToolCallDisplay[];
  isStreaming?: boolean;
};

type ChatColumnProps = {
  column: ColumnUiState;
  showInput: boolean;
  disabled?: boolean;
  onSend: (styleId: string, prompt: string) => void;
};

export function ChatColumn({ column, showInput, disabled, onSend }: ChatColumnProps) {
  const [draft, setDraft] = useState("");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text || disabled || column.isStreaming) return;
    onSend(column.style_id, text);
    setDraft("");
  };

  return (
    <div
      className="card"
      style={{
        display: "flex",
        flexDirection: "column",
        minHeight: "420px",
        minWidth: "280px",
      }}
    >
      <h3 style={{ margin: "0 0 0.75rem", color: "var(--text)", textTransform: "none" }}>
        {column.label}
        <span style={{ color: "var(--muted)", fontSize: "0.75rem", marginLeft: "0.5rem" }}>
          ({column.style_id})
        </span>
      </h3>
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: "0.75rem",
          marginBottom: "0.75rem",
        }}
      >
        {column.messages.map((msg, idx) => (
          <div
            key={`${column.style_id}-msg-${idx}`}
            style={{
              padding: "0.5rem 0.75rem",
              borderRadius: "6px",
              background: msg.role === "user" ? "var(--accent-soft)" : "transparent",
              border: msg.role === "assistant" ? "1px solid var(--border)" : "none",
              fontSize: "0.9rem",
              whiteSpace: "pre-wrap",
            }}
          >
            <div style={{ color: "var(--muted)", fontSize: "0.7rem", marginBottom: "0.25rem" }}>
              {msg.role}
            </div>
            {msg.content}
          </div>
        ))}
        {column.isStreaming ? (
          <div
            style={{
              padding: "0.5rem 0.75rem",
              border: "1px dashed var(--border)",
              borderRadius: "6px",
              fontSize: "0.9rem",
              whiteSpace: "pre-wrap",
            }}
          >
            {column.streamingText ? (
              column.streamingText
            ) : (
              <span style={{ color: "var(--muted)" }}>考え中…</span>
            )}
          </div>
        ) : null}
        {(column.toolCalls ?? []).map((tc) => (
          <details
            key={tc.call_id}
            style={{
              border: "1px solid var(--border)",
              borderRadius: "6px",
              padding: "0.5rem",
              fontSize: "0.8rem",
            }}
          >
            <summary>
              tool: {tc.name}
              {tc.result !== undefined ? " (done)" : " (running…)"}
            </summary>
            <pre style={{ overflow: "auto", margin: "0.5rem 0 0" }}>
              {JSON.stringify(tc.arguments, null, 2)}
            </pre>
            {tc.result !== undefined ? (
              <pre style={{ overflow: "auto", margin: "0.5rem 0 0" }}>{tc.result}</pre>
            ) : null}
          </details>
        ))}
      </div>
      {showInput ? (
        <form onSubmit={handleSubmit} style={{ display: "flex", gap: "0.5rem" }}>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            disabled={disabled || column.isStreaming}
            rows={2}
            placeholder="追加質問…"
            style={{
              flex: 1,
              resize: "vertical",
              background: "var(--bg)",
              color: "var(--text)",
              border: "1px solid var(--border)",
              borderRadius: "6px",
              padding: "0.5rem",
              fontSize: "0.85rem",
            }}
          />
          <button
            type="submit"
            disabled={disabled || column.isStreaming || !draft.trim()}
            style={{
              alignSelf: "flex-end",
              padding: "0.5rem 0.75rem",
              background: "var(--accent)",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              cursor: disabled ? "not-allowed" : "pointer",
              opacity: disabled || column.isStreaming ? 0.5 : 1,
            }}
          >
            送信
          </button>
        </form>
      ) : null}
    </div>
  );
}

export function applyChatEvent(
  columns: ColumnUiState[],
  event: ChatEvent,
): ColumnUiState[] {
  if (event.type === "done") return columns;
  if (event.type === "error" && !("column" in event && event.column)) return columns;

  const colId = "column" in event ? event.column : undefined;
  if (!colId) return columns;

  return columns.map((col) => {
    if (col.style_id !== colId) return col;
    switch (event.type) {
      case "column_start":
        return {
          ...col,
          isStreaming: true,
          streamingText: col.streamingText ?? "",
        };
      case "turn_start":
        return {
          ...col,
          isStreaming: true,
          streamingText: col.streamingText ?? "",
        };
      case "token":
        return {
          ...col,
          isStreaming: true,
          streamingText: (col.streamingText ?? "") + event.delta,
        };
      case "tool_call": {
        const existing = col.toolCalls ?? [];
        return {
          ...col,
          toolCalls: [
            ...existing,
            {
              call_id: event.call_id,
              name: event.name,
              arguments: event.arguments,
            },
          ],
        };
      }
      case "tool_result": {
        const toolCalls = (col.toolCalls ?? []).map((tc) =>
          tc.call_id === event.call_id ? { ...tc, result: event.content } : tc,
        );
        return { ...col, toolCalls };
      }
      case "column_done":
        return {
          ...col,
          isStreaming: false,
          streamingText: undefined,
          toolCalls: undefined,
          turn_index: col.turn_index + 1,
          messages: col.streamingText
            ? [
                ...col.messages,
                { role: "assistant", content: col.streamingText },
              ]
            : col.messages,
        };
      default:
        return col;
    }
  });
}
