// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ChatPage from "./page";
import {
  getActiveSessionId,
  setActiveSessionId,
} from "@/lib/chatSessionStorage";

const mockCreateSession = vi.hoisted(() => vi.fn());
const mockFetchSession = vi.hoisted(() => vi.fn());
const mockFetchSessions = vi.hoisted(() => vi.fn());
const mockDeleteSession = vi.hoisted(() => vi.fn());
const mockRenameSession = vi.hoisted(() => vi.fn());
const mockStreamMessage = vi.hoisted(() => vi.fn());
const mockStreamColumnMessage = vi.hoisted(() => vi.fn());
const mockDistillFastPoll = vi.hoisted(() => vi.fn(() => false));
const mockCurateFastPoll = vi.hoisted(() => vi.fn(() => false));

vi.mock("@/lib/chat", () => ({
  createSession: (...args: unknown[]) => mockCreateSession(...args),
  fetchSession: (...args: unknown[]) => mockFetchSession(...args),
  fetchSessions: (...args: unknown[]) => mockFetchSessions(...args),
  deleteSession: (...args: unknown[]) => mockDeleteSession(...args),
  renameSession: (...args: unknown[]) => mockRenameSession(...args),
  streamMessage: (...args: unknown[]) => mockStreamMessage(...args),
  streamColumnMessage: (...args: unknown[]) => mockStreamColumnMessage(...args),
  JobActiveError: class JobActiveError extends Error {
    name = "JobActiveError";
  },
}));

vi.mock("@/lib/useDistillJobFastPoll", () => ({
  useDistillJobFastPoll: () => mockDistillFastPoll(),
}));

vi.mock("@/lib/useJobFastPoll", () => ({
  useCurateJobFastPoll: () => mockCurateFastPoll(),
}));

const sampleColumns = [
  { style_id: "prose", label: "散文", messages: [], turn_index: 0 },
  { style_id: "qa_short", label: "短答", messages: [], turn_index: 0 },
];

beforeEach(() => {
  localStorage.clear();
  mockFetchSessions.mockResolvedValue({ items: [], next_cursor: null });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  localStorage.clear();
  mockDistillFastPoll.mockReturnValue(false);
  mockCurateFastPoll.mockReturnValue(false);
});

describe("ChatPage", () => {
  it("renders N style columns after session init", async () => {
    mockCreateSession.mockResolvedValue({
      session_id: "sess-1",
      columns: sampleColumns,
    });
    render(<ChatPage />);
    await waitFor(() => {
      expect(screen.getByText("散文")).toBeTruthy();
      expect(screen.getByText("短答")).toBeTruthy();
    });
    expect(document.querySelector(".chat-layout")).toBeTruthy();
    expect(document.querySelector(".chat-main")).toBeTruthy();
    expect(screen.getByPlaceholderText("全スタイルに同じ質問を送信…")).toBeTruthy();
  });

  it("restores session from localStorage without createSession", async () => {
    setActiveSessionId("saved-sess");
    mockFetchSession.mockResolvedValue({
      session_id: "saved-sess",
      columns: sampleColumns,
    });
    render(<ChatPage />);
    await waitFor(() => {
      expect(screen.getByText("散文")).toBeTruthy();
    });
    expect(mockFetchSession).toHaveBeenCalledWith("saved-sess");
    expect(mockCreateSession).not.toHaveBeenCalled();
    expect(getActiveSessionId()).toBe("saved-sess");
  });

  it("falls back to createSession when fetchSession fails", async () => {
    setActiveSessionId("missing-sess");
    mockFetchSession.mockRejectedValue(new Error("404"));
    mockCreateSession.mockResolvedValue({
      session_id: "new-sess",
      columns: sampleColumns,
    });
    render(<ChatPage />);
    await waitFor(() => {
      expect(screen.getByText("散文")).toBeTruthy();
    });
    expect(mockCreateSession).toHaveBeenCalled();
    expect(getActiveSessionId()).toBe("new-sess");
  });

  it("shows job-active banner when fast poll reports active job", async () => {
    mockDistillFastPoll.mockReturnValue(true);
    mockCreateSession.mockResolvedValue({
      session_id: "sess-1",
      columns: [sampleColumns[0]],
    });
    render(<ChatPage />);
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toContain(
        "ジョブ実行中のためチャットを停止しています",
      );
    });
  });

  it("clears job-active banner when fast poll becomes inactive", async () => {
    mockDistillFastPoll.mockReturnValue(true);
    mockCreateSession.mockResolvedValue({
      session_id: "sess-1",
      columns: [sampleColumns[0]],
    });
    const { unmount } = render(<ChatPage />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeTruthy();
    });
    mockDistillFastPoll.mockReturnValue(false);
    unmount();
    render(<ChatPage />);
    await waitFor(() => {
      expect(screen.queryByRole("alert")).toBeNull();
    });
  });
});
