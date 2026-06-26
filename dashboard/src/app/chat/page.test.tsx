// @vitest-environment jsdom

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ChatPage from "./page";

const mockCreateSession = vi.hoisted(() => vi.fn());
const mockStreamMessage = vi.hoisted(() => vi.fn());
const mockStreamColumnMessage = vi.hoisted(() => vi.fn());
const mockDistillFastPoll = vi.hoisted(() => vi.fn(() => false));
const mockCurateFastPoll = vi.hoisted(() => vi.fn(() => false));

vi.mock("@/lib/chat", () => ({
  createSession: (...args: unknown[]) => mockCreateSession(...args),
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

afterEach(() => {
  vi.clearAllMocks();
  mockDistillFastPoll.mockReturnValue(false);
  mockCurateFastPoll.mockReturnValue(false);
});

describe("ChatPage", () => {
  it("renders N style columns after session init", async () => {
    mockCreateSession.mockResolvedValue({
      session_id: "sess-1",
      columns: [
        { style_id: "prose", label: "散文", messages: [], turn_index: 0 },
        { style_id: "qa_short", label: "短答", messages: [], turn_index: 0 },
      ],
    });
    render(<ChatPage />);
    await waitFor(() => {
      expect(screen.getByText("散文")).toBeTruthy();
      expect(screen.getByText("短答")).toBeTruthy();
    });
    expect(screen.getByPlaceholderText("全スタイルに同じ質問を送信…")).toBeTruthy();
  });

  it("shows job-active banner when fast poll reports active job", async () => {
    mockDistillFastPoll.mockReturnValue(true);
    mockCreateSession.mockResolvedValue({
      session_id: "sess-1",
      columns: [{ style_id: "prose", label: "散文", messages: [], turn_index: 0 }],
    });
    render(<ChatPage />);
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toContain(
        "ジョブ実行中のためチャットを停止しています",
      );
    });
  });
});
