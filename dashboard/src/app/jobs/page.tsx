"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import {
  CreateJobRequest,
  JobOptions,
  JobRecord,
  cancelJob,
  createJob,
  getJobLogs,
  isJobActive,
  listJobs,
  loadJobOptions,
  statusLabel,
} from "@/lib/jobs";

function StatusBadge({ status }: { status: JobRecord["status"] }) {
  return <span className={`badge badge-${status}`}>{statusLabel(status)}</span>;
}

export default function JobsPage() {
  const [options, setOptions] = useState<JobOptions | null>(null);
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [logs, setLogs] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [cancellingId, setCancellingId] = useState<string | null>(null);

  const [count, setCount] = useState(0);
  const [duration, setDuration] = useState("");
  const [mode, setMode] = useState<string>("");
  const [styles, setStyles] = useState<string[]>([]);
  const [temperature, setTemperature] = useState("");
  const [topP, setTopP] = useState("");

  const refreshJobs = useCallback(async () => {
    try {
      const rows = await listJobs();
      setJobs(rows);
      setError(null);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    }
  }, []);

  useEffect(() => {
    loadJobOptions()
      .then((opts) => {
        setOptions(opts);
        setMode(opts.defaults.mode);
      })
      .catch((exc) => setError(exc instanceof Error ? exc.message : String(exc)));
    refreshJobs();
  }, [refreshJobs]);

  useEffect(() => {
    const hasActive = jobs.some((j) => j.status === "queued" || j.status === "running");
    if (!hasActive) return;
    const timer = setInterval(refreshJobs, 3000);
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
        const res = await getJobLogs(selectedId, offset);
        if (cancelled) return;
        if (res.chunk) {
          setLogs((prev) => prev + res.chunk);
        }
        offset = res.offset;
      } catch {
        /* ignore transient log errors */
      }
    };

    poll();
    const timer = setInterval(poll, 3000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [selectedId]);

  const toggleStyle = (id: string) => {
    setStyles((prev) => (prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]));
  };

  const onCancel = async (job: JobRecord) => {
    if (!isJobActive(job.status)) return;
    if (typeof window !== "undefined" && !window.confirm("このジョブを停止しますか？")) {
      return;
    }
    setCancellingId(job.id);
    setError(null);
    try {
      await cancelJob(job.id);
      await refreshJobs();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setCancellingId(null);
    }
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const body: CreateJobRequest = {
      count,
      duration: duration.trim(),
      mode: mode || null,
      style: styles,
      temperature: temperature.trim(),
      top_p: topP.trim(),
    };
    try {
      const job = await createJob(body);
      setSelectedId(job.id);
      setLogs("");
      await refreshJobs();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <section className="section">
        <h2>蒸留ジョブ投入</h2>
        <p style={{ color: "var(--muted)", marginBottom: "1rem" }}>
          joryu-distill と同等のパラメータでローカル LLM 蒸留を実行します。API (
          {process.env.NEXT_PUBLIC_JORYU_API_URL || "http://localhost:8000"}) が起動している必要があります。
        </p>
        {error && <p className="error-banner">{error}</p>}
        <form className="job-form card" onSubmit={onSubmit}>
          <label>
            件数 (count)
            <input
              type="number"
              min={0}
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
            />
          </label>
          <label>
            時間上限 (duration)
            <input
              type="text"
              placeholder="例: 2h, 30m"
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
            />
          </label>
          <label>
            モード
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="">既定</option>
              {(options?.modes ?? ["thinking", "nothinking"]).map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          <label>
            temperature (カンマ区切り)
            <input
              type="text"
              placeholder="0.5,0.7,1.0"
              value={temperature}
              onChange={(e) => setTemperature(e.target.value)}
            />
          </label>
          <label>
            top_p (カンマ区切り)
            <input
              type="text"
              placeholder="0.8,0.9,0.95"
              value={topP}
              onChange={(e) => setTopP(e.target.value)}
            />
          </label>
          <fieldset className="style-fieldset">
            <legend>文体 (style)</legend>
            <div className="style-grid">
              {(options?.styles ?? []).map((s) => (
                <label key={s.id} className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={styles.includes(s.id)}
                    onChange={() => toggleStyle(s.id)}
                  />
                  {s.label}
                </label>
              ))}
            </div>
          </fieldset>
          <button type="submit" className="primary-btn" disabled={submitting}>
            {submitting ? "投入中…" : "ジョブを実行"}
          </button>
        </form>
      </section>

      <section className="section">
        <h2>ジョブ一覧</h2>
        {jobs.length === 0 ? (
          <p style={{ color: "var(--muted)" }}>ジョブはまだありません。</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>状態</th>
                <th>ID</th>
                <th>count</th>
                <th>作成</th>
                <th>終了</th>
                <th>exit</th>
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
                    <StatusBadge status={job.status} />
                  </td>
                  <td title={job.id}>{job.id.slice(0, 8)}…</td>
                  <td>{job.spec.count}</td>
                  <td>{new Date(job.created_at).toLocaleString()}</td>
                  <td>{job.finished_at ? new Date(job.finished_at).toLocaleString() : "—"}</td>
                  <td>{job.exit_code ?? "—"}</td>
                  <td>
                    {isJobActive(job.status) ? (
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
        )}
      </section>

      {selectedId && (
        <section className="section">
          <h2>ログ — {selectedId.slice(0, 8)}…</h2>
          <pre className="snippet log-panel">{logs || "(ログなし)"}</pre>
        </section>
      )}
    </>
  );
}
