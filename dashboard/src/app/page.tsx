"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { PipelineStageCard, type PipelineStageId } from "@/components/PipelineStageCard";
import { CheckStagePanel } from "@/components/pipeline/CheckStagePanel";
import { CurateStagePanel } from "@/components/pipeline/CurateStagePanel";
import { DistillStagePanel } from "@/components/pipeline/DistillStagePanel";
import { PromptsStagePanel } from "@/components/pipeline/PromptsStagePanel";
import { ScreeningPanel } from "@/components/stats/ScreeningPanel";
import type { CurateJobRecord } from "@/lib/curate-jobs";
import type { JobRecord } from "@/lib/jobs";
import { EMPTY_STATS, loadStats, statsDataChanged } from "@/lib/stats";
import type { PromptCheckStatus, SeedGenJobRecord } from "@/lib/seed-gen-jobs";
import { loadPromptCheckStatus, loadSeedGenStatus } from "@/lib/seed-gen-jobs";
import { EMPTY_SCREENING, loadScreening, screeningDataChanged } from "@/lib/screening";
import { useIntervalPoll } from "@/lib/useIntervalPoll";

const STAGE_IDS: PipelineStageId[] = ["prompts", "check", "distill", "curate", "screening"];

function useActiveStage(): [PipelineStageId, (id: PipelineStageId) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const raw = params.get("stage");
  const active: PipelineStageId = STAGE_IDS.includes(raw as PipelineStageId)
    ? (raw as PipelineStageId)
    : "prompts";
  const setActive = useCallback(
    (id: PipelineStageId) => {
      router.push(`/?stage=${id}`);
    },
    [router],
  );
  return [active, setActive];
}

function HubContent() {
  const [active, setActive] = useActiveStage();
  const [lastPromptsJob, setLastPromptsJob] = useState<SeedGenJobRecord | null>(null);
  const [lastCheckJob, setLastCheckJob] = useState<SeedGenJobRecord | null>(null);
  const [lastDistillJob, setLastDistillJob] = useState<JobRecord | null>(null);
  const [lastCurateJob, setLastCurateJob] = useState<CurateJobRecord | null>(null);
  const [checkStatus, setCheckStatus] = useState<PromptCheckStatus | null>(null);

  const stats = useIntervalPoll(loadStats, EMPTY_STATS, {
    shouldUpdate: statsDataChanged,
    intervalMs: 3000,
  });
  const seedStatus = useIntervalPoll(loadSeedGenStatus, null, { intervalMs: 3000 });
  const polledCheckStatus = useIntervalPoll(
    loadPromptCheckStatus,
    null as PromptCheckStatus | null,
    { intervalMs: 3000 },
  );
  const screening = useIntervalPoll(loadScreening, EMPTY_SCREENING, {
    shouldUpdate: screeningDataChanged,
    intervalMs: 3000,
  });

  const checkCompleted = useMemo(
    () =>
      (checkStatus ?? polledCheckStatus)?.check_completed ??
      false,
    [checkStatus, polledCheckStatus],
  );

  const promptsMetric = seedStatus
    ? `${seedStatus.bank_total.toLocaleString()} 件`
    : "—";
  const distillMetric = stats.total ? `${stats.total.toLocaleString()} レコード` : "—";
  const screeningMetric = screening.total
    ? `${screening.total.toLocaleString()} 件`
    : "—";

  const [handlePromptsLastJob, handleCheckLastJob, handleDistillLastJob, handleCurateLastJob] =
    useMemo(
      () => [
        (j: SeedGenJobRecord | null) => setLastPromptsJob(j),
        (j: SeedGenJobRecord | null) => setLastCheckJob(j),
        (j: JobRecord | null) => setLastDistillJob(j),
        (j: CurateJobRecord | null) => setLastCurateJob(j),
      ],
      [],
    );

  useEffect(() => {
    // ステージ遷移時にスクロール位置を上に戻す UX 上の配慮
    if (typeof window !== "undefined" && typeof window.scrollTo === "function") {
      try {
        window.scrollTo({ top: 0, behavior: "smooth" });
      } catch {
        /* jsdom / non-DOM 環境 */
      }
    }
  }, [active]);

  return (
    <>
      <section className="section">
        <h2>パイプライン</h2>
        <p className="section-subtitle">
          プロンプト生成 → プロンプトチェック (LLM) → 蒸留 → 高品質抽出 → 健全性 の順で実行します。
          カードを選ぶと下部にステージ別のパネルが開きます。
          統計や履歴は <Link href="/stats">/stats</Link>、出力は <Link href="/outputs">/outputs</Link> で確認できます。
        </p>
        <div className="grid" data-testid="pipeline-stages">
          <PipelineStageCard
            index={1}
            id="prompts"
            title="プロンプト生成"
            description="seed_gen create + 手動追加。LLM がプロンプト候補を生成し Stage1 dedup を通します。"
            metric={promptsMetric}
            lastStatus={lastPromptsJob?.status}
            active={active === "prompts"}
            onSelect={setActive}
          />
          <PipelineStageCard
            index={2}
            id="check"
            title="プロンプトチェック (LLM)"
            description="seed_gen check + LLM 品質スクリーニング (連動起動)。作成したプロンプトは必ずここを通します。"
            metric={
              checkStatus ?? polledCheckStatus
                ? `未チェック: ${(checkStatus ?? polledCheckStatus)!.unchecked_count.toLocaleString()}`
                : lastCheckJob
                  ? `最新チェック: ${lastCheckJob.status}`
                  : "未実施"
            }
            lastStatus={lastCheckJob?.status}
            active={active === "check"}
            onSelect={setActive}
            warning={
              !checkCompleted && lastPromptsJob
                ? "作成済みプロンプトのチェックが未完了です。"
                : undefined
            }
          />
          <PipelineStageCard
            index={3}
            id="distill"
            title="蒸留"
            description="joryu-distill: style × temperature × top_p × tools の直積で蒸留を実行します。"
            metric={distillMetric}
            lastStatus={lastDistillJob?.status}
            active={active === "distill"}
            onSelect={setActive}
            warning={
              !checkCompleted
                ? "プロンプトチェック未完了。②を先に実行してください。"
                : undefined
            }
          />
          <PipelineStageCard
            index={4}
            id="curate"
            title="高品質抽出"
            description="joryu-curate: 蒸留 JSONL に LLM-RUBRIC 判定と閾値フィルタを適用します。"
            metric={distillMetric}
            lastStatus={lastCurateJob?.status}
            active={active === "curate"}
            onSelect={setActive}
          />
          <PipelineStageCard
            index={5}
            id="screening"
            title="健全性"
            description="健全性スクリーニング結果 (screening.json) を確認します。詳細は /stats?tab=screening。"
            metric={screeningMetric}
            active={active === "screening"}
            onSelect={setActive}
          />
        </div>
      </section>

      <section className="section" data-testid="pipeline-active-panel" data-active={active}>
        {active === "prompts" && (
          <PromptsStagePanel onLastJob={handlePromptsLastJob} />
        )}
        {active === "check" && (
          <CheckStagePanel
            onLastJob={handleCheckLastJob}
            onCheckStatusChange={setCheckStatus}
          />
        )}
        {active === "distill" && (
          <DistillStagePanel
            checkCompleted={checkCompleted}
            onLastJob={handleDistillLastJob}
          />
        )}
        {active === "curate" && <CurateStagePanel onLastJob={handleCurateLastJob} />}
        {active === "screening" && (
          <div data-testid="panel-screening">
            <p className="muted" style={{ marginBottom: "1rem" }}>
              スクリーニングは「プロンプトチェック」ステージから curate と一緒に自動起動されます。
              詳細履歴は <Link href="/stats?tab=screening">/stats?tab=screening</Link> でも確認できます。
            </p>
            <ScreeningPanel />
          </div>
        )}
      </section>
    </>
  );
}

export default function HomePage() {
  return (
    <Suspense fallback={<p className="muted">パイプラインを初期化しています…</p>}>
      <HubContent />
    </Suspense>
  );
}
