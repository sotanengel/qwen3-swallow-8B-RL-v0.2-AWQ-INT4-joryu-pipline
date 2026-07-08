// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest";

import type { DistilledRecord } from "./jsonl";

const createObjectURL = vi.hoisted(() => vi.fn(() => "blob:mock"));
const revokeObjectURL = vi.hoisted(() => vi.fn());
const clickMock = vi.hoisted(() => vi.fn());

afterEach(() => {
  vi.clearAllMocks();
});

describe("downloadJsonl", () => {
  it("creates a download link with jsonl content", async () => {
    const originalCreateObjectURL = URL.createObjectURL;
    const originalRevokeObjectURL = URL.revokeObjectURL;
    URL.createObjectURL = createObjectURL;
    URL.revokeObjectURL = revokeObjectURL;

    const anchor = { href: "", download: "", click: clickMock };
    const createElement = vi.spyOn(document, "createElement").mockReturnValue(
      anchor as unknown as HTMLAnchorElement,
    );

    try {
      const { downloadJsonl } = await import("./download");
      const records: DistilledRecord[] = [{ prompt: "p", answer: "a" }];
      downloadJsonl(records, "responses.distilled.jsonl");

      expect(createObjectURL).toHaveBeenCalled();
      const blob = createObjectURL.mock.calls[0][0] as Blob;
      expect(blob.type).toBe("application/x-ndjson");
      expect(anchor.download).toBe("responses.distilled.jsonl");
      expect(clickMock).toHaveBeenCalled();
      expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock");
    } finally {
      URL.createObjectURL = originalCreateObjectURL;
      URL.revokeObjectURL = originalRevokeObjectURL;
      createElement.mockRestore();
    }
  });
});
