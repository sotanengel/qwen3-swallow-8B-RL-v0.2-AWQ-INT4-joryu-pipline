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
    return <p className="muted">棄却サンプルなし</p>;
  }
  return (
    <details
      className="rejected-table-wrap"
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary className="rejected-table-title">
        棄却サンプル {samples.length} 件 (固定 seed 抽出 / クリックで展開)
      </summary>
      <table className="rejected-table">
        <thead>
          <tr>
            <th>#</th>
            <th>prompt</th>
            <th style={{ width: 100 }}>mode</th>
            <th style={{ width: 100 }}>style</th>
            <th>rejected_by</th>
            <th className="text-right" style={{ width: 70 }}>
              score
            </th>
          </tr>
        </thead>
        <tbody>
          {samples.map((s, i) => (
            <tr key={s.record_hash ?? i}>
              <td className="muted">{i + 1}</td>
              <td>{s.prompt}</td>
              <td>{s.mode ?? "-"}</td>
              <td>{s.style_id ?? "-"}</td>
              <td className="rejected-by">{s.rejected_by.join(", ")}</td>
              <td className="text-right">
                {s.final_score != null ? s.final_score.toFixed(2) : "-"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
