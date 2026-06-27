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
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <button
        type="button"
        onClick={() => void handleNewSession()}
        style={{
          margin: "0.75rem",
          padding: "0.55rem 0.75rem",
          background: "var(--accent)",
          color: "#fff",
          border: "none",
          borderRadius: "6px",
          cursor: "pointer",
          fontWeight: 600,
        }}
      >
        + 新しいセッション
      </button>
      {error ? (
        <p style={{ color: "#f85149", fontSize: "0.85rem", padding: "0 0.75rem" }}>{error}</p>
      ) : null}
      {loading ? (
        <p style={{ color: "var(--muted)", padding: "0 0.75rem", fontSize: "0.85rem" }}>
          読み込み中…
        </p>
      ) : (
        <ul
          style={{
            listStyle: "none",
            margin: 0,
            padding: "0 0.5rem 0.75rem",
            overflowY: "auto",
            flex: 1,
          }}
        >
          {items.map((item) => {
            const active = item.session_id === activeSessionId;
            return (
              <li key={item.session_id} style={{ marginBottom: "0.35rem" }}>
                {editingId === item.session_id ? (
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      void commitRename(item.session_id);
                    }}
                    style={{ display: "flex", gap: "0.25rem", padding: "0.25rem" }}
                  >
                    <input
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      autoFocus
                      style={{
                        flex: 1,
                        background: "var(--surface)",
                        color: "var(--text)",
                        border: "1px solid var(--border)",
                        borderRadius: "4px",
                        padding: "0.25rem 0.4rem",
                        fontSize: "0.85rem",
                      }}
                    />
                    <button type="submit" style={{ fontSize: "0.75rem" }}>
                      保存
                    </button>
                  </form>
                ) : (
                  <div
                    role="button"
                    tabIndex={0}
                    onClick={() => handleSelect(item.session_id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") handleSelect(item.session_id);
                    }}
                    style={{
                      padding: "0.55rem 0.65rem",
                      borderRadius: "6px",
                      cursor: "pointer",
                      background: active ? "var(--surface)" : "transparent",
                      border: active ? "1px solid var(--accent)" : "1px solid transparent",
                    }}
                  >
                    <div
                      style={{
                        fontSize: "0.9rem",
                        fontWeight: active ? 600 : 400,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {displayTitle(item)}
                    </div>
                    <div
                      style={{
                        fontSize: "0.75rem",
                        color: "var(--muted)",
                        marginTop: "0.15rem",
                        display: "flex",
                        justifyContent: "space-between",
                        gap: "0.5rem",
                      }}
                    >
                      <span>{formatRelativeTime(item.last_updated_at)}</span>
                      <span>{item.turn_count} ターン</span>
                    </div>
                    <div
                      style={{
                        marginTop: "0.35rem",
                        display: "flex",
                        gap: "0.35rem",
                      }}
                    >
                      <button
                        type="button"
                        aria-label="改名"
                        onClick={(e) => startRename(item, e)}
                        style={{
                          fontSize: "0.7rem",
                          padding: "0.15rem 0.35rem",
                          background: "transparent",
                          border: "1px solid var(--border)",
                          borderRadius: "4px",
                          color: "var(--muted)",
                          cursor: "pointer",
                        }}
                      >
                        改名
                      </button>
                      <button
                        type="button"
                        aria-label="削除"
                        onClick={(e) => void handleDelete(item.session_id, e)}
                        style={{
                          fontSize: "0.7rem",
                          padding: "0.15rem 0.35rem",
                          background: "transparent",
                          border: "1px solid var(--border)",
                          borderRadius: "4px",
                          color: "#f85149",
                          cursor: "pointer",
                        }}
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
        style={{
          display: "none",
          marginBottom: "0.75rem",
          padding: "0.5rem 0.75rem",
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "6px",
          color: "var(--text)",
          cursor: "pointer",
        }}
      >
        セッション一覧
      </button>
      <aside
        className={`chat-session-sidebar${drawerOpen ? " chat-session-sidebar--open" : ""}`}
        style={{
          width: "240px",
          flexShrink: 0,
          borderRight: "1px solid var(--border)",
          background: "var(--bg)",
          minHeight: "60vh",
        }}
      >
        <div style={{ padding: "0.75rem 0.75rem 0", fontWeight: 600, fontSize: "0.95rem" }}>
          セッション
        </div>
        {sidebarBody}
      </aside>
      <style jsx global>{`
        @media (max-width: 767px) {
          .chat-sidebar-toggle {
            display: inline-block !important;
          }
          .chat-session-sidebar {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            bottom: 0;
            z-index: 40;
            box-shadow: 0 0 24px rgba(0, 0, 0, 0.25);
          }
          .chat-session-sidebar--open {
            display: block;
          }
        }
      `}</style>
    </>
  );
}
