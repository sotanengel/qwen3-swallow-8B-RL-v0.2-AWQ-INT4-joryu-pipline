"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { ChatColumn } from "@/components/ChatColumn";
import { createSession } from "@/lib/chat";
import { useChatColumns } from "@/lib/useChatColumns";
import { useCurateJobFastPoll } from "@/lib/useJobFastPoll";
import { useDistillJobFastPoll } from "@/lib/useDistillJobFastPoll";

export default function ChatPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [globalPrompt, setGlobalPrompt] = useState("");
  const [jobBlocked, setJobBlocked] = useState(false);
  const distillActive = useDistillJobFastPoll();
  const curateActive = useCurateJobFastPoll();
  const jobActive = distillActive || curateActive;
  const chatDisabled = jobActive || jobBlocked;

  const { columns, setColumnsFromSession, globalSending, sendGlobal, sendColumn } =
    useChatColumns({
      onJobBlocked: () => setJobBlocked(true),
      onSuccess: () => setJobBlocked(false),
    });

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
        setColumnsFromSession(session.columns);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    };
    void init();
  }, [setColumnsFromSession]);

  const isInitialPhase = useMemo(
    () => columns.length > 0 && columns.every((c) => c.turn_index === 0),
    [columns],
  );

  const handleGlobalSend = async (e: FormEvent) => {
    e.preventDefault();
    const prompt = globalPrompt.trim();
    if (!prompt || !sessionId || globalSending || chatDisabled) return;
    setError(null);
    setGlobalPrompt("");
    try {
      await sendGlobal(sessionId, prompt);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleColumnSend = async (styleId: string, prompt: string) => {
    if (!sessionId || chatDisabled) return;
    setError(null);
    try {
      await sendColumn(sessionId, styleId, prompt);
    } catch (err) {
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
