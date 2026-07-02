"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

export type StatsTabKey = "overview" | "distributions" | "curation" | "screening";

export type StatsTabsProps = {
  active: StatsTabKey;
  onChange?: (key: StatsTabKey) => void;
};

const TABS: { key: StatsTabKey; label: string }[] = [
  { key: "overview", label: "概要" },
  { key: "distributions", label: "分布" },
  { key: "curation", label: "抽出品質" },
  { key: "screening", label: "健全性" },
];

export function useStatsActiveTab(defaultKey: StatsTabKey = "overview"): StatsTabKey {
  const params = useSearchParams();
  const key = params.get("tab");
  if (key && TABS.some((t) => t.key === key)) return key as StatsTabKey;
  return defaultKey;
}

export function StatsTabs({ active, onChange }: StatsTabsProps) {
  const router = useRouter();

  const setTab = useCallback(
    (key: StatsTabKey) => {
      if (onChange) {
        onChange(key);
        return;
      }
      router.push(`/stats?tab=${key}`);
    },
    [router, onChange],
  );

  return (
    <nav
      role="tablist"
      aria-label="統計タブ"
      data-testid="stats-tabs"
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "0.25rem 0.5rem",
        marginBottom: "1rem",
      }}
    >
      {TABS.map((t) => (
        <button
          key={t.key}
          type="button"
          role="tab"
          aria-selected={active === t.key}
          className={`nav-link${active === t.key ? " nav-link-active" : ""}`}
          onClick={() => setTab(t.key)}
          data-testid={`stats-tab-${t.key}`}
        >
          {t.label}
        </button>
      ))}
    </nav>
  );
}
