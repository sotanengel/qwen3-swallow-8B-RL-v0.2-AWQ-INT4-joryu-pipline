/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { ToolEventTimeline } from "@/components/ToolEventTimeline";
import type { ToolTimelineEvent } from "@/lib/tool-events";

describe("ToolEventTimeline", () => {
  it("renders tool call, result, and error events", () => {
    const events: ToolTimelineEvent[] = [
      { kind: "call", id: "weather-0", name: "weather", arguments: { location: "東京" } },
      {
        kind: "error",
        id: "weather-0",
        name: "weather",
        message: "weather upstream timeout",
      },
    ];
    render(<ToolEventTimeline events={events} />);
    expect(screen.getByText(/tool_call: weather/)).toBeTruthy();
    expect(screen.getByText(/tool_error: weather/)).toBeTruthy();
    expect(screen.getByText("weather upstream timeout")).toBeTruthy();
  });

  it("shows running label for pending tool call", () => {
    const events: ToolTimelineEvent[] = [
      { kind: "call", id: "weather-0", name: "weather", arguments: { location: "東京" } },
    ];
    render(<ToolEventTimeline events={events} />);
    expect(screen.getByText(/実行中/)).toBeTruthy();
  });
});
