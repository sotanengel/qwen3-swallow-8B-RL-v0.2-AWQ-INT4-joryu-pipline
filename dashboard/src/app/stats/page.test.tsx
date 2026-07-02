// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import StatsPage from "./page";

const mockPush = vi.hoisted(() => vi.fn());
const mockSearchParamsGet = vi.hoisted(() =>
  vi.fn((_key: string): string | null => null),
);

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => ({ get: mockSearchParamsGet }),
}));

vi.mock("@/components/stats/OverviewPanel", () => ({
  OverviewPanel: () => <div data-testid="overview">OVERVIEW</div>,
}));
vi.mock("@/components/stats/DistributionsPanel", () => ({
  DistributionsPanel: () => <div data-testid="distributions">DIST</div>,
}));
vi.mock("@/components/stats/CurationQualityPanel", () => ({
  CurationQualityPanel: () => <div data-testid="curation">CURATION</div>,
}));
vi.mock("@/components/stats/ScreeningPanel", () => ({
  ScreeningPanel: () => <div data-testid="screening">SCREENING</div>,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  mockSearchParamsGet.mockReturnValue(null);
});

describe("StatsPage", () => {
  it("defaults to the overview tab", async () => {
    render(<StatsPage />);
    await waitFor(() => expect(screen.getByTestId("overview")).toBeTruthy());
    expect(screen.queryByTestId("distributions")).toBeNull();
    expect(screen.getByTestId("stats-panel").getAttribute("data-active")).toBe("overview");
  });

  it("selects distributions tab from ?tab=distributions", async () => {
    mockSearchParamsGet.mockImplementation((k) => (k === "tab" ? "distributions" : null));
    render(<StatsPage />);
    await waitFor(() => expect(screen.getByTestId("distributions")).toBeTruthy());
    expect(screen.queryByTestId("overview")).toBeNull();
  });

  it("selects curation tab from ?tab=curation", async () => {
    mockSearchParamsGet.mockImplementation((k) => (k === "tab" ? "curation" : null));
    render(<StatsPage />);
    await waitFor(() => expect(screen.getByTestId("curation")).toBeTruthy());
  });

  it("selects screening tab from ?tab=screening", async () => {
    mockSearchParamsGet.mockImplementation((k) => (k === "tab" ? "screening" : null));
    render(<StatsPage />);
    await waitFor(() => expect(screen.getByTestId("screening")).toBeTruthy());
  });

  it("navigates when clicking a tab", async () => {
    render(<StatsPage />);
    await waitFor(() => expect(screen.getByTestId("stats-tab-distributions")).toBeTruthy());
    fireEvent.click(screen.getByTestId("stats-tab-distributions"));
    expect(mockPush).toHaveBeenCalledWith("/stats?tab=distributions");
  });

  it("marks the active tab with aria-selected", async () => {
    mockSearchParamsGet.mockImplementation((k) => (k === "tab" ? "curation" : null));
    render(<StatsPage />);
    await waitFor(() => expect(screen.getByTestId("stats-tab-curation")).toBeTruthy());
    expect(screen.getByTestId("stats-tab-curation").getAttribute("aria-selected")).toBe("true");
    expect(screen.getByTestId("stats-tab-overview").getAttribute("aria-selected")).toBe("false");
  });
});
