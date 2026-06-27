// @vitest-environment jsdom

import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { JobActiveError } from "@/lib/api/errors";
import { useChatColumns } from "@/lib/useChatColumns";

const mockStreamMessage = vi.hoisted(() => vi.fn());
const mockStreamColumnMessage = vi.hoisted(() => vi.fn());

vi.mock("@/lib/chat", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/chat")>();
  return {
    ...actual,
    streamMessage: (...args: unknown[]) => mockStreamMessage(...args),
    streamColumnMessage: (...args: unknown[]) => mockStreamColumnMessage(...args),
  };
});

describe("useChatColumns", () => {
  it("applies column_start before tokens via stream", async () => {
    mockStreamMessage.mockImplementation(
      async (
        _sid: string,
        _prompt: string,
        onEvent: (e: { type: string; column?: string; delta?: string }) => void,
      ) => {
        onEvent({ type: "column_start", column: "prose" });
        onEvent({ type: "token", column: "prose", delta: "hi" });
        onEvent({ type: "column_done", column: "prose" });
      },
    );
    const { result } = renderHook(() => useChatColumns());

    act(() => {
      result.current.setColumnsFromSession([
        { style_id: "prose", label: "散文", messages: [], turn_index: 0 },
        { style_id: "qa_short", label: "短答", messages: [], turn_index: 0 },
      ]);
    });

    await act(async () => {
      await result.current.sendGlobal("sess-1", "hello");
    });

    expect(result.current.columns[0]?.isStreaming).toBe(false);
    expect(result.current.columns[1]?.isStreaming).toBe(false);
    expect(result.current.columns[1]?.turn_index).toBe(1);
  });

  it("applies optimistic update and SSE events on sendGlobal", async () => {
    mockStreamMessage.mockImplementation(
      async (_sid: string, _prompt: string, onEvent: (e: { type: string; column?: string; delta?: string }) => void) => {
        onEvent({ type: "token", column: "prose", delta: "hi" });
        onEvent({ type: "column_done", column: "prose" });
      },
    );
    const onSuccess = vi.fn();
    const { result } = renderHook(() => useChatColumns({ onSuccess }));

    act(() => {
      result.current.setColumnsFromSession([
        { style_id: "prose", label: "散文", messages: [], turn_index: 0 },
      ]);
    });

    await act(async () => {
      await result.current.sendGlobal("sess-1", "hello");
    });

    expect(result.current.columns[0]?.messages).toEqual([
      { role: "user", content: "hello" },
      { role: "assistant", content: "hi" },
    ]);
    expect(onSuccess).toHaveBeenCalled();
  });

  it("calls onJobBlocked when stream returns 409", async () => {
    mockStreamMessage.mockRejectedValue(new JobActiveError());
    const onJobBlocked = vi.fn();
    const { result } = renderHook(() => useChatColumns({ onJobBlocked }));

    act(() => {
      result.current.setColumnsFromSession([
        { style_id: "prose", label: "散文", messages: [], turn_index: 0 },
      ]);
    });

    await act(async () => {
      await expect(result.current.sendGlobal("sess-1", "hello")).rejects.toThrow(
        JobActiveError,
      );
    });

    expect(onJobBlocked).toHaveBeenCalled();
  });

  it("finalizes column when stream ends without column_done", async () => {
    mockStreamMessage.mockImplementation(
      async (
        _sid: string,
        _prompt: string,
        onEvent: (e: { type: string; column?: string; delta?: string }) => void,
      ) => {
        onEvent({ type: "token", column: "prose", delta: "partial" });
      },
    );
    const { result } = renderHook(() => useChatColumns());

    act(() => {
      result.current.setColumnsFromSession([
        { style_id: "prose", label: "散文", messages: [], turn_index: 0 },
      ]);
    });

    await act(async () => {
      await result.current.sendGlobal("sess-1", "hello");
    });

    expect(result.current.columns[0]?.isStreaming).toBe(false);
    expect(result.current.columns[0]?.messages.at(-1)?.content).toBe("partial");
  });
});
