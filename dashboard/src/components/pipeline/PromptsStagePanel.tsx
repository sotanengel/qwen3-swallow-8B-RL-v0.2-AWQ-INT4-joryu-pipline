"use client";

import { useCallback, useEffect, useState } from "react";

import { JobPanel } from "@/components/JobPanel";
import {
  SeedGenJobRecord,
  SeedGenStatus,
  appendManualPrompt,
  cancelSeedGenJob,
  createSeedGenJob,
  getSeedGenJobLogs,
  isSeedGenJobActive,
  listSeedGenJobs,
  loadSeedGenStatus,
  seedGenModeLabel,
} from "@/lib/seed-gen-jobs";
import { useIntervalPoll } from "@/lib/useIntervalPoll";
import { useJobList } from "@/lib/useJobList";
import { useJobLogs } from "@/lib/useJobLogs";

export function PromptsStagePanel({
  onLastJob,
}: {
  onLastJob?: (job: SeedGenJobRecord | null) => void;
}) {
  const [status, setStatus] = useState<SeedGenStatus | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [domain, setDomain] = useState("");
  const [manualPrompt, setManualPrompt] = useState("");
  const [manualDomain, setManualDomain] = useState("general_qa");
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  const polledStatus = useIntervalPoll(() => loadSeedGenStatus(), null as SeedGenStatus | null, {
    intervalMs: 3000,
  });
  const displayStatus = polledStatus ?? status;

  const [jobs, refreshJobs, listError] = useJobList<SeedGenJobRecord>(
    listSeedGenJobs,
    useCallback((j: SeedGenJobRecord) => isSeedGenJobActive(j.status), []),
  );

  const logs = useJobLogs(selectedId, getSeedGenJobLogs);

  useEffect(() => {
    if (!onLastJob) return;
    const createJobs = jobs.filter((j) => j.spec.mode === "create");
    onLastJob(createJobs[0] ?? null);
  }, [jobs, onLastJob]);

  async function submitCreate() {
    setError(null);
    try {
      const job = await createSeedGenJob({
        domain,
        mode: "create",
        target_total: 100,
        batch_size: 8,
      });
      setSelectedId(job.id);
      await refreshJobs();
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
    <>
      <section className="card">
        <h3>プロンプト生成 (seed_gen create)</h3>
        <div className="job-form">
          <label>
            分野 (空=全分野)
            <input
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              placeholder="math"
            />
          </label>
          <button type="button" className="primary-btn" onClick={submitCreate}>
            プロンプト作成を実行
          </button>
          <p className="hint">
            LLM 生成 + Stage1 完全一致 dedup。作成後は次ステージ「プロンプトチェック」で LLM 審査を必ず実施してください。
          </p>
        </div>
      </section>

      <section className="card">
        <h3>手動 1 件追加</h3>
        <div className="job-form">
          <label>
            プロンプト
            <textarea
              value={manualPrompt}
              onChange={(e) => setManualPrompt(e.target.value)}
              rows={3}
            />
          </label>
          <label>
            分野
            <input value={manualDomain} onChange={(e) => setManualDomain(e.target.value)} />
          </label>
          <button
            type="button"
            className="primary-btn"
            onClick={() =>
              appendManualPrompt(manualPrompt, manualDomain)
                .then(() => loadSeedGenStatus().then(setStatus))
                .catch((exc) => setError(String(exc)))
            }
          >
            追記
          </button>
        </div>
      </section>

      {displayStatus && (
        <section className="card">
          <h3>
            分野進捗 (バンク総件数 {displayStatus.bank_total} / 目標 {displayStatus.target_total})
          </h3>
          <table>
            <thead>
              <tr>
                <th>分野</th>
                <th>現在</th>
                <th>目標</th>
                <th>達成率</th>
              </tr>
            </thead>
            <tbody>
              {(displayStatus.domains ?? []).map((d) => (
                <tr key={d.key} className={d.ratio >= 0.8 ? "domain-ratio-ok" : undefined}>
                  <td>{d.key}</td>
                  <td>{d.current}</td>
                  <td>{d.target}</td>
                  <td>{(d.ratio * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  );

  return (
    <JobPanel<SeedGenJobRecord>
      form={form}
      error={error ?? listError}
      jobs={jobs.filter((j) => j.spec.mode === "create")}
      selectedId={selectedId}
      onSelect={setSelectedId}
      onCancel={onCancel}
      cancellingId={cancellingId}
      jobsHeader="プロンプト生成ジョブ"
      emptyJobsLabel="プロンプト生成ジョブはまだありません。"
      extraColumns={[
        { key: "mode", header: "モード", render: (j) => seedGenModeLabel(j.spec.mode) },
        { key: "domain", header: "分野", render: (j) => j.spec.domain || "全分野" },
      ]}
      logs={logs}
    />
  );
}
