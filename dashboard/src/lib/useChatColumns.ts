import { useCallback, useState } from "react";

import { applyChatEvent, finalizeColumnDefensively, type ColumnUiState } from "@/components/ChatColumn";
import {
  JobActiveError,
  streamColumnMessage,
  streamMessage,
  type ChatColumnState,
  type ChatEvent,
} from "@/lib/chat";

type UseChatColumnsOptions = {
  onJobBlocked?: () => void;
  onSuccess?: () => void;
};

export type UseChatColumnsResult = {
  columns: ColumnUiState[];
  setColumnsFromSession: (cols: ChatColumnState[]) => void;
  globalSending: boolean;
  sendGlobal: (sessionId: string, prompt: string) => Promise<void>;
  sendColumn: (sessionId: string, styleId: string, prompt: string) => Promise<void>;
};

export function useChatColumns(options: UseChatColumnsOptions = {}): UseChatColumnsResult {
  const { onJobBlocked, onSuccess } = options;
  const [columns, setColumns] = useState<ColumnUiState[]>([]);
  const [globalSending, setGlobalSending] = useState(false);

  const setColumnsFromSession = useCallback((cols: ChatColumnState[]) => {
    setColumns(
      cols.map((c) => ({
        ...c,
        messages: c.messages ?? [],
      })),
    );
  }, []);

  const handleEvent = useCallback((event: ChatEvent) => {
    setColumns((prev) => applyChatEvent(prev, event));
  }, []);

  const handleStreamError = useCallback(
    (err: unknown) => {
      if (err instanceof JobActiveError) {
        onJobBlocked?.();
      }
      throw err;
    },
    [onJobBlocked],
  );

  const sendGlobal = useCallback(
    async (sessionId: string, prompt: string) => {
      setGlobalSending(true);
      setColumns((prev) =>
        prev.map((c) => ({
          ...c,
          isStreaming: true,
          streamingText: "",
          toolCalls: [],
          messages: [...c.messages, { role: "user", content: prompt }],
        })),
      );
      try {
        await streamMessage(sessionId, prompt, handleEvent);
        onSuccess?.();
      } catch (err) {
        handleStreamError(err);
      } finally {
        setGlobalSending(false);
        setColumns((prev) => prev.map((c) => finalizeColumnDefensively(c)));
      }
    },
    [handleEvent, handleStreamError, onSuccess],
  );

  const sendColumn = useCallback(
    async (sessionId: string, styleId: string, prompt: string) => {
      setColumns((prev) =>
        prev.map((c) =>
          c.style_id === styleId
            ? {
                ...c,
                isStreaming: true,
                streamingText: "",
                toolCalls: [],
                messages: [...c.messages, { role: "user", content: prompt }],
              }
            : c,
        ),
      );
      try {
        await streamColumnMessage(sessionId, styleId, prompt, handleEvent);
        onSuccess?.();
      } catch (err) {
        handleStreamError(err);
      } finally {
        setColumns((prev) =>
          prev.map((c) => (c.style_id === styleId ? finalizeColumnDefensively(c) : c)),
        );
      }
    },
    [handleEvent, handleStreamError, onSuccess],
  );

  return {
    columns,
    setColumnsFromSession,
    globalSending,
    sendGlobal,
    sendColumn,
  };
}

export { JobActiveError };
