"use client";

import type { CurationSamplingStyleCell } from "@/lib/curation";

/**
 * sampling × style の 2 軸ヒートマップ。
 * keep_rate (0-1) を背景色の濃さに、count を tooltip 的に文字で表示。
 */
export function HeatmapTable({ cells }: { cells: CurationSamplingStyleCell[] }) {
  if (cells.length === 0) {
    return <p className="muted">データなし</p>;
  }

  const samplings = Array.from(new Set(cells.map((c) => c.sampling))).sort();
  const styles = Array.from(new Set(cells.map((c) => c.style_id))).sort();
  const cellMap = new Map<string, CurationSamplingStyleCell>();
  for (const c of cells) {
    cellMap.set(`${c.sampling}__${c.style_id}`, c);
  }

  const colorFor = (rate: number): string => {
    const intensity = Math.round(rate * 100);
    return `rgba(63, 185, 80, ${0.15 + (intensity / 100) * 0.85})`;
  };

  const cellSize = 64;
  const labelWidth = 110;

  return (
    <div className="heatmap-wrap">
      <table className="heatmap-table">
        <thead>
          <tr>
            <th style={{ width: labelWidth }}>sampling \ style</th>
            {styles.map((sid) => (
              <th key={sid} className="heatmap-cell" style={{ minWidth: cellSize }}>
                {sid}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {samplings.map((samp) => (
            <tr key={samp}>
              <td className="muted" style={{ whiteSpace: "nowrap" }}>
                {samp}
              </td>
              {styles.map((sid) => {
                const cell = cellMap.get(`${samp}__${sid}`);
                if (!cell) {
                  return (
                    <td
                      key={sid}
                      className="heatmap-cell"
                      style={{
                        background: "var(--bg)",
                        color: "var(--muted)",
                        height: cellSize,
                        minWidth: cellSize,
                      }}
                    >
                      –
                    </td>
                  );
                }
                const pct = (cell.keep_rate * 100).toFixed(0);
                return (
                  <td
                    key={sid}
                    title={`採用 ${cell.kept} / ${cell.total} = ${pct}%`}
                    className="heatmap-cell"
                    style={{
                      background: colorFor(cell.keep_rate),
                      height: cellSize,
                      minWidth: cellSize,
                    }}
                  >
                    <div className="heatmap-cell-pct">{pct}%</div>
                    <div className="heatmap-cell-count">
                      {cell.kept}/{cell.total}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
