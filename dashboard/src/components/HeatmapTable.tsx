"use client";

import type { CurationSamplingStyleCell } from "@/lib/curation";

/**
 * sampling × style の 2 軸ヒートマップ。
 * keep_rate (0-1) を背景色の濃さに、count を tooltip 的に文字で表示。
 *
 * recharts に綺麗な heatmap が無いので CSS Grid で実装 (depencencies を増やさない方針)。
 */
export function HeatmapTable({ cells }: { cells: CurationSamplingStyleCell[] }) {
  if (cells.length === 0) {
    return <p style={{ color: "var(--muted)" }}>データなし</p>;
  }

  const samplings = Array.from(new Set(cells.map((c) => c.sampling))).sort();
  const styles = Array.from(new Set(cells.map((c) => c.style_id))).sort();
  const cellMap = new Map<string, CurationSamplingStyleCell>();
  for (const c of cells) {
    cellMap.set(`${c.sampling}__${c.style_id}`, c);
  }

  const colorFor = (rate: number): string => {
    // GitHub-ish green scale。0 → 透明、1 → 濃い緑。
    const intensity = Math.round(rate * 100);
    return `rgba(63, 185, 80, ${0.15 + (intensity / 100) * 0.85})`;
  };

  const cellSize = 64;
  const labelWidth = 110;

  return (
    <div style={{ overflowX: "auto" }}>
      <table
        style={{
          borderCollapse: "collapse",
          fontSize: "0.85rem",
        }}
      >
        <thead>
          <tr>
            <th style={{ width: labelWidth, textAlign: "left", color: "var(--muted)" }}>
              sampling \ style
            </th>
            {styles.map((sid) => (
              <th
                key={sid}
                style={{
                  padding: "0.25rem 0.5rem",
                  color: "var(--muted)",
                  textAlign: "center",
                  minWidth: cellSize,
                }}
              >
                {sid}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {samplings.map((samp) => (
            <tr key={samp}>
              <td
                style={{
                  padding: "0.25rem 0.5rem",
                  color: "var(--muted)",
                  whiteSpace: "nowrap",
                }}
              >
                {samp}
              </td>
              {styles.map((sid) => {
                const cell = cellMap.get(`${samp}__${sid}`);
                if (!cell) {
                  return (
                    <td
                      key={sid}
                      style={{
                        background: "#0d1117",
                        border: "1px solid #30363d",
                        textAlign: "center",
                        color: "#484f58",
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
                    style={{
                      background: colorFor(cell.keep_rate),
                      border: "1px solid #30363d",
                      textAlign: "center",
                      height: cellSize,
                      minWidth: cellSize,
                    }}
                  >
                    <div style={{ fontWeight: 600 }}>{pct}%</div>
                    <div style={{ fontSize: "0.7rem", color: "#c9d1d9" }}>
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
