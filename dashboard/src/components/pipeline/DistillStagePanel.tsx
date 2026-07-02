"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { JobPanel } from "@/components/JobPanel";
import {
  CreateJobRequest,
  DurationUnit,
  JobOptions,
  JobRecord,
  cancelJob,
  createJob,
  defaultJobSelections,
  formatJobDuration,
  getJobLogs,
  isJobActive,
  listJobs,
  loadJobOptions,
} from "@/lib/jobs";
import { useJobList } from "@/lib/useJobList";
import { useJobLogs } from "@/lib/useJobLogs";

export function DistillStagePanel({
  checkCompleted,
  onLastJob,
}: {
  checkCompleted: boolean;
  onLastJob?: (job: JobRecord | null) => void;
}) {
  const [options, setOptions] = useState<JobOptions | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  const [count, setCount] = useState(0);
  const [durationValue, setDurationValue] = useState<number | "">(2);
  const [durationUnit, setDurationUnit] = useState<DurationUnit>("h");
  const [styles, setStyles] = useState<string[]>([]);
  const [temperature, setTemperature] = useState("");
  const [topP, setTopP] = useState("");
  const [toolIds, setToolIds] = useState<string[]>([]);
  const [toolLoop, setToolLoop] = useState(true);
  const [maxTurns, setMaxTurns] = useState<number | "">("");

  const [jobs, refreshJobs, listError] = useJobList<JobRecord>(
    listJobs,
    useCallback((j: JobRecord) => isJobActive(j.status), []),
  );

  const logs = useJobLogs(selectedId, getJobLogs);

  useEffect(() => {
    loadJobOptions()
      .then((opts) => {
        setOptions(opts);
        const defaults = defaultJobSelections(opts);
        setStyles(defaults.styles);
        setToolIds(defaults.toolIds);
        setToolLoop(defaults.toolLoop);
      })
      .catch((exc) => setError(exc instanceof Error ? exc.message : String(exc)));
  }, []);

  useEffect(() => {
    if (!onLastJob) return;
    onLastJob(jobs[0] ?? null);
  }, [jobs, onLastJob]);

  const toggleStyle = (id: string) => {
    setStyles((prev) => (prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]));
  };
  const toggleTool = (id: string) => {
    setToolIds((prev) => (prev.includes(id) ? prev.filter((t) => t !== id) : [...prev, id]));
  };

  const onCancel = async (job: JobRecord) => {
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
      duration: formatJobDuration(durationValue, durationUnit),
      style: styles,
      temperature: temperature.trim(),
      top_p: topP.trim(),
      tool_ids: toolIds,
      tool_loop: toolLoop,
      max_turns: maxTurns === "" ? null : maxTurns,
    };
    try {
      const job = await createJob(body);
      setSelectedId(job.id);
      await refreshJobs();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setSubmitting(false);
    }
  };

  const form = (
    <>
      {!checkCompleted && (
        <div
          className="warning-banner"
          role="alert"
          data-testid="check-required-warning"
          style={{ marginBottom: "1rem" }}
        >
          プロンプトチェック (LLM 品質スクリーニング) が未完了です。
          蒸留に進む前に「プロンプトチェック」ステージを必ず実行してください。
        </div>
      )}
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
          <div className="duration-inputs">
            <input
              type="number"
              min={1}
              placeholder="制限なし"
              value={durationValue}
              onChange={(e) =>
                setDurationValue(e.target.value === "" ? "" : Number(e.target.value))
              }
            />
            <select
              value={durationUnit}
              onChange={(e) => setDurationUnit(e.target.value as DurationUnit)}
            >
              <option value="h">h</option>
              <option value="m">min</option>
            </select>
          </div>
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
          <legend>ツール (tools)</legend>
          <p className="muted" style={{ fontSize: "0.875rem", margin: "0 0 0.5rem" }}>
            プロンプト行に tool_ids が無い行にのみ適用されます。
          </p>
          <div className="style-grid">
            {(options?.tools ?? []).map((t) => (
              <label key={t.id} className="checkbox-label" title={t.description}>
                <input
                  type="checkbox"
                  checked={toolIds.includes(t.id)}
                  onChange={() => toggleTool(t.id)}
                />
                {t.id}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={toolLoop}
            onChange={(e) => setToolLoop(e.target.checked)}
          />
          tool 実行ループ (tool_loop)
        </label>
        {toolLoop && (
          <label>
            最大ターン (max_turns)
            <input
              type="number"
              min={1}
              placeholder="既定 (config)"
              value={maxTurns}
              onChange={(e) =>
                setMaxTurns(e.target.value === "" ? "" : Number(e.target.value))
              }
            />
          </label>
        )}
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
          {submitting ? "投入中…" : "蒸留を実行"}
        </button>
      </form>
    </>
  );

  return (
    <JobPanel<JobRecord>
      form={form}
      error={error ?? listError}
      jobs={jobs}
      selectedId={selectedId}
      onSelect={setSelectedId}
      onCancel={onCancel}
      cancellingId={cancellingId}
      jobsHeader="蒸留ジョブ"
      emptyJobsLabel="蒸留ジョブはまだありません。"
      extraColumns={[
        { key: "count", header: "count", render: (j) => j.spec.count },
        { key: "exit", header: "exit", render: (j) => j.exit_code ?? "—" },
      ]}
      logs={logs}
    />
  );
}
