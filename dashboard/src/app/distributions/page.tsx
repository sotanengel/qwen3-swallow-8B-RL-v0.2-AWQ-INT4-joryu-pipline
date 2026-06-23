"use client";

import dynamic from "next/dynamic";
import { useState } from "react";

import { EMPTY_STATS, loadStats, sortByCount, statsDataChanged } from "@/lib/stats";
import { useDistillJobFastPoll } from "@/lib/useDistillJobFastPoll";
import { useIntervalPoll } from "@/lib/useIntervalPoll";

const HistogramChart = dynamic(
  () =>
    import("@/components/HistogramChart").then((mod) => mod.HistogramChart),
  {
    ssr: false,
    loading: () => (
      <div style={{ width: "100%", height: 280, color: "var(--muted)" }}>
        グラフを読み込み中…
      </div>
    ),
  },
);

export default function DistributionsPage() {
  const fastPoll = useDistillJobFastPoll();
  const [loaded, setLoaded] = useState(false);
  const stats = useIntervalPoll(
    async () => {
      const data = await loadStats();
      setLoaded(true);
      return data;
    },
    EMPTY_STATS,
    {
      shouldUpdate: statsDataChanged,
      intervalMs: fastPoll ? 1000 : 3000,
    },
  );

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
      {loaded && stats.total === 0 && (
        <p style={{ color: "var(--muted)", marginBottom: "1rem" }}>
          stats.json が未生成または空です。{" "}
          <code>uv run joryu-stats</code> または{" "}
          <code>uv run joryu-up --refresh-stats</code> を実行してください。
        </p>
      )}

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
