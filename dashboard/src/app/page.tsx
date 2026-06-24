"use client";

import { useIntervalPoll } from "@/lib/useIntervalPoll";
import { useDistillJobFastPoll } from "@/lib/useDistillJobFastPoll";
import { EMPTY_STATS, JoryuStats, loadStats, sortByCount, statsDataChanged } from "@/lib/stats";

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="card">
      <h3>{label}</h3>
      <div className="value">{value}</div>
    </div>
  );
}

function HistogramTable({
  rows,
  keyLabel,
}: {
  rows: Array<{ key: string; count: number }>;
  keyLabel: string;
}) {
  if (rows.length === 0) return <p style={{ color: "var(--muted)" }}>データなし</p>;
  return (
    <table>
      <thead>
        <tr>
          <th>{keyLabel}</th>
          <th style={{ textAlign: "right" }}>件数</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.key}>
            <td>{r.key}</td>
            <td style={{ textAlign: "right" }}>{r.count.toLocaleString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function HomePage() {
  const fastPoll = useDistillJobFastPoll();
  const stats = useIntervalPoll(loadStats, EMPTY_STATS, {
    shouldUpdate: statsDataChanged,
    intervalMs: 3000,
    fastPoll,
  });

  const modeRows = sortByCount(stats.modes);
  const modelRows = sortByCount(stats.models);
  const topCategories = sortByCount(stats.categories, 10);

  return (
    <>
      <section className="grid">
        <StatCard label="総レコード数" value={stats.total.toLocaleString()} />
        <StatCard label="平均回答長 (文字)" value={Math.round(stats.answer_length.mean)} />
        <StatCard label="最大回答長 (文字)" value={stats.answer_length.max} />
        <StatCard
          label="thinking 行数"
          value={(stats.modes.thinking ?? 0).toLocaleString()}
        />
      </section>

      <section className="section">
        <h2>モデル別</h2>
        <HistogramTable rows={modelRows} keyLabel="model" />
      </section>

      <section className="section">
        <h2>モード別</h2>
        <HistogramTable rows={modeRows} keyLabel="mode" />
      </section>

      <section className="section">
        <h2>カテゴリ上位 10</h2>
        <HistogramTable rows={topCategories} keyLabel="category" />
      </section>

      {stats._meta?.generated_at && (
        <p style={{ color: "var(--muted)", fontSize: "0.8rem" }}>
          生成時刻: {stats._meta.generated_at} / source: {stats._meta.source_path}
        </p>
      )}
    </>
  );
}
