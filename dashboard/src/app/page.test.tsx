// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import HomePage from "./page";

const mockPush = vi.hoisted(() => vi.fn());
const mockSearchParamsGet = vi.hoisted(() =>
  vi.fn((_key: string): string | null => null),
);

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => ({ get: mockSearchParamsGet }),
}));

vi.mock("@/components/pipeline/PromptsStagePanel", () => ({
  PromptsStagePanel: () => <div data-testid="panel-prompts">PROMPTS</div>,
}));
vi.mock("@/components/pipeline/CheckStagePanel", () => ({
  CheckStagePanel: () => <div data-testid="panel-check">CHECK</div>,
}));
vi.mock("@/components/pipeline/DistillStagePanel", () => ({
  DistillStagePanel: ({ checkCompleted }: { checkCompleted: boolean }) => (
    <div data-testid="panel-distill" data-check={String(checkCompleted)}>
      DISTILL
    </div>
  ),
}));
vi.mock("@/components/pipeline/CurateStagePanel", () => ({
  CurateStagePanel: () => <div data-testid="panel-curate">CURATE</div>,
}));

vi.mock("@/lib/stats", () => ({
  EMPTY_STATS: { total: 0 },
  loadStats: vi.fn(() => Promise.resolve({ total: 0 })),
  statsDataChanged: () => false,
}));
vi.mock("@/lib/seed-gen-jobs", async () => {
  const actual = await vi.importActual<typeof import("@/lib/seed-gen-jobs")>(
    "@/lib/seed-gen-jobs",
  );
  return {
    ...actual,
    loadSeedGenStatus: vi.fn(() => Promise.resolve(null)),
    loadPromptCheckStatus: vi.fn(() =>
      Promise.resolve({
        bank_total: 1,
        checked_count: 0,
        unchecked_count: 1,
        check_completed: false,
      }),
    ),
  };
});
vi.mock("@/lib/screening", () => ({
  EMPTY_SCREENING: { total: 0 },
  loadScreening: vi.fn(() => Promise.resolve({ total: 0 })),
  screeningDataChanged: () => false,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  mockSearchParamsGet.mockReturnValue(null);
});

describe("HomePage (Pipeline Hub)", () => {
  it("renders the 5 stages in order: prompts -> check -> distill -> curate -> screening", async () => {
    render(<HomePage />);
    await waitFor(() => expect(screen.getByTestId("pipeline-stages")).toBeTruthy());
    const cards = screen.getByTestId("pipeline-stages").querySelectorAll('[data-testid^="pipeline-stage-"]');
    // 5 cards × (card wrapper + metric + button) — filter for the card wrappers only
    const stageIds = Array.from(cards)
      .map((c) => c.getAttribute("data-testid"))
      .filter((id) => id && !id.includes("-metric") && !id.includes("-btn"));
    expect(stageIds).toEqual([
      "pipeline-stage-prompts",
      "pipeline-stage-check",
      "pipeline-stage-distill",
      "pipeline-stage-curate",
      "pipeline-stage-screening",
    ]);
  });

  it("check stage is presented as an independent stage with LLM linkage in its description", async () => {
    render(<HomePage />);
    await waitFor(() => expect(screen.getByTestId("pipeline-stage-check")).toBeTruthy());
    const card = screen.getByTestId("pipeline-stage-check");
    expect(card.textContent).toContain("プロンプトチェック");
    expect(card.textContent).toContain("LLM 品質スクリーニング");
  });

  it("defaults to the prompts stage when ?stage= is missing", async () => {
    render(<HomePage />);
    await waitFor(() => expect(screen.getByTestId("panel-prompts")).toBeTruthy());
    expect(screen.getByTestId("pipeline-active-panel").getAttribute("data-active")).toBe("prompts");
  });

  it("opens the distill panel when ?stage=distill", async () => {
    mockSearchParamsGet.mockImplementation((k) => (k === "stage" ? "distill" : null));
    render(<HomePage />);
    await waitFor(() => expect(screen.getByTestId("panel-distill")).toBeTruthy());
  });

  it("propagates the checkCompleted=false warning to DistillStagePanel", async () => {
    mockSearchParamsGet.mockImplementation((k) => (k === "stage" ? "distill" : null));
    render(<HomePage />);
    await waitFor(() => expect(screen.getByTestId("panel-distill")).toBeTruthy());
    expect(screen.getByTestId("panel-distill").getAttribute("data-check")).toBe("false");
  });
});
