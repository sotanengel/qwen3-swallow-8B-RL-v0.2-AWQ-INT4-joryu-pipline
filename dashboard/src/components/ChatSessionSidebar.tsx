"use client";

import { useCallback, useEffect, useState } from "react";

import {
  createSession,
  deleteSession,
  fetchSessions,
  renameSession,
  type ChatSessionListItem,
} from "@/lib/chat";
import { setActiveSessionId } from "@/lib/chatSessionStorage";

type ChatSessionSidebarProps = {
  activeSessionId: string | null;
  onSelect: (sessionId: string) => void;
  onNewSession: (sessionId: string) => void;
  onDeleted: (sessionId: string) => void;
  refreshKey?: number;
};

function formatRelativeTime(epochSec: number): string {
  const diffMs = Date.now() - epochSec * 1000;
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return "たった今";
  if (diffMin < 60) return `${diffMin}分前`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}時間前`;
  const diffDay = Math.floor(diffHour / 24);
  return `${diffDay}日前`;
}

function displayTitle(item: ChatSessionListItem): string {
  return item.title?.trim() || "新しいセッション";
}

export function ChatSessionSidebar({
  activeSessionId,
  onSelect,
  onNewSession,
  onDeleted,
  refreshKey = 0,
}: ChatSessionSidebarProps) {
  const [items, setItems] = useState<ChatSessionListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchSessions();
      setItems(data.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload, refreshKey]);

  const handleNewSession = async () => {
    setError(null);
    try {
      const session = await createSession();
      setActiveSessionId(session.session_id);
      onNewSession(session.session_id);
      await reload();
      setDrawerOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleSelect = (sessionId: string) => {
    if (sessionId === activeSessionId) return;
    onSelect(sessionId);
    setDrawerOpen(false);
  };

  const handleDelete = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm("このセッションを削除しますか？")) return;
    setError(null);
    try {
      await deleteSession(sessionId);
      onDeleted(sessionId);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const startRename = (item: ChatSessionListItem, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(item.session_id);
    setEditTitle(displayTitle(item));
  };

  const commitRename = async (sessionId: string) => {
    const title = editTitle.trim();
    if (!title) {
      setEditingId(null);
      return;
    }
    setError(null);
    try {
      await renameSession(sessionId, title);
      setEditingId(null);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const sidebarBody = (
    <div className="chat-sidebar-body">
      <button type="button" className="chat-sidebar-new-btn" onClick={() => void handleNewSession()}>
        + 新しいセッション
      </button>
      {error ? <p className="chat-sidebar-error">{error}</p> : null}
      {loading ? (
        <p className="chat-sidebar-loading muted">読み込み中…</p>
      ) : (
        <ul className="chat-sidebar-list">
          {items.map((item) => {
            const active = item.session_id === activeSessionId;
            return (
              <li key={item.session_id} className="chat-sidebar-item">
                {editingId === item.session_id ? (
                  <form
                    className="chat-sidebar-rename-form"
                    onSubmit={(e) => {
                      e.preventDefault();
                      void commitRename(item.session_id);
                    }}
                  >
                    <input
                      className="chat-sidebar-rename-input"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      autoFocus
                    />
                    <button type="submit" className="chat-sidebar-rename-save secondary-btn">
                      保存
                    </button>
                  </form>
                ) : (
                  <div
                    role="button"
                    tabIndex={0}
                    className={`chat-sidebar-entry${active ? " chat-sidebar-entry--active" : ""}`}
                    onClick={() => handleSelect(item.session_id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") handleSelect(item.session_id);
                    }}
                  >
                    <div
                      className={`chat-sidebar-entry-title${active ? " chat-sidebar-entry-title--active" : ""}`}
                    >
                      {displayTitle(item)}
                    </div>
                    <div className="chat-sidebar-entry-meta">
                      <span>{formatRelativeTime(item.last_updated_at)}</span>
                      <span>{item.turn_count} ターン</span>
                    </div>
                    <div className="chat-sidebar-entry-actions">
                      <button
                        type="button"
                        aria-label="改名"
                        className="ghost-btn"
                        onClick={(e) => startRename(item, e)}
                      >
                        改名
                      </button>
                      <button
                        type="button"
                        aria-label="削除"
                        className="ghost-btn ghost-btn-danger"
                        onClick={(e) => void handleDelete(item.session_id, e)}
                      >
                        削除
                      </button>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );

  return (
    <>
      <button
        type="button"
        className="chat-sidebar-toggle"
        onClick={() => setDrawerOpen((v) => !v)}
        aria-expanded={drawerOpen}
      >
        セッション一覧
      </button>
      <aside
        className={`chat-session-sidebar${drawerOpen ? " chat-session-sidebar--open" : ""}`}
      >
        <div className="chat-session-sidebar-header">セッション</div>
        {sidebarBody}
      </aside>
    </>
  );
}
