// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DistilledRecord } from "@/lib/jsonl";

const mockReplace = vi.hoisted(() => vi.fn());
const mockPush = vi.hoisted(() => vi.fn());
const mockSearchParamsGet = vi.hoisted(() =>
  vi.fn((_key: string): string | null => null),
);
const mockSearchParamsToString = vi.hoisted(() => vi.fn(() => ""));
const downloadJsonlMock = vi.hoisted(() => vi.fn());

const distilledRows = vi.hoisted((): DistilledRecord[] => [
  { prompt: "distilled-kept", answer: "a1", category: "国語" },
  { prompt: "distilled-extracted", answer: "a2", category: "数学" },
]);
const curatedRows = vi.hoisted((): DistilledRecord[] => [
  { prompt: "distilled-extracted", answer: "a2", category: "数学" },
]);

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
  useSearchParams: () => ({
    get: mockSearchParamsGet,
    toString: mockSearchParamsToString,
  }),
}));

vi.mock("@/lib/useDistillJobFastPoll", () => ({
  useDistillJobFastPoll: () => false,
}));

let pollCall = 0;
vi.mock("@/lib/useIntervalPoll", () => ({
  useIntervalPoll: (load: () => Promise<DistilledRecord[]>) => {
    const hookIndex = pollCall % 2;
    pollCall += 1;
    void load();
    return hookIndex === 0 ? distilledRows : curatedRows;
  },
}));

vi.mock("@/lib/jsonl", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/jsonl")>();
  return {
    ...actual,
    loadJsonl: vi.fn(async () => distilledRows),
    loadCuratedJsonl: vi.fn(async () => curatedRows),
  };
});

vi.mock("@/lib/download", () => ({
  downloadJsonl: downloadJsonlMock,
}));

vi.mock("@/components/OutputsHierarchyView", () => ({
  OutputsHierarchyView: ({ records }: { records: DistilledRecord[] }) => (
    <div data-testid="hierarchy">{records.map((r) => r.prompt).join(",")}</div>
  ),
  HIERARCHY_PAGE_SIZE: 25,
}));

import OutputsPage from "./page";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  pollCall = 0;
  mockSearchParamsGet.mockReturnValue(null);
  mockSearchParamsToString.mockReturnValue("");
});

describe("OutputsPage dataset split", () => {
  it("shows distilled records excluding extracted ones by default", async () => {
    render(<OutputsPage />);
    await waitFor(() => expect(screen.getByTestId("hierarchy")).toBeTruthy());
    expect(screen.getByTestId("hierarchy").textContent).toBe("distilled-kept");
    expect(screen.getByText(/抽出済み 1 件を除外/)).toBeTruthy();
  });

  it("switches to extracted dataset tab", async () => {
    mockSearchParamsGet.mockImplementation((key) =>
      key === "dataset" ? "extracted" : null,
    );
    render(<OutputsPage />);
    await waitFor(() =>
      expect(screen.getByTestId("hierarchy").textContent).toBe("distilled-extracted"),
    );
    expect(screen.getByTestId("outputs-dataset-extracted").getAttribute("aria-selected")).toBe(
      "true",
    );
  });

  it("exports current dataset as jsonl", async () => {
    render(<OutputsPage />);
    await waitFor(() => expect(screen.getByTestId("outputs-export-jsonl")).toBeTruthy());
    fireEvent.click(screen.getByTestId("outputs-export-jsonl"));
    expect(downloadJsonlMock).toHaveBeenCalledWith(
      expect.arrayContaining([expect.objectContaining({ prompt: "distilled-kept" })]),
      "responses.distilled.jsonl",
    );
  });

  it("hides delete-all on extracted view", async () => {
    mockSearchParamsGet.mockImplementation((key) =>
      key === "dataset" ? "extracted" : null,
    );
    render(<OutputsPage />);
    await waitFor(() => expect(screen.getByTestId("outputs-dataset-extracted")).toBeTruthy());
    expect(screen.queryByRole("button", { name: "全削除" })).toBeNull();
  });
});
