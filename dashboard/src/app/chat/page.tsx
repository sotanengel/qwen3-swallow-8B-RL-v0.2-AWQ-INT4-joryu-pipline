"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import {
  applyChatEvent,
  ChatColumn,
  type ColumnUiState,
} from "@/components/ChatColumn";
import {
  createSession,
  JobActiveError,
  streamColumnMessage,
  streamMessage,
  type ChatEvent,
} from "@/lib/chat";
import { useCurateJobFastPoll } from "@/lib/useJobFastPoll";
import { useDistillJobFastPoll } from "@/lib/useDistillJobFastPoll";

export default function ChatPage() {
  const [columns, setColumns] = useState<ColumnUiState[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [globalPrompt, setGlobalPrompt] = useState("");
  const [globalSending, setGlobalSending] = useState(false);
  const [jobBlocked, setJobBlocked] = useState(false);
  const distillActive = useDistillJobFastPoll();
  const curateActive = useCurateJobFastPoll();
  const jobActive = distillActive || curateActive;
  const chatDisabled = jobActive || jobBlocked;

  useEffect(() => {
    if (!jobActive) {
      setJobBlocked(false);
    }
  }, [jobActive]);

  useEffect(() => {
    const init = async () => {
      try {
        const session = await createSession();
        setSessionId(session.session_id);
        setColumns(
          session.columns.map((c) => ({
            ...c,
            messages: c.messages ?? [],
          })),
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    };
    void init();
  }, []);

  const isInitialPhase = useMemo(
    () => columns.length > 0 && columns.every((c) => c.turn_index === 0),
    [columns],
  );

  const handleEvent = useCallback((event: ChatEvent) => {
    setColumns((prev) => applyChatEvent(prev, event));
  }, []);

  const handleGlobalSend = async (e: FormEvent) => {
    e.preventDefault();
    const prompt = globalPrompt.trim();
    if (!prompt || !sessionId || globalSending || chatDisabled) return;
    setGlobalSending(true);
    setError(null);
    setColumns((prev) =>
      prev.map((c) => ({
        ...c,
        isStreaming: true,
        streamingText: "",
        toolCalls: [],
        messages: [...c.messages, { role: "user", content: prompt }],
      })),
    );
    setGlobalPrompt("");
    try {
      await streamMessage(sessionId, prompt, handleEvent);
    } catch (err) {
      if (err instanceof JobActiveError) {
        setJobBlocked(true);
      }
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setGlobalSending(false);
    }
  };

  const handleColumnSend = async (styleId: string, prompt: string) => {
    if (!sessionId || chatDisabled) return;
    setError(null);
    setColumns((prev) =>
      prev.map((c) =>
        c.style_id === styleId
          ? {
              ...c,
              isStreaming: true,
              streamingText: "",
              toolCalls: [],
              messages: [...c.messages, { role: "user", content: prompt }],
            }
          : c,
      ),
    );
    try {
      await streamColumnMessage(sessionId, styleId, prompt, handleEvent);
    } catch (err) {
      if (err instanceof JobActiveError) {
        setJobBlocked(true);
      }
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  if (loading) {
    return <p style={{ color: "var(--muted)" }}>セッションを初期化しています…</p>;
  }

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>インタラクティブチャット</h2>
      <p style={{ color: "var(--muted)", fontSize: "0.9rem" }}>
        全スタイルで並列比較。初回は共通入力、2 ターン目以降は列ごとに独立した対話ができます。
      </p>
      {chatDisabled ? (
        <div
          role="alert"
          style={{
            background: "#d4a72c33",
            border: "1px solid #d4a72c",
            borderRadius: "8px",
            padding: "0.75rem 1rem",
            marginBottom: "1rem",
            color: "var(--text)",
          }}
        >
          ジョブ実行中のためチャットを停止しています
        </div>
      ) : null}
      {error ? (
        <p style={{ color: "#f85149", marginBottom: "1rem" }}>{error}</p>
      ) : null}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${Math.max(columns.length, 1)}, minmax(280px, 1fr))`,
          gap: "1rem",
          overflowX: "auto",
          marginBottom: "1rem",
        }}
      >
        {columns.map((col) => (
          <ChatColumn
            key={col.style_id}
            column={col}
            showInput={!isInitialPhase}
            disabled={chatDisabled}
            onSend={handleColumnSend}
          />
        ))}
      </div>
      {isInitialPhase ? (
        <form
          onSubmit={(e) => void handleGlobalSend(e)}
          style={{
            position: "sticky",
            bottom: 0,
            background: "var(--bg)",
            padding: "1rem 0",
            borderTop: "1px solid var(--border)",
          }}
        >
          <textarea
            value={globalPrompt}
            onChange={(e) => setGlobalPrompt(e.target.value)}
            disabled={globalSending || chatDisabled}
            rows={3}
            placeholder="全スタイルに同じ質問を送信…"
            style={{
              width: "100%",
              resize: "vertical",
              background: "var(--surface)",
              color: "var(--text)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "0.75rem",
              marginBottom: "0.5rem",
            }}
          />
          <button
            type="submit"
            disabled={globalSending || chatDisabled || !globalPrompt.trim()}
            style={{
              padding: "0.6rem 1.25rem",
              background: "var(--accent)",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              cursor: globalSending ? "wait" : "pointer",
              opacity: globalSending ? 0.6 : 1,
            }}
          >
            {globalSending ? "送信中…" : "全列に送信"}
          </button>
        </form>
      ) : null}
    </div>
  );
}
