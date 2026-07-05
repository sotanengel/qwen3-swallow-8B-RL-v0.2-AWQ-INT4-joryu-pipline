"use client";

import type { ReactNode } from "react";

import { StatusBadge } from "@/components/StatusBadge";

export type PipelineStageId =
  | "prompts"
  | "check"
  | "distill"
  | "curate";

export type PipelineStageCardProps = {
  index: number;
  id: PipelineStageId;
  title: string;
  description: ReactNode;
  metric?: ReactNode;
  lastStatus?: string | null;
  active: boolean;
  onSelect: (id: PipelineStageId) => void;
  actionLabel?: string;
  warning?: ReactNode;
};

/**
 * パイプラインの 1 ステージ (プロンプト生成 / プロンプトチェック / 蒸留 / 高品質抽出)。
 * カードを選ぶと onSelect が発火し、下部の JobPanel が該当ステージに切り替わる。
 */
export function PipelineStageCard({
  index,
  id,
  title,
  description,
  metric,
  lastStatus,
  active,
  onSelect,
  actionLabel = "パネルを開く",
  warning,
}: PipelineStageCardProps) {
  return (
    <div
      className={`card${active ? " row-selected" : ""}`}
      data-testid={`pipeline-stage-${id}`}
      data-active={active}
      style={{
        cursor: "pointer",
        borderColor: active ? "var(--accent)" : undefined,
      }}
      onClick={() => onSelect(id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(id);
        }
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
          marginBottom: "0.5rem",
        }}
      >
        <span
          style={{
            fontWeight: 600,
            color: "var(--muted)",
            minWidth: "1.6em",
          }}
        >
          {`${index}.`}
        </span>
        <h3 style={{ margin: 0, flex: 1 }}>{title}</h3>
        {lastStatus && <StatusBadge status={lastStatus} />}
      </div>
      <div className="muted" style={{ fontSize: "0.85rem", marginBottom: "0.5rem" }}>
        {description}
      </div>
      {metric && (
        <div
          className="value"
          data-testid={`pipeline-stage-${id}-metric`}
          style={{ fontSize: "1.4rem", marginBottom: "0.5rem" }}
        >
          {metric}
        </div>
      )}
      {warning && (
        <div className="warning-banner" role="alert" style={{ marginBottom: "0.5rem" }}>
          {warning}
        </div>
      )}
      <button
        type="button"
        className={active ? "primary-btn" : "secondary-btn"}
        onClick={(e) => {
          e.stopPropagation();
          onSelect(id);
        }}
        data-testid={`pipeline-stage-${id}-btn`}
      >
        {actionLabel}
      </button>
    </div>
  );
}
