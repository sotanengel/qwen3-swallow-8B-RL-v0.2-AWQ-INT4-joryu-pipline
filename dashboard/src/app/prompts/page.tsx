"use client";

import { useCallback, useEffect, useState } from "react";

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
  seedGenStatusLabel,
} from "@/lib/seed-gen-jobs";
import { createCurateJob } from "@/lib/curate-jobs";
import { loadSystemStatus, profileReady } from "@/lib/system";
import { useIntervalPoll } from "@/lib/useIntervalPoll";

export default function PromptsPage() {
  const [status, setStatus] = useState<SeedGenStatus | null>(null);
  const [jobs, setJobs] = useState<SeedGenJobRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [logs, setLogs] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [domain, setDomain] = useState("");
  const [fakeLlm, setFakeLlm] = useState(true);
  const [dryRun, setDryRun] = useState(false);
  const [manualPrompt, setManualPrompt] = useState("");
  const [manualDomain, setManualDomain] = useState("general_qa");

  useEffect(() => {
    loadSystemStatus()
      .then((sys) => {
        if (!profileReady(sys, "seed_gen")) {
          setFakeLlm(true);
        }
      })
      .catch(() => undefined);
  }, []);

  const polledStatus = useIntervalPoll(
    () => loadSeedGenStatus(),
    null as SeedGenStatus | null,
    { intervalMs: 3000 },
  );
  const displayStatus = polledStatus ?? status;

  const refreshJobs = useCallback(async () => {
    const rows = await listSeedGenJobs();
    setJobs(rows);
  }, []);

  useEffect(() => {
    refreshJobs().catch((exc) => setError(String(exc)));
  }, [refreshJobs]);

  useEffect(() => {
    if (!selectedId) return;
    const tick = () => {
      getSeedGenJobLogs(selectedId)
        .then((res) => setLogs((prev) => prev + res.chunk))
        .catch((exc) => setError(String(exc)));
    };
    tick();
    const id = setInterval(tick, 3000);
    return () => clearInterval(id);
  }, [selectedId]);

  async function submitJob() {
    setError(null);
    try {
      const job = await createSeedGenJob({
        domain,
        fake_llm: fakeLlm,
        dry_run: dryRun,
        target_total: 100,
        batch_size: 8,
      });
      setSelectedId(job.id);
      setLogs("");
      await refreshJobs();
    } catch (exc) {
      setError(String(exc));
    }
  }

  async function runPromptScreening() {
    setError(null);
    try {
      await createCurateJob({ screening: true, prompt_bank: true, skip_llm: false });
    } catch (exc) {
      setError(String(exc));
    }
  }

  return (
    <div className="stack">
      <h2>プロンプト作成</h2>
      {error && <p className="text-danger">{error}</p>}
      {displayStatus && (
        <p>
          バンク総件数: {displayStatus.bank_total} / 目標 {displayStatus.target_total}
        </p>
      )}

      <section>
        <h3>分野進捗</h3>
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
            {(displayStatus?.domains ?? []).map((d) => (
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

      <section className="card">
        <h3>ジョブ起動</h3>
        <div className="job-form">
          <label>
            分野 (空=全分野)
            <input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="math" />
          </label>
          <label className="checkbox-label">
            <input type="checkbox" checked={fakeLlm} onChange={(e) => setFakeLlm(e.target.checked)} />
            fake_llm
          </label>
          <label className="checkbox-label">
            <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
            dry_run
          </label>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <button type="button" className="primary-btn" onClick={submitJob}>
              seed-gen 開始
            </button>
            <button type="button" className="secondary-btn" onClick={runPromptScreening}>
              プロンプト LLM スクリーニング
            </button>
          </div>
        </div>
      </section>

      <section className="card">
        <h3>手動 1 件追加</h3>
        <div className="job-form">
          <label>
            プロンプト
            <textarea value={manualPrompt} onChange={(e) => setManualPrompt(e.target.value)} rows={3} />
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

      <section className="card">
        <h3>ジョブ一覧</h3>
        <ul className="chat-sidebar-list" style={{ padding: 0 }}>
          {jobs.map((job) => (
            <li key={job.id} className="chat-sidebar-item">
              <div className="chat-sidebar-entry-actions">
                <button type="button" className="secondary-btn" onClick={() => setSelectedId(job.id)}>
                  {job.id.slice(0, 8)}… {seedGenStatusLabel(job.status)}
                  {isSeedGenJobActive(job.status) ? " (実行中)" : ""}
                </button>
                {isSeedGenJobActive(job.status) && (
                  <button type="button" className="danger-btn" onClick={() => cancelSeedGenJob(job.id).then(refreshJobs)}>
                    中止
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
        {selectedId && (
          <pre className="snippet log-panel-scroll">{logs}</pre>
        )}
      </section>
    </div>
  );
}
