"use client";

import { useCallback, useEffect, useState } from "react";

import { JobPanel } from "@/components/JobPanel";
import { createCurateJob } from "@/lib/curate-jobs";
import {
  PromptBankItem,
  PromptCheckStatus,
  SeedGenJobRecord,
  cancelSeedGenJob,
  createSeedGenJob,
  getSeedGenJobLogs,
  isSeedGenJobActive,
  listPromptBank,
  listSeedGenJobs,
  loadPromptCheckStatus,
  markPromptsChecked,
  seedGenModeLabel,
} from "@/lib/seed-gen-jobs";
import { useIntervalPoll } from "@/lib/useIntervalPoll";
import { useJobList } from "@/lib/useJobList";
import { useJobLogs } from "@/lib/useJobLogs";

const PAGE_SIZE = 50;

export function CheckStagePanel({
  onLastJob,
  onCheckStatusChange,
}: {
  onLastJob?: (job: SeedGenJobRecord | null) => void;
  onCheckStatusChange?: (status: PromptCheckStatus | null) => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [domain, setDomain] = useState("");
  const [listDomain, setListDomain] = useState("");
  const [cancellingId, setCancellingId] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [promptList, setPromptList] = useState<PromptBankItem[]>([]);
  const [promptTotal, setPromptTotal] = useState(0);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [marking, setMarking] = useState(false);

  const checkStatus = useIntervalPoll(loadPromptCheckStatus, null as PromptCheckStatus | null, {
    intervalMs: 3000,
  });

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

  useEffect(() => {
    onCheckStatusChange?.(checkStatus);
  }, [checkStatus, onCheckStatusChange]);

  const refreshPromptList = useCallback(async () => {
    try {
      const data = await listPromptBank({
        offset,
        limit: PAGE_SIZE,
        domain: listDomain,
        checked: "all",
      });
      setPromptList(data.items);
      setPromptTotal(data.total);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    }
  }, [offset, listDomain]);

  useEffect(() => {
    void refreshPromptList();
  }, [refreshPromptList]);

  const toggleKey = (key: string) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const selectPageUnchecked = () => {
    setSelectedKeys(new Set(promptList.filter((p) => !p.checked).map((p) => p.key)));
  };

  const clearSelection = () => setSelectedKeys(new Set());

  async function submitMarkSelected() {
    if (selectedKeys.size === 0) return;
    setMarking(true);
    setError(null);
    try {
      await markPromptsChecked({ keys: [...selectedKeys] });
      clearSelection();
      await refreshPromptList();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setMarking(false);
    }
  }

  async function submitMarkAllUnchecked() {
    setMarking(true);
    setError(null);
    try {
      await markPromptsChecked({ all_unchecked: true, domain: listDomain });
      clearSelection();
      await refreshPromptList();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setMarking(false);
    }
  }

  async function submitCheck() {
    if (checkStatus && checkStatus.unchecked_count === 0) {
      setError("未チェックのプロンプトがありません。");
      return;
    }
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
    <>
      <section className="card">
        <h3>プロンプトチェック (LLM 品質スクリーニング)</h3>
        {checkStatus && (
          <p className="muted" data-testid="check-status-summary">
            チェック済み {checkStatus.checked_count.toLocaleString()} /{" "}
            {checkStatus.bank_total.toLocaleString()} 件
            {checkStatus.unchecked_count > 0 &&
              `（未チェック ${checkStatus.unchecked_count.toLocaleString()} 件）`}
          </p>
        )}
        <div className="job-form">
          <label>
            分野 (空=全分野)
            <input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="math" />
          </label>
          <button
            type="button"
            className="primary-btn"
            onClick={submitCheck}
            disabled={checkStatus?.unchecked_count === 0}
          >
            未チェック分をチェック + LLM スクリーニング
          </button>
          <p className="hint">
            Stage2 類似 dedup + LLM 品質審査（未チェック分のみ）。
            既に審査済みのプロンプトは下の一覧から選択してチェック済み登録できます。
          </p>
        </div>
      </section>

      <section className="card" data-testid="prompt-check-list">
        <h3>チェック済み手動登録</h3>
        <p className="hint">
          実際に品質確認済みのプロンプトのみ選択してください。登録後は再チェック対象から除外され、蒸留可能になります。
        </p>
        <div className="job-form">
          <label>
            一覧フィルタ分野
            <input
              value={listDomain}
              onChange={(e) => {
                setListDomain(e.target.value);
                setOffset(0);
              }}
              placeholder="空=全分野"
            />
          </label>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <button type="button" onClick={selectPageUnchecked}>
              ページ内未チェックを全選択
            </button>
            <button type="button" onClick={clearSelection}>
              選択解除
            </button>
            <button
              type="button"
              className="primary-btn"
              disabled={marking || selectedKeys.size === 0}
              onClick={submitMarkSelected}
            >
              選択をチェック済み登録 ({selectedKeys.size})
            </button>
            <button
              type="button"
              disabled={marking || (checkStatus?.unchecked_count ?? 0) === 0}
              onClick={submitMarkAllUnchecked}
            >
              未チェックをすべて登録
            </button>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th></th>
              <th>分野</th>
              <th>プロンプト</th>
              <th>状態</th>
            </tr>
          </thead>
          <tbody>
            {promptList.map((item) => (
              <tr key={item.key}>
                <td>
                  <input
                    type="checkbox"
                    checked={selectedKeys.has(item.key)}
                    disabled={item.checked}
                    onChange={() => toggleKey(item.key)}
                    aria-label={`select ${item.key}`}
                  />
                </td>
                <td>{item.domain ?? "—"}</td>
                <td>{item.prompt_preview}</td>
                <td>{item.checked ? "済" : "未"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }}>
          <button
            type="button"
            disabled={offset === 0}
            onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
          >
            前へ
          </button>
          <span className="muted">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, promptTotal)} / {promptTotal}
          </span>
          <button
            type="button"
            disabled={offset + PAGE_SIZE >= promptTotal}
            onClick={() => setOffset((o) => o + PAGE_SIZE)}
          >
            次へ
          </button>
        </div>
      </section>
    </>
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
