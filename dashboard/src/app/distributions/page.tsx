"use client";

import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { EMPTY_STATS, JoryuStats, loadStats, sortByCount } from "@/lib/stats";

function HistogramChart({
  data,
}: {
  data: Array<{ name: string; count: number }>;
}) {
  return (
    <div style={{ width: "100%", height: 280 }}>
      <ResponsiveContainer>
        <BarChart data={data}>
          <CartesianGrid stroke="#30363d" strokeDasharray="3 3" />
          <XAxis dataKey="name" stroke="#8b949e" interval={0} angle={-30} textAnchor="end" height={70} />
          <YAxis stroke="#8b949e" />
          <Tooltip contentStyle={{ background: "#161b22", border: "1px solid #30363d" }} />
          <Bar dataKey="count" fill="#58a6ff" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function DistributionsPage() {
  const [stats, setStats] = useState<JoryuStats>(EMPTY_STATS);
  useEffect(() => {
    loadStats().then(setStats);
  }, []);

  const ansBins = stats.answer_length.bins.map((b) => ({
    name: `${b.lo}–${b.hi ?? "∞"}`,
    count: b.count,
  }));
  const thinkBins = stats.thinking_length.bins.map((b) => ({
    name: `${b.lo}–${b.hi ?? "∞"}`,
    count: b.count,
  }));
  const topCats = sortByCount(stats.categories, 15).map((r) => ({
    name: r.key,
    count: r.count,
  }));
  const tempBins = Object.entries(stats.sampling.temperature)
    .map(([k, v]) => ({ name: k, count: v }))
    .sort((a, b) => parseFloat(a.name) - parseFloat(b.name));
  const topPBins = Object.entries(stats.sampling.top_p)
    .map(([k, v]) => ({ name: k, count: v }))
    .sort((a, b) => parseFloat(a.name) - parseFloat(b.name));
  const timeline = Object.entries(stats.timeline_daily)
    .map(([k, v]) => ({ name: k, count: v }))
    .sort((a, b) => (a.name < b.name ? -1 : 1));

  return (
    <>
      <section className="section">
        <h2>回答長 (文字数) ヒストグラム</h2>
        <HistogramChart data={ansBins} />
      </section>

      <section className="section">
        <h2>思考 (thinking_trace) 長</h2>
        <HistogramChart data={thinkBins} />
      </section>

      <section className="section">
        <h2>カテゴリ上位 15</h2>
        <HistogramChart data={topCats} />
      </section>

      <section className="section">
        <h2>サンプリング: temperature</h2>
        <HistogramChart data={tempBins} />
      </section>

      <section className="section">
        <h2>サンプリング: top_p</h2>
        <HistogramChart data={topPBins} />
      </section>

      <section className="section">
        <h2>日別生成数</h2>
        <HistogramChart data={timeline} />
      </section>
    </>
  );
}
