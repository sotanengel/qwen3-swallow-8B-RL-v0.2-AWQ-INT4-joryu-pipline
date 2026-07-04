"use client";

import { useCallback, useEffect, useState } from "react";

import { JobPanel } from "@/components/JobPanel";
import {
  CurateJobOptions,
  CurateJobRecord,
  cancelCurateJob,
  createCurateJob,
  getCurateJobLogs,
  isCurateJobActive,
  listCurateJobs,
  loadCurateJobOptions,
} from "@/lib/curate-jobs";
import { useJobList } from "@/lib/useJobList";
import { useJobLogs } from "@/lib/useJobLogs";

export function CurateStagePanel({
  onLastJob,
}: {
  onLastJob?: (job: CurateJobRecord | null) => void;
}) {
  const [options, setOptions] = useState<CurateJobOptions | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  const [jobs, refreshJobs, listError] = useJobList<CurateJobRecord>(
    listCurateJobs,
    useCallback((j: CurateJobRecord) => isCurateJobActive(j.status), []),
  );

  const logs = useJobLogs(selectedId, getCurateJobLogs);

  useEffect(() => {
    loadCurateJobOptions()
      .then((opts) => setOptions(opts))
      .catch((exc) => setError(exc instanceof Error ? exc.message : String(exc)));
  }, []);

  useEffect(() => {
    if (!onLastJob) return;
    onLastJob(jobs[0] ?? null);
  }, [jobs, onLastJob]);

  const onRun = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const job = await createCurateJob({ skip_llm: false });
      setSelectedId(job.id);
      await refreshJobs();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setSubmitting(false);
    }
  };

  const onCancel = async (job: CurateJobRecord) => {
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

  const inputReady = options?.input_ready ?? false;

  const form = (
    <div className="card card-stack">
      {!inputReady && (
        <p className="section-subtitle">
          蒸留 JSONL が未生成です。先に「蒸留」ステージを実行するか、
          <code> uv run joryu-distill</code> を実行してください。
        </p>
      )}
      <button
        type="button"
        className="primary-btn"
        disabled={submitting || !inputReady}
        onClick={() => void onRun()}
      >
        {submitting ? "投入中…" : "高品質抽出を実行"}
      </button>
    </div>
  );

  return (
    <JobPanel<CurateJobRecord>
      form={form}
      error={error ?? listError}
      jobs={jobs}
      selectedId={selectedId}
      onSelect={setSelectedId}
      onCancel={onCancel}
      cancellingId={cancellingId}
      jobsHeader="高品質抽出ジョブ"
      emptyJobsLabel="抽出ジョブはまだありません。"
      extraColumns={[
        { key: "skip_llm", header: "skip_llm", render: (j) => (j.spec.skip_llm ? "yes" : "no") },
      ]}
      logs={logs}
    />
  );
}
