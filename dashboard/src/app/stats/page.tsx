"use client";

import { Suspense } from "react";

import { StatsTabs, useStatsActiveTab } from "@/components/StatsTabs";
import { CurationQualityPanel } from "@/components/stats/CurationQualityPanel";
import { DistributionsPanel } from "@/components/stats/DistributionsPanel";
import { OverviewPanel } from "@/components/stats/OverviewPanel";

function StatsContent() {
  const active = useStatsActiveTab();
  return (
    <>
      <StatsTabs active={active} />
      <div data-testid="stats-panel" data-active={active}>
        {active === "overview" && <OverviewPanel />}
        {active === "distributions" && <DistributionsPanel />}
        {active === "curation" && <CurationQualityPanel />}
      </div>
    </>
  );
}

export default function StatsPage() {
  return (
    <Suspense fallback={<p className="muted">統計を読み込み中…</p>}>
      <StatsContent />
    </Suspense>
  );
}
