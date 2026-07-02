// @vitest-environment jsdom

import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useJobLogs } from "./useJobLogs";

function Probe({
  jobId,
  getLogs,
}: {
  jobId: string | null;
  getLogs: (id: string, offset: number) => Promise<{ chunk: string; offset: number }>;
}) {
  const logs = useJobLogs(jobId, getLogs, { intervalMs: 100 });
  return <div data-testid="logs">{logs}</div>;
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

async function flushMicrotasks() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("useJobLogs", () => {
  it("appends chunks and continues offset across polls", async () => {
    const calls: Array<{ id: string; offset: number }> = [];
    const getLogs = vi.fn(async (id: string, offset: number) => {
      calls.push({ id, offset });
      if (offset === 0) return { chunk: "hello", offset: 5 };
      if (offset === 5) return { chunk: " world", offset: 11 };
      return { chunk: "", offset };
    });

    const utils = render(<Probe jobId="j1" getLogs={getLogs} />);
    await flushMicrotasks();
    expect(utils.getByTestId("logs").textContent).toBe("hello");

    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    await flushMicrotasks();
    expect(utils.getByTestId("logs").textContent).toBe("hello world");
    expect(calls[1].offset).toBe(5);
  });

  it("resets when jobId changes", async () => {
    const getLogs = vi.fn(async () => ({ chunk: "A", offset: 1 }));
    const utils = render(<Probe jobId="j1" getLogs={getLogs} />);
    await flushMicrotasks();
    expect(utils.getByTestId("logs").textContent).toBe("A");

    utils.rerender(<Probe jobId="j2" getLogs={getLogs} />);
    await flushMicrotasks();
    // resetは即座に空になり、続けて j2 の初回結果 "A" が入る
    expect(utils.getByTestId("logs").textContent).toBe("A");
  });

  it("clears logs and stops polling when jobId becomes null", async () => {
    const getLogs = vi.fn(async () => ({ chunk: "X", offset: 1 }));
    const utils = render(<Probe jobId="j1" getLogs={getLogs} />);
    await flushMicrotasks();
    expect(utils.getByTestId("logs").textContent).toBe("X");

    utils.rerender(<Probe jobId={null} getLogs={getLogs} />);
    expect(utils.getByTestId("logs").textContent).toBe("");

    const callsBefore = getLogs.mock.calls.length;
    await act(async () => {
      vi.advanceTimersByTime(500);
    });
    expect(getLogs.mock.calls.length).toBe(callsBefore);
  });

  it("clears interval on unmount", async () => {
    const getLogs = vi.fn(async () => ({ chunk: "", offset: 0 }));
    const utils = render(<Probe jobId="j1" getLogs={getLogs} />);
    await flushMicrotasks();
    const callsBefore = getLogs.mock.calls.length;
    utils.unmount();
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    expect(getLogs.mock.calls.length).toBe(callsBefore);
  });
});
