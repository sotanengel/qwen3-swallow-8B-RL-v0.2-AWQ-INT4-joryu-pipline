import { describe, expect, it } from "vitest";

import { parseSseBuffer, parseSseText } from "./sse-parse";

describe("parseSseBuffer", () => {
  it("parses a single complete event", () => {
    const raw = 'event: token\ndata: {"column":"prose","delta":"hi"}\n\n';
    const { events, remainder } = parseSseBuffer(raw);
    expect(events).toEqual([{ type: "token", column: "prose", delta: "hi" }]);
    expect(remainder).toBe("");
  });

  it("keeps partial block in remainder", () => {
    const raw = 'event: token\ndata: {"column":"prose","delta":"hi"}\n\nevent: done\ndata: {"session_id":"s1"';
    const { events, remainder } = parseSseBuffer(raw);
    expect(events).toHaveLength(1);
    expect(remainder).toContain("event: done");
  });

  it("parses multiple concatenated events", () => {
    const raw =
      'event: token\ndata: {"column":"a","delta":"1"}\n\n' +
      'event: column_done\ndata: {"column":"a","finish_reason":"stop","record_id":"x"}\n\n' +
      'event: done\ndata: {"session_id":"s"}\n\n';
    const events = parseSseText(raw);
    expect(events.map((e) => e.type)).toEqual(["token", "column_done", "done"]);
  });

  it("emits error event on invalid JSON", () => {
    const raw = "event: token\ndata: not-json\n\n";
    const { events } = parseSseBuffer(raw);
    expect(events[0]?.type).toBe("error");
  });
});
