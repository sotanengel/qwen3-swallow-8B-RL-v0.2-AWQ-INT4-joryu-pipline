"use client";

import { FormEvent, useState } from "react";

import { MarkdownView } from "@/components/MarkdownView";
import type { ChatColumnState, ChatEvent } from "@/lib/chat";

export type ToolCallDisplay = {
  call_id: string;
  name: string;
  arguments: unknown;
  result?: string;
  error?: string;
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
    <div className="card chat-column">
      <h3 className="chat-column-title">
        {column.label}
        <span className="chat-column-title-id">({column.style_id})</span>
      </h3>
      <div className="chat-messages">
        {column.messages.map((msg, idx) => (
          <div
            key={`${column.style_id}-msg-${idx}`}
            className={`chat-message chat-message--${msg.role}`}
          >
            <div className="chat-message-role">{msg.role}</div>
            <div className="chat-message-markdown">
              <MarkdownView source={msg.content} />
            </div>
          </div>
        ))}
        {column.isStreaming ? (
          <div className="chat-message chat-message--streaming">
            {column.streamingText ? (
              <div className="chat-message-markdown">
                <MarkdownView source={column.streamingText} />
              </div>
            ) : (
              <span className="muted">考え中…</span>
            )}
          </div>
        ) : null}
        {(column.toolCalls ?? []).map((tc) => (
          <details key={tc.call_id} className="chat-tool-details">
            <summary>
              tool: {tc.name}
              {tc.error ? " (error)" : tc.result !== undefined ? " (done)" : " (running…)"}
            </summary>
            <pre className="chat-tool-pre">{JSON.stringify(tc.arguments, null, 2)}</pre>
            {tc.error ? <pre className="chat-tool-pre chat-tool-pre--error">{tc.error}</pre> : null}
            {tc.result !== undefined ? <pre className="chat-tool-pre">{tc.result}</pre> : null}
          </details>
        ))}
      </div>
      {showInput ? (
        <form className="chat-column-form" onSubmit={handleSubmit}>
          <textarea
            className="chat-column-textarea"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            disabled={disabled || column.isStreaming}
            rows={2}
            placeholder="追加質問…"
          />
          <button
            type="submit"
            className="chat-column-submit"
            disabled={disabled || column.isStreaming || !draft.trim()}
          >
            送信
          </button>
        </form>
      ) : null}
    </div>
  );
}

export function finalizeColumnDefensively(
  column: ColumnUiState,
  fallbackText = "(応答が途中で切れました)",
): ColumnUiState {
  if (!column.isStreaming) return column;
  return {
    ...column,
    isStreaming: false,
    streamingText: undefined,
    toolCalls: undefined,
    turn_index: column.turn_index + 1,
    messages: column.streamingText
      ? [...column.messages, { role: "assistant", content: column.streamingText }]
      : [...column.messages, { role: "assistant", content: fallbackText }],
  };
}

export function applyChatEvent(
  columns: ColumnUiState[],
  event: ChatEvent,
): ColumnUiState[] {
  if (event.type === "done") {
    return columns.map((col) => finalizeColumnDefensively(col));
  }
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
      case "tool_error": {
        const toolCalls = (col.toolCalls ?? []).map((tc) =>
          tc.call_id === event.call_id ? { ...tc, error: event.message } : tc,
        );
        return { ...col, toolCalls };
      }
      case "error":
        return finalizeColumnDefensively(col, event.message);
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
