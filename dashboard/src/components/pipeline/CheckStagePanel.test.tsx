// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CheckStagePanel } from "./CheckStagePanel";

const listPromptBank = vi.hoisted(() =>
  vi.fn(() =>
    Promise.resolve({
      total: 1,
      checked_total: 0,
      unchecked_total: 1,
      offset: 0,
      limit: 50,
      items: [
        {
          key: "id:abc",
          id: "abc",
          prompt: "test prompt",
          prompt_preview: "test prompt",
          domain: "math",
          category: null,
          checked: false,
        },
      ],
    }),
  ),
);

vi.mock("@/lib/seed-gen-jobs", () => ({
  listPromptBank,
  loadPromptCheckStatus: vi.fn(() =>
    Promise.resolve({
      bank_total: 1,
      checked_count: 0,
      unchecked_count: 1,
      check_completed: false,
    }),
  ),
  listSeedGenJobs: vi.fn(() => Promise.resolve([])),
  createSeedGenJob: vi.fn(),
  cancelSeedGenJob: vi.fn(),
  getSeedGenJobLogs: vi.fn(() => Promise.resolve("")),
  markPromptsChecked: vi.fn(),
  isSeedGenJobActive: vi.fn(() => false),
  seedGenModeLabel: (m: string) => m,
}));

vi.mock("@/lib/curate-jobs", () => ({
  createCurateJob: vi.fn(),
}));

vi.mock("@/lib/useJobList", () => ({
  useJobList: () => [[], vi.fn(), null] as const,
}));

vi.mock("@/lib/useJobLogs", () => ({
  useJobLogs: () => "",
}));

vi.mock("@/lib/useIntervalPoll", () => ({
  useIntervalPoll: <T,>(_fn: () => Promise<T>, fallback: T) => fallback,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("CheckStagePanel", () => {
  it("lists only unchecked prompts", async () => {
    render(<CheckStagePanel />);
    await waitFor(() => expect(listPromptBank).toHaveBeenCalled());
    expect(listPromptBank.mock.calls[0][0]).toMatchObject({ checked: "unchecked" });
  });

  it("does not show checked status column values", async () => {
    render(<CheckStagePanel />);
    await waitFor(() => expect(screen.getByText("test prompt")).toBeTruthy());
    expect(screen.queryByText("済")).toBeNull();
    expect(screen.queryByText("未")).toBeNull();
  });
});
