// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PromptsStagePanel } from "./PromptsStagePanel";

const mockStatus = {
  bank_total: 10,
  target_total: 100,
  domains: [
    { key: "general_qa", target: 50, current: 5, ratio: 0.1 },
    { key: "math", target: 30, current: 3, ratio: 0.1 },
  ],
  state_updated_at: null,
  running_job_ids: [],
};

vi.mock("@/lib/seed-gen-jobs", () => ({
  loadSeedGenStatus: vi.fn(() => Promise.resolve(mockStatus)),
  listSeedGenJobs: vi.fn(() => Promise.resolve([])),
  createSeedGenJob: vi.fn(),
  cancelSeedGenJob: vi.fn(),
  getSeedGenJobLogs: vi.fn(() => Promise.resolve("")),
  appendManualPrompt: vi.fn(),
  isSeedGenJobActive: vi.fn(() => false),
  seedGenModeLabel: (m: string) => m,
}));

vi.mock("@/lib/useJobList", () => ({
  useJobList: () => [[], vi.fn(), null] as const,
}));

vi.mock("@/lib/useJobLogs", () => ({
  useJobLogs: () => "",
}));

vi.mock("@/lib/useIntervalPoll", () => ({
  useIntervalPoll: <T,>(_fn: () => Promise<T>, fallback: T) => fallback ?? mockStatus,
}));

afterEach(() => cleanup());

describe("PromptsStagePanel", () => {
  it("renders domain selects with options from status", async () => {
    render(<PromptsStagePanel />);
    await waitFor(() => {
      const selects = screen.getAllByRole("combobox");
      expect(selects).toHaveLength(2);
      expect(selects[0].querySelector('option[value=""]')?.textContent).toBe("全分野");
      expect(selects[0].querySelector('option[value="math"]')).toBeTruthy();
      expect(selects[1].querySelector('option[value="general_qa"]')).toBeTruthy();
    });
  });

  it("wraps domain progress in a collapsible details element", async () => {
    render(<PromptsStagePanel />);
    await waitFor(() => {
      const details = document.querySelector("details");
      expect(details).toBeTruthy();
      expect(details?.querySelector("summary")?.textContent).toContain("分野進捗");
      expect(details?.querySelector("table")).toBeTruthy();
    });
  });
});
