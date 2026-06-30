"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export function HistogramChart({
  data,
}: {
  data: Array<{ name: string; count: number }>;
}) {
  if (data.length === 0) {
    return <p className="muted">データなし</p>;
  }

  return (
    <div className="chart-container">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid stroke="#30363d" strokeDasharray="3 3" />
          <XAxis
            dataKey="name"
            stroke="#8b949e"
            interval={0}
            angle={-30}
            textAnchor="end"
            height={70}
          />
          <YAxis stroke="#8b949e" />
          <Tooltip
            contentStyle={{ background: "#161b22", border: "1px solid #30363d", color: "#e6edf3" }}
          />
          <Bar dataKey="count" fill="#58a6ff" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
