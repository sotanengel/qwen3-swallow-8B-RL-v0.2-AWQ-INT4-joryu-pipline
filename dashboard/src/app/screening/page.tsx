"use client";

import { useIntervalPoll } from "@/lib/useIntervalPoll";
import {
  EMPTY_SCREENING,
  loadScreening,
  screeningDataChanged,
} from "@/lib/screening";

const HEALTH_KEYS = ["L-01", "L-02", "L-03", "L-04", "L-05"];

export default function ScreeningPage() {
  const data = useIntervalPoll(
    async () => loadScreening(),
    EMPTY_SCREENING,
    { shouldUpdate: screeningDataChanged, intervalMs: 3000 },
  );

  const labels = Object.entries(data.label_distribution ?? {});

  return (
    <div>
      <h2>健全性スクリーニング</h2>
      <p className="muted">
        `joryu-curate --screening` の集計 (`screening.json`)。総件数: {data.total}
      </p>

      <section className="card">
        <h3>ラベル分布</h3>
        {labels.length === 0 ? (
          <p className="muted">データがありません</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>ラベル</th>
                <th>件数</th>
                <th>割合</th>
              </tr>
            </thead>
            <tbody>
              {labels.map(([lbl, bucket]) => (
                <tr key={lbl}>
                  <td>{lbl}</td>
                  <td>{bucket.count}</td>
                  <td>{(bucket.rate * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h3>ルール違反率 (R-01〜R-09)</h3>
        <table className="data-table">
          <thead>
            <tr>
              <th>ルール ID</th>
              <th>違反率</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(data.rule_violation_rates ?? {}).map(([rid, rate]) => (
              <tr key={rid}>
                <td>{rid}</td>
                <td>{(rate * 100).toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h3>LLM-HEALTH 観点別平均 (1〜5)</h3>
        <table className="data-table">
          <thead>
            <tr>
              <th>観点</th>
              <th>平均</th>
            </tr>
          </thead>
          <tbody>
            {HEALTH_KEYS.map((k) => (
              <tr key={k}>
                <td>{k}</td>
                <td>{(data.llm_health_averages?.[k] ?? 0).toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">評価件数: {data.llm_health_count}</p>
      </section>
    </div>
  );
}
