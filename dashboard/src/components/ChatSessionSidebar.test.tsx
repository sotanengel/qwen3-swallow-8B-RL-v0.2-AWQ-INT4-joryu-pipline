// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatSessionSidebar } from "./ChatSessionSidebar";

const mockFetchSessions = vi.hoisted(() => vi.fn());
const mockCreateSession = vi.hoisted(() => vi.fn());
const mockDeleteSession = vi.hoisted(() => vi.fn());
const mockRenameSession = vi.hoisted(() => vi.fn());

vi.mock("@/lib/chat", () => ({
  fetchSessions: (...args: unknown[]) => mockFetchSessions(...args),
  createSession: (...args: unknown[]) => mockCreateSession(...args),
  deleteSession: (...args: unknown[]) => mockDeleteSession(...args),
  renameSession: (...args: unknown[]) => mockRenameSession(...args),
}));

vi.mock("@/lib/chatSessionStorage", () => ({
  setActiveSessionId: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ChatSessionSidebar", () => {
  it("lists sessions and calls onSelect", async () => {
    mockFetchSessions.mockResolvedValue({
      items: [
        {
          session_id: "a",
          title: "Alpha",
          created_at: 1,
          last_updated_at: 2,
          turn_count: 1,
        },
        {
          session_id: "b",
          title: null,
          created_at: 1,
          last_updated_at: 1,
          turn_count: 0,
        },
      ],
      next_cursor: null,
    });
    const onSelect = vi.fn();
    render(
      <ChatSessionSidebar
        activeSessionId="a"
        onSelect={onSelect}
        onNewSession={vi.fn()}
        onDeleted={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(screen.getByText("Alpha")).toBeTruthy();
      expect(screen.getByText("新しいセッション")).toBeTruthy();
    });
    fireEvent.click(screen.getByText("新しいセッション"));
    expect(onSelect).toHaveBeenCalledWith("b");
  });

  it("creates new session via + button", async () => {
    mockFetchSessions.mockResolvedValue({ items: [], next_cursor: null });
    mockCreateSession.mockResolvedValue({
      session_id: "new-id",
      columns: [],
    });
    const onNewSession = vi.fn();
    render(
      <ChatSessionSidebar
        activeSessionId={null}
        onSelect={vi.fn()}
        onNewSession={onNewSession}
        onDeleted={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(screen.getByText("+ 新しいセッション")).toBeTruthy();
    });
    fireEvent.click(screen.getByText("+ 新しいセッション"));
    await waitFor(() => {
      expect(mockCreateSession).toHaveBeenCalled();
      expect(onNewSession).toHaveBeenCalledWith("new-id");
    });
  });

  it("renames session", async () => {
    mockFetchSessions.mockResolvedValue({
      items: [
        {
          session_id: "a",
          title: "Old",
          created_at: 1,
          last_updated_at: 2,
          turn_count: 0,
        },
      ],
      next_cursor: null,
    });
    mockRenameSession.mockResolvedValue({
      session_id: "a",
      title: "New Title",
      created_at: 1,
      last_updated_at: 3,
      turn_count: 0,
    });
    render(
      <ChatSessionSidebar
        activeSessionId="a"
        onSelect={vi.fn()}
        onNewSession={vi.fn()}
        onDeleted={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(screen.getByText("Old")).toBeTruthy();
    });
    fireEvent.click(screen.getByLabelText("改名"));
    const input = screen.getByDisplayValue("Old");
    fireEvent.change(input, { target: { value: "New Title" } });
    fireEvent.submit(input.closest("form")!);
    await waitFor(() => {
      expect(mockRenameSession).toHaveBeenCalledWith("a", "New Title");
    });
  });
});
