"use client";

import dynamic from "next/dynamic";

import { HeatmapTable } from "@/components/HeatmapTable";
import { RejectedSamplesTable } from "@/components/RejectedSamplesTable";
import {
  EMPTY_CURATION,
  curationDataChanged,
  loadCuration,
} from "@/lib/curation";
import { useIntervalPoll } from "@/lib/useIntervalPoll";
import { useCurateJobFastPoll } from "@/lib/useJobFastPoll";

const HistogramChart = dynamic(
  () =>
    import("@/components/HistogramChart").then((mod) => mod.HistogramChart),
  {
    ssr: false,
    loading: () => <div className="chart-loading">グラフを読み込み中…</div>,
  },
);

const RUBRIC_ORDER: Array<{ key: string; label: string }> = [
  { key: "accuracy", label: "正確性" },
  { key: "completeness", label: "完全性" },
  { key: "fluency", label: "流暢性" },
  { key: "instruction_following", label: "指示追従" },
  { key: "safety", label: "安全性" },
];

export function CurationQualityPanel() {
  const fastPoll = useCurateJobFastPoll();
  const cur = useIntervalPoll(loadCuration, EMPTY_CURATION, {
    shouldUpdate: curationDataChanged,
    intervalMs: 3000,
    fastPoll,
  });

  const scoreBins = cur.score_bins.map((b) => ({
    name: `${b.lo}–${b.hi ?? "∞"}`,
    count: b.count,
  }));
  const reasonBars = cur.rejected_reasons_top.map(([reason, count]) => ({
    name: reason,
    count,
  }));
  const rubricBars = RUBRIC_ORDER.map(({ key, label }) => ({
    name: label,
    count: Number(
      (cur.rubric_avg as Record<string, number | undefined>)[key] ?? 0,
    ),
  }));
  const styleBars = Object.entries(cur.by_style)
    .map(([sid, v]) => ({
      name: sid,
      count: Number((v.keep_rate * 100).toFixed(1)),
    }))
    .sort((a, b) => b.count - a.count);

  const modeEntries = Object.entries(cur.by_mode).sort(([a], [b]) =>
    a.localeCompare(b),
  );

  return (
    <>
      <section className="section">
        <h2>採否サマリ</h2>
        <p>
          総数: <strong>{cur.total}</strong> / 採用: <strong>{cur.accepted}</strong>{" "}
          / 棄却: <strong>{cur.rejected}</strong> / 採用率:{" "}
          <strong>{(cur.keep_rate * 100).toFixed(1)}%</strong>
        </p>
      </section>

      <section className="section">
        <h2>合成スコア分布 (%)</h2>
        <HistogramChart data={scoreBins} />
      </section>

      <section className="section">
        <h2>mode 別 スコア分布</h2>
        {modeEntries.length === 0 ? (
          <p className="muted">データなし</p>
        ) : (
          <div className="curation-charts">
            {modeEntries.map(([mode, v]) => (
              <div key={mode} className="curation-chart-card">
                <h3>
                  {mode} (n={v.total}, 採用率 {(v.keep_rate * 100).toFixed(1)}%)
                </h3>
                <HistogramChart
                  data={v.score_bins.map((b) => ({
                    name: `${b.lo}–${b.hi ?? "∞"}`,
                    count: b.count,
                  }))}
                />
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="section">
        <h2>棄却理由 Top-N</h2>
        <HistogramChart data={reasonBars} />
      </section>

      <section className="section">
        <h2>LLM-RUBRIC 5 観点 平均 (1〜5)</h2>
        {cur.rubric_count > 0 ? (
          <HistogramChart data={rubricBars} />
        ) : (
          <p className="muted">
            LLM judge が走っていません (--skip-llm モード)。
          </p>
        )}
      </section>

      <section className="section">
        <h2>style 別採用率 (%)</h2>
        <HistogramChart data={styleBars} />
      </section>

      <section className="section">
        <h2>sampling × style 採用率ヒートマップ</h2>
        <HeatmapTable cells={cur.by_sampling_style} />
      </section>

      <section className="section">
        <h2>棄却サンプル</h2>
        <RejectedSamplesTable samples={cur.rejected_samples} />
      </section>
    </>
  );
}
