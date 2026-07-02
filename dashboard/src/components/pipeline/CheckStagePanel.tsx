"use client";

import { useCallback, useEffect, useState } from "react";

import { JobPanel } from "@/components/JobPanel";
import { createCurateJob } from "@/lib/curate-jobs";
import {
  SeedGenJobRecord,
  cancelSeedGenJob,
  createSeedGenJob,
  getSeedGenJobLogs,
  isSeedGenJobActive,
  listSeedGenJobs,
  seedGenModeLabel,
} from "@/lib/seed-gen-jobs";
import { useJobList } from "@/lib/useJobList";
import { useJobLogs } from "@/lib/useJobLogs";

export function CheckStagePanel({
  onLastJob,
}: {
  onLastJob?: (job: SeedGenJobRecord | null) => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [domain, setDomain] = useState("");
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  const [jobs, refreshJobs, listError] = useJobList<SeedGenJobRecord>(
    listSeedGenJobs,
    useCallback((j: SeedGenJobRecord) => isSeedGenJobActive(j.status), []),
  );

  const logs = useJobLogs(selectedId, getSeedGenJobLogs);

  useEffect(() => {
    if (!onLastJob) return;
    const checkJobs = jobs.filter((j) => j.spec.mode === "check");
    onLastJob(checkJobs[0] ?? null);
  }, [jobs, onLastJob]);

  async function submitCheck() {
    setError(null);
    try {
      const job = await createSeedGenJob({
        domain,
        mode: "check",
        target_total: 100,
        batch_size: 8,
      });
      setSelectedId(job.id);
      await refreshJobs();
      // LLM 品質スクリーニングを連動起動
      await createCurateJob({ screening: true, prompt_bank: true, skip_llm: false });
    } catch (exc) {
      setError(String(exc));
    }
  }

  const onCancel = async (job: SeedGenJobRecord) => {
    setCancellingId(job.id);
    setError(null);
    try {
      await cancelSeedGenJob(job.id);
      await refreshJobs();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setCancellingId(null);
    }
  };

  const form = (
    <section className="card">
      <h3>プロンプトチェック (LLM 品質スクリーニング)</h3>
      <div className="job-form">
        <label>
          分野 (空=全分野)
          <input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="math" />
        </label>
        <button type="button" className="primary-btn" onClick={submitCheck}>
          チェック + 健全性スクリーニングを実行
        </button>
        <p className="hint">
          Stage2 類似 dedup + LLM 品質審査。<strong>プロンプト作成後、蒸留に進む前に必ず本ステージを実行してください。</strong>
          seed_gen check と curate screening を同時に起動します。
        </p>
      </div>
    </section>
  );

  return (
    <JobPanel<SeedGenJobRecord>
      form={form}
      error={error ?? listError}
      jobs={jobs.filter((j) => j.spec.mode === "check")}
      selectedId={selectedId}
      onSelect={setSelectedId}
      onCancel={onCancel}
      cancellingId={cancellingId}
      jobsHeader="プロンプトチェックジョブ"
      emptyJobsLabel="チェックジョブはまだありません。"
      extraColumns={[
        { key: "mode", header: "モード", render: (j) => seedGenModeLabel(j.spec.mode) },
        { key: "domain", header: "分野", render: (j) => j.spec.domain || "全分野" },
      ]}
      logs={logs}
    />
  );
}
