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
    >
      <h2>ツール実行</h2>
      <ol className="tool-event-list">
        {events.map((event) => {
          const pending = toolEventPending(event, events);
          const isError = event.kind === "error";
          return (
            <li key={`${event.kind}-${event.id}`}>
              <details
                open={isError || pending}
                className={`tool-event-details${isError ? " tool-event-details--error" : ""}`}
              >
                <summary>
                  {eventLabel(event)}
                  {pending ? " (実行中…)" : null}
                  {isError ? " (失敗)" : null}
                </summary>
                {event.kind === "call" ? (
                  <pre className="tool-event-pre">{JSON.stringify(event.arguments, null, 2)}</pre>
                ) : null}
                {event.kind === "result" ? (
                  <pre className="tool-event-pre">{event.content}</pre>
                ) : null}
                {event.kind === "error" ? (
                  <p className="tool-event-error-msg">{event.message}</p>
                ) : null}
              </details>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
