"use client";

import { useState } from "react";

import type { CurationRejectedSample } from "@/lib/curation";

export function RejectedSamplesTable({
  samples,
}: {
  samples: CurationRejectedSample[];
}) {
  const [open, setOpen] = useState(false);
  if (samples.length === 0) {
    return <p style={{ color: "var(--muted)" }}>棄却サンプルなし</p>;
  }
  return (
    <details
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
      style={{ background: "#0d1117", borderRadius: 6, padding: "0.5rem 0.75rem" }}
    >
      <summary
        style={{
          cursor: "pointer",
          color: "var(--muted)",
          marginBottom: open ? "0.5rem" : 0,
        }}
      >
        棄却サンプル {samples.length} 件 (固定 seed 抽出 / クリックで展開)
      </summary>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
        <thead>
          <tr style={{ color: "var(--muted)" }}>
            <th style={{ textAlign: "left", padding: "0.25rem 0.5rem" }}>#</th>
            <th style={{ textAlign: "left", padding: "0.25rem 0.5rem" }}>prompt</th>
            <th style={{ textAlign: "left", padding: "0.25rem 0.5rem", width: 100 }}>
              mode
            </th>
            <th style={{ textAlign: "left", padding: "0.25rem 0.5rem", width: 100 }}>
              style
            </th>
            <th style={{ textAlign: "left", padding: "0.25rem 0.5rem" }}>rejected_by</th>
            <th
              style={{
                textAlign: "right",
                padding: "0.25rem 0.5rem",
                width: 70,
              }}
            >
              score
            </th>
          </tr>
        </thead>
        <tbody>
          {samples.map((s, i) => (
            <tr
              key={s.record_hash ?? i}
              style={{ borderTop: "1px solid #30363d" }}
            >
              <td style={{ padding: "0.25rem 0.5rem", color: "var(--muted)" }}>
                {i + 1}
              </td>
              <td style={{ padding: "0.25rem 0.5rem" }}>{s.prompt}</td>
              <td style={{ padding: "0.25rem 0.5rem" }}>{s.mode ?? "-"}</td>
              <td style={{ padding: "0.25rem 0.5rem" }}>{s.style_id ?? "-"}</td>
              <td style={{ padding: "0.25rem 0.5rem", color: "#ff7b72" }}>
                {s.rejected_by.join(", ")}
              </td>
              <td style={{ padding: "0.25rem 0.5rem", textAlign: "right" }}>
                {s.final_score != null ? s.final_score.toFixed(2) : "-"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
