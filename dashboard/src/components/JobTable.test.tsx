// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { JobTable } from "./JobTable";

type Row = {
  id: string;
  status: "queued" | "running" | "succeeded" | "cancelled";
  created_at: string;
  finished_at: string | null;
};

const rows: Row[] = [
  { id: "abcdefgh-1", status: "running", created_at: "2026-01-01T00:00:00Z", finished_at: null },
  { id: "xyz-2", status: "succeeded", created_at: "2026-01-02T00:00:00Z", finished_at: "2026-01-02T00:30:00Z" },
];

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("JobTable", () => {
  it("renders empty label when there are no jobs", () => {
    render(
      <JobTable
        jobs={[]}
        selectedId={null}
        onSelect={() => {}}
        onCancel={() => {}}
        emptyLabel="からっぽ"
      />,
    );
    expect(screen.getByText("からっぽ")).toBeTruthy();
  });

  it("calls onSelect when a row is clicked", () => {
    const onSelect = vi.fn();
    render(
      <JobTable
        jobs={rows}
        selectedId={null}
        onSelect={onSelect}
        onCancel={() => {}}
      />,
    );
    const [firstRow] = screen.getAllByTestId("job-row");
    fireEvent.click(firstRow);
    expect(onSelect).toHaveBeenCalledWith("abcdefgh-1");
  });

  it("shows cancel button only for active jobs", () => {
    render(
      <JobTable
        jobs={rows}
        selectedId={null}
        onSelect={() => {}}
        onCancel={() => {}}
      />,
    );
    expect(screen.getAllByTestId("cancel-btn")).toHaveLength(1);
  });

  it("does not call onCancel when confirm is cancelled", () => {
    const onCancel = vi.fn();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(
      <JobTable
        jobs={rows}
        selectedId={null}
        onSelect={() => {}}
        onCancel={onCancel}
      />,
    );
    fireEvent.click(screen.getByTestId("cancel-btn"));
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("calls onCancel when confirm is accepted", () => {
    const onCancel = vi.fn();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(
      <JobTable
        jobs={rows}
        selectedId={null}
        onSelect={() => {}}
        onCancel={onCancel}
      />,
    );
    fireEvent.click(screen.getByTestId("cancel-btn"));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect((onCancel.mock.calls[0][0] as Row).id).toBe("abcdefgh-1");
  });

  it("stops row selection when the cancel button is clicked", () => {
    const onSelect = vi.fn();
    const onCancel = vi.fn();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(
      <JobTable
        jobs={rows}
        selectedId={null}
        onSelect={onSelect}
        onCancel={onCancel}
      />,
    );
    fireEvent.click(screen.getByTestId("cancel-btn"));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("marks the selected row with the row-selected class", () => {
    render(
      <JobTable
        jobs={rows}
        selectedId="xyz-2"
        onSelect={() => {}}
        onCancel={() => {}}
      />,
    );
    const [, secondRow] = screen.getAllByTestId("job-row");
    expect(secondRow.className).toContain("row-selected");
  });

  it("renders extra columns", () => {
    render(
      <JobTable
        jobs={rows}
        selectedId={null}
        onSelect={() => {}}
        onCancel={() => {}}
        extraColumns={[{ key: "kind", header: "種別", render: () => "distill" }]}
      />,
    );
    expect(screen.getByText("種別")).toBeTruthy();
    expect(screen.getAllByText("distill")).toHaveLength(2);
  });
});
