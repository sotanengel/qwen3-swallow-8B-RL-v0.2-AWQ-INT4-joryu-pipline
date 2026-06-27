"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { ChatColumn } from "@/components/ChatColumn";
import { ChatSessionSidebar } from "@/components/ChatSessionSidebar";
import { createSession, fetchSession } from "@/lib/chat";
import {
  clearActiveSessionId,
  getActiveSessionId,
  setActiveSessionId,
} from "@/lib/chatSessionStorage";
import { useChatColumns } from "@/lib/useChatColumns";
import { useCurateJobFastPoll } from "@/lib/useJobFastPoll";
import { useDistillJobFastPoll } from "@/lib/useDistillJobFastPoll";

export default function ChatPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [globalPrompt, setGlobalPrompt] = useState("");
  const [jobBlocked, setJobBlocked] = useState(false);
  const [sidebarRefreshKey, setSidebarRefreshKey] = useState(0);
  const distillActive = useDistillJobFastPoll();
  const curateActive = useCurateJobFastPoll();
  const jobActive = distillActive || curateActive;
  const chatDisabled = jobActive || jobBlocked;

  const { columns, setColumnsFromSession, globalSending, sendGlobal, sendColumn } =
    useChatColumns({
      onJobBlocked: () => setJobBlocked(true),
      onSuccess: () => setJobBlocked(false),
    });

  const applySession = useCallback(
    (id: string, session: Awaited<ReturnType<typeof fetchSession>>) => {
      setSessionId(id);
      setActiveSessionId(id);
      setColumnsFromSession(session.columns);
    },
    [setColumnsFromSession],
  );

  const loadSession = useCallback(
    async (id: string) => {
      setSwitching(true);
      setError(null);
      try {
        const session = await fetchSession(id);
        applySession(id, session);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        throw e;
      } finally {
        setSwitching(false);
      }
    },
    [applySession],
  );

  useEffect(() => {
    if (!jobActive) {
      setJobBlocked(false);
    }
  }, [jobActive]);

  useEffect(() => {
    const init = async () => {
      try {
        const savedId = getActiveSessionId();
        if (savedId) {
          try {
            const session = await fetchSession(savedId);
            applySession(savedId, session);
            return;
          } catch {
            clearActiveSessionId();
          }
        }
        const session = await createSession();
        applySession(session.session_id, session);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    };
    void init();
  }, [applySession]);

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
      setSidebarRefreshKey((k) => k + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleColumnSend = async (styleId: string, prompt: string) => {
    if (!sessionId || chatDisabled) return;
    setError(null);
    try {
      await sendColumn(sessionId, styleId, prompt);
      setSidebarRefreshKey((k) => k + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleSelectSession = async (id: string) => {
    if (id === sessionId) return;
    try {
      await loadSession(id);
    } catch {
      // error state already set
    }
  };

  const handleNewSession = async (id: string) => {
    try {
      const session = await fetchSession(id);
      applySession(id, session);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleDeletedSession = async (deletedId: string) => {
    if (deletedId !== sessionId) return;
    clearActiveSessionId();
    try {
      const session = await createSession();
      applySession(session.session_id, session);
      setSidebarRefreshKey((k) => k + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  if (loading) {
    return <p style={{ color: "var(--muted)" }}>セッションを初期化しています…</p>;
  }

  return (
    <div style={{ display: "flex", gap: "0", alignItems: "stretch" }}>
      <ChatSessionSidebar
        activeSessionId={sessionId}
        onSelect={(id) => void handleSelectSession(id)}
        onNewSession={(id) => void handleNewSession(id)}
        onDeleted={(id) => void handleDeletedSession(id)}
        refreshKey={sidebarRefreshKey}
      />
      <div style={{ flex: 1, minWidth: 0, paddingLeft: "1rem" }}>
        <h2 style={{ marginTop: 0 }}>インタラクティブチャット</h2>
        <p style={{ color: "var(--muted)", fontSize: "0.9rem" }}>
          全スタイルで並列比較。初回は共通入力、2 ターン目以降は列ごとに独立した対話ができます。
        </p>
        {switching ? (
          <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>セッションを切り替え中…</p>
        ) : null}
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
    </div>
  );
}
