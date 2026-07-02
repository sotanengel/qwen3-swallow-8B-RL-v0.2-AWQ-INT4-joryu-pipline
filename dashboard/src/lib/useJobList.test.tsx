// @vitest-environment jsdom

import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useJobList } from "./useJobList";

type Row = { id: string; status: "queued" | "running" | "succeeded" };

function Probe({
  loader,
}: {
  loader: () => Promise<Row[]>;
}) {
  const [rows, , error] = useJobList<Row>(
    loader,
    (r) => r.status === "queued" || r.status === "running",
    { intervalMs: 100 },
  );
  return (
    <div>
      <div data-testid="count">{rows.length}</div>
      <div data-testid="error">{error ?? ""}</div>
    </div>
  );
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("useJobList", () => {
  it("loads once on mount", async () => {
    const loader = vi.fn(async (): Promise<Row[]> => [
      { id: "a", status: "succeeded" },
    ]);
    const utils = render(<Probe loader={loader} />);
    await flush();
    expect(utils.getByTestId("count").textContent).toBe("1");
    expect(loader).toHaveBeenCalledTimes(1);
  });

  it("polls while an active job exists", async () => {
    const loader = vi.fn(async (): Promise<Row[]> => [
      { id: "a", status: "running" },
    ]);
    render(<Probe loader={loader} />);
    await flush();
    expect(loader).toHaveBeenCalledTimes(1);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    await flush();
    expect(loader).toHaveBeenCalledTimes(2);
  });

  it("stops polling when no jobs are active", async () => {
    const loader = vi.fn(async (): Promise<Row[]> => [
      { id: "a", status: "succeeded" },
    ]);
    render(<Probe loader={loader} />);
    await flush();
    const first = loader.mock.calls.length;
    await act(async () => {
      vi.advanceTimersByTime(500);
    });
    expect(loader.mock.calls.length).toBe(first);
  });

  it("captures loader errors", async () => {
    const loader = vi.fn(async (): Promise<Row[]> => {
      throw new Error("boom");
    });
    const utils = render(<Probe loader={loader} />);
    await flush();
    expect(utils.getByTestId("error").textContent).toBe("boom");
  });
});
