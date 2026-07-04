// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CurateStagePanel } from "./CurateStagePanel";

const createCurateJob = vi.hoisted(() =>
  vi.fn(() =>
    Promise.resolve({
      id: "job-1",
      kind: "curate",
      spec: { config: "config.yaml", skip_llm: false, threshold: 0.7 },
      status: "queued",
      created_at: "2026-01-01T00:00:00Z",
      started_at: null,
      finished_at: null,
      exit_code: null,
      error: null,
    }),
  ),
);

vi.mock("@/lib/curate-jobs", () => ({
  loadCurateJobOptions: vi.fn(() =>
    Promise.resolve({ input_ready: true, vllm_available: false }),
  ),
  listCurateJobs: vi.fn(() => Promise.resolve([])),
  createCurateJob,
  cancelCurateJob: vi.fn(),
  getCurateJobLogs: vi.fn(() => Promise.resolve("")),
  isCurateJobActive: vi.fn(() => false),
}));

vi.mock("@/lib/useJobList", () => ({
  useJobList: () => [[], vi.fn(), null] as const,
}));

vi.mock("@/lib/useJobLogs", () => ({
  useJobLogs: () => "",
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("CurateStagePanel", () => {
  it("does not render the LLM judge skip checkbox", async () => {
    render(<CurateStagePanel />);
    await waitFor(() => expect(screen.getByRole("button", { name: "高品質抽出を実行" })).toBeTruthy());
    expect(screen.queryByLabelText(/スキップ/)).toBeNull();
  });

  it("submits curate job without skip_llm", async () => {
    render(<CurateStagePanel />);
    await waitFor(() => expect(screen.getByRole("button", { name: "高品質抽出を実行" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "高品質抽出を実行" }));
    await waitFor(() => expect(createCurateJob).toHaveBeenCalled());
    expect(createCurateJob.mock.calls[0][0]).toEqual({ skip_llm: false });
  });
});
