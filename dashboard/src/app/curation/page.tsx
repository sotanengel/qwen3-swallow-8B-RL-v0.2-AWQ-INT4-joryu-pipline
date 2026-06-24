"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";

import { HeatmapTable } from "@/components/HeatmapTable";
import { RejectedSamplesTable } from "@/components/RejectedSamplesTable";
import {
  CurateJobOptions,
  CurateJobRecord,
  cancelCurateJob,
  createCurateJob,
  curateStatusLabel,
  getCurateJobLogs,
  isCurateJobActive,
  listCurateJobs,
  loadCurateJobOptions,
} from "@/lib/curate-jobs";
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
    loading: () => (
      <div style={{ width: "100%", height: 280, color: "var(--muted)" }}>
        グラフを読み込み中…
      </div>
    ),
  },
);

const RUBRIC_ORDER: Array<{ key: string; label: string }> = [
  { key: "accuracy", label: "正確性" },
  { key: "completeness", label: "完全性" },
  { key: "fluency", label: "流暢性" },
  { key: "instruction_following", label: "指示追従" },
  { key: "safety", label: "安全性" },
];

export default function CurationPage() {
  const [loaded, setLoaded] = useState(false);
  const [options, setOptions] = useState<CurateJobOptions | null>(null);
  const [jobs, setJobs] = useState<CurateJobRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [logs, setLogs] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [skipLlm, setSkipLlm] = useState(false);
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  const fastPoll = useCurateJobFastPoll();
  const cur = useIntervalPoll(
    async () => {
      const data = await loadCuration();
      setLoaded(true);
      return data;
    },
    EMPTY_CURATION,
    { shouldUpdate: curationDataChanged, intervalMs: 3000, fastPoll },
  );

  const refreshJobs = useCallback(async () => {
    try {
      const rows = await listCurateJobs();
      setJobs(rows);
      setError(null);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    }
  }, []);

  useEffect(() => {
    loadCurateJobOptions()
      .then((opts) => {
        setOptions(opts);
        setSkipLlm(!opts.vllm_available);
      })
      .catch((exc) => setError(exc instanceof Error ? exc.message : String(exc)));
    void refreshJobs();
  }, [refreshJobs]);

  useEffect(() => {
    const hasActive = jobs.some((j) => isCurateJobActive(j.status));
    if (!hasActive) return;
    const timer = setInterval(() => void refreshJobs(), 3000);
    return () => clearInterval(timer);
  }, [jobs, refreshJobs]);

  useEffect(() => {
    if (!selectedId) {
      setLogs("");
      return;
    }

    let cancelled = false;
    let offset = 0;
    setLogs("");

    const poll = async () => {
      try {
        const res = await getCurateJobLogs(selectedId, offset);
        if (cancelled) return;
        if (res.chunk) {
          setLogs((prev) => prev + res.chunk);
        }
        offset = res.offset;
      } catch {
        /* ignore transient log errors */
      }
    };

    void poll();
    const timer = setInterval(() => void poll(), 3000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [selectedId]);

  const onRunCurate = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const job = await createCurateJob({ skip_llm: skipLlm });
      setSelectedId(job.id);
      setLogs("");
      await refreshJobs();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setSubmitting(false);
    }
  };

  const onCancel = async (job: CurateJobRecord) => {
    if (!isCurateJobActive(job.status)) return;
    if (typeof window !== "undefined" && !window.confirm("このジョブを停止しますか？")) {
      return;
    }
    setCancellingId(job.id);
    setError(null);
    try {
      await cancelCurateJob(job.id);
      await refreshJobs();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setCancellingId(null);
    }
  };

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

  const inputReady = options?.input_ready ?? false;
  const vllmAvailable = options?.vllm_available ?? false;

  return (
    <>
      <section className="section">
        <h2>高品質抽出</h2>
        <p style={{ color: "var(--muted)", marginBottom: "1rem" }}>
          API (
          {process.env.NEXT_PUBLIC_JORYU_API_URL || "http://localhost:8000"}
          ) 経由で <code>joryu-curate</code> を実行します。完了後、curation.json が自動更新されます。
        </p>
        {error && <p className="error-banner">{error}</p>}
        {!inputReady && (
          <p style={{ color: "var(--muted)", marginBottom: "1rem" }}>
            蒸留 JSONL が未生成です。先に /jobs から蒸留を実行するか、
            <code> uv run joryu-distill</code> を実行してください。
          </p>
        )}
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={skipLlm}
              onChange={(e) => setSkipLlm(e.target.checked)}
            />
            LLM judge をスキップ (--skip-llm)
            {!vllmAvailable && (
              <span style={{ color: "var(--muted)", marginLeft: "0.5rem" }}>
                vLLM 未起動のため推奨
              </span>
            )}
          </label>
          <button
            type="button"
            className="primary-btn"
            disabled={submitting || !inputReady}
            onClick={() => void onRunCurate()}
          >
            {submitting ? "投入中…" : "高品質抽出を実行"}
          </button>
        </div>
      </section>

      {jobs.length > 0 && (
        <section className="section">
          <h2>抽出ジョブ</h2>
          <table>
            <thead>
              <tr>
                <th>状態</th>
                <th>ID</th>
                <th>skip_llm</th>
                <th>作成</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr
                  key={job.id}
                  className={selectedId === job.id ? "row-selected" : ""}
                  onClick={() => {
                    setSelectedId(job.id);
                    setLogs("");
                  }}
                  style={{ cursor: "pointer" }}
                >
                  <td>
                    <span className={`badge badge-${job.status}`}>
                      {curateStatusLabel(job.status)}
                    </span>
                  </td>
                  <td title={job.id}>{job.id.slice(0, 8)}…</td>
                  <td>{job.spec.skip_llm ? "yes" : "no"}</td>
                  <td>{new Date(job.created_at).toLocaleString()}</td>
                  <td>
                    {isCurateJobActive(job.status) ? (
                      <button
                        type="button"
                        className="danger-btn"
                        disabled={cancellingId === job.id}
                        onClick={(event) => {
                          event.stopPropagation();
                          void onCancel(job);
                        }}
                      >
                        {cancellingId === job.id ? "停止中…" : "停止"}
                      </button>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {selectedId && (
        <section className="section">
          <h2>ログ — {selectedId.slice(0, 8)}…</h2>
          <pre className="snippet log-panel">{logs || "(ログなし)"}</pre>
        </section>
      )}

      {loaded && cur.total === 0 && (
        <p style={{ color: "var(--muted)", marginBottom: "1rem" }}>
          curation.json が未生成または空です。上の「高品質抽出を実行」ボタンを使うか、
          <code> uv run joryu-curate</code> を実行してください。
        </p>
      )}

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
          <p style={{ color: "var(--muted)" }}>データなし</p>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: `repeat(${Math.min(modeEntries.length, 2)}, 1fr)`,
              gap: "1rem",
            }}
          >
            {modeEntries.map(([mode, v]) => (
              <div key={mode}>
                <h3 style={{ fontSize: "0.95rem", color: "var(--muted)" }}>
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
          <p style={{ color: "var(--muted)" }}>
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
