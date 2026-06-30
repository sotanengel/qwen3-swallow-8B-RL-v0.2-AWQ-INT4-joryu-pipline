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
    return <p className="muted">セッションを初期化しています…</p>;
  }

  return (
    <div className="chat-layout">
      <ChatSessionSidebar
        activeSessionId={sessionId}
        onSelect={(id) => void handleSelectSession(id)}
        onNewSession={(id) => void handleNewSession(id)}
        onDeleted={(id) => void handleDeletedSession(id)}
        refreshKey={sidebarRefreshKey}
      />
      <div className="chat-main">
        <div className="page-header">
          <h2>インタラクティブチャット</h2>
          <p className="page-subtitle">
            全スタイルで並列比較。初回は共通入力、2 ターン目以降は列ごとに独立した対話ができます。
          </p>
        </div>
        {switching ? (
          <p className="muted" style={{ fontSize: "0.85rem" }}>
            セッションを切り替え中…
          </p>
        ) : null}
        {chatDisabled ? (
          <div className="warning-banner" role="alert">
            ジョブ実行中のためチャットを停止しています
          </div>
        ) : null}
        {error ? <p className="text-danger" style={{ marginBottom: "1rem" }}>{error}</p> : null}
        <div
          className="chat-columns"
          style={{
            gridTemplateColumns: `repeat(${Math.max(columns.length, 1)}, minmax(280px, 1fr))`,
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
          <form className="chat-input-bar" onSubmit={(e) => void handleGlobalSend(e)}>
            <textarea
              className="chat-global-textarea"
              value={globalPrompt}
              onChange={(e) => setGlobalPrompt(e.target.value)}
              disabled={globalSending || chatDisabled}
              rows={3}
              placeholder="全スタイルに同じ質問を送信…"
            />
            <button
              type="submit"
              className="chat-global-submit"
              disabled={globalSending || chatDisabled || !globalPrompt.trim()}
            >
              {globalSending ? "送信中…" : "全列に送信"}
            </button>
          </form>
        ) : null}
      </div>
    </div>
  );
}
