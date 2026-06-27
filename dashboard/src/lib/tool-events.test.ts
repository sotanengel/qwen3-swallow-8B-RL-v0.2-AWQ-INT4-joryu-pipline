import { describe, expect, it } from "vitest";

import type { DistilledRecord } from "./jsonl";
import { extractToolEvents } from "./tool-events";

describe("extractToolEvents", () => {
  it("builds timeline from turns with tool error content", () => {
    const record = {
      prompt: "天気",
      answer: "",
      turns: [
        {
          role: "assistant",
          tool_calls: [{ name: "weather", arguments: { location: "東京" } }],
        },
        { role: "tool", name: "weather", content: "error: weather upstream timeout" },
      ],
    } satisfies DistilledRecord;
    const events = extractToolEvents(record);
    expect(events).toHaveLength(2);
    expect(events[1]).toMatchObject({
      kind: "error",
      message: "weather upstream timeout",
    });
  });
});
