"use client";

import type { ToolTimelineEvent } from "@/lib/tool-events";
import { toolEventPending } from "@/lib/tool-events";

type ToolEventTimelineProps = {
  events: ToolTimelineEvent[];
};

function eventLabel(event: ToolTimelineEvent): string {
  switch (event.kind) {
    case "call":
      return `tool_call: ${event.name}`;
    case "result":
      return `tool_result: ${event.name}`;
    case "error":
      return `tool_error: ${event.name}`;
  }
}

export function ToolEventTimeline({ events }: ToolEventTimelineProps) {
  if (events.length === 0) return null;

  return (
    <section
      aria-live="polite"
      aria-label="ツール実行タイムライン"
      className="tool-event-timeline"
      style={{ marginBottom: "1.5rem" }}
    >
      <h2 style={{ fontSize: "1rem", marginBottom: "0.75rem" }}>ツール実行</h2>
      <ol style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: "0.5rem" }}>
        {events.map((event) => {
          const pending = toolEventPending(event, events);
          const isError = event.kind === "error";
          return (
            <li key={`${event.kind}-${event.id}`}>
              <details
                open={isError || pending}
                style={{
                  border: `1px solid ${isError ? "#c62828" : "var(--border)"}`,
                  borderRadius: "6px",
                  padding: "0.5rem 0.75rem",
                  background: isError ? "rgba(198, 40, 40, 0.08)" : "transparent",
                }}
              >
                <summary style={{ cursor: "pointer" }}>
                  {eventLabel(event)}
                  {pending ? " (実行中…)" : null}
                  {isError ? " (失敗)" : null}
                </summary>
                {event.kind === "call" ? (
                  <pre style={{ overflow: "auto", margin: "0.5rem 0 0", fontSize: "0.8rem" }}>
                    {JSON.stringify(event.arguments, null, 2)}
                  </pre>
                ) : null}
                {event.kind === "result" ? (
                  <pre style={{ overflow: "auto", margin: "0.5rem 0 0", fontSize: "0.8rem" }}>
                    {event.content}
                  </pre>
                ) : null}
                {event.kind === "error" ? (
                  <p style={{ margin: "0.5rem 0 0", color: "#c62828", fontSize: "0.85rem" }}>
                    {event.message}
                  </p>
                ) : null}
              </details>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
