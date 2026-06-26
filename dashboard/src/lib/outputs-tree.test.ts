import { describe, expect, it } from "vitest";

import { DistilledRecord } from "./jsonl";
import { buildOutputsTree, styleLabel } from "./outputs-tree";

function rec(overrides: Partial<DistilledRecord> = {}): DistilledRecord {
  return {
    prompt: "test",
    answer: "answer",
    ...overrides,
  };
}

describe("styleLabel", () => {
  it("maps known style ids to Japanese labels", () => {
    expect(styleLabel("prose")).toBe("散文");
    expect(styleLabel("qa_short")).toBe("短答");
    expect(styleLabel("dialog")).toBe("対話");
    expect(styleLabel("report")).toBe("レポート");
  });

  it("returns the id for unknown styles", () => {
    expect(styleLabel("custom_style")).toBe("custom_style");
  });

  it("returns (default) for empty values", () => {
    expect(styleLabel(null)).toBe("(default)");
    expect(styleLabel(undefined)).toBe("(default)");
    expect(styleLabel("")).toBe("(default)");
  });
});

describe("buildOutputsTree", () => {
  it("returns empty array for no records", () => {
    expect(buildOutputsTree([])).toEqual([]);
  });

  it("groups records by category and style_id", () => {
    const records = [
      rec({ category: "国語", style_id: "prose", prompt: "a" }),
      rec({ category: "国語", style_id: "dialog", prompt: "b" }),
      rec({ category: "数学", style_id: "prose", prompt: "c" }),
    ];
    const tree = buildOutputsTree(records);
    expect(tree).toHaveLength(2);
    expect(tree[0].category).toBe("国語");
    expect(tree[0].styles).toHaveLength(2);
    expect(tree[1].category).toBe("数学");
    expect(tree[1].styles).toHaveLength(1);
    expect(tree[1].styles[0].styleId).toBe("prose");
  });

  it("uses (未分類) and (default) for missing values", () => {
    const records = [rec({ prompt: "x" })];
    const tree = buildOutputsTree(records);
    expect(tree).toHaveLength(1);
    expect(tree[0].category).toBe("(未分類)");
    expect(tree[0].styles[0].styleId).toBe("(default)");
  });

  it("aggregates count, truncatedCount, and latestCreatedAt per category", () => {
    const records = [
      rec({
        category: "国語",
        style_id: "prose",
        created_at: "2026-01-01T00:00:00Z",
        finish_reason: "length",
      }),
      rec({
        category: "国語",
        style_id: "dialog",
        created_at: "2026-06-01T00:00:00Z",
      }),
    ];
    const tree = buildOutputsTree(records);
    expect(tree[0].count).toBe(2);
    expect(tree[0].truncatedCount).toBe(1);
    expect(tree[0].latestCreatedAt).toBe("2026-06-01T00:00:00Z");
  });

  it("aggregates thinkingCount per style", () => {
    const records = [
      rec({ category: "国語", style_id: "prose", mode: "thinking" }),
      rec({ category: "国語", style_id: "prose", mode: "nothinking" }),
      rec({ category: "国語", style_id: "prose", mode: "thinking" }),
    ];
    const tree = buildOutputsTree(records);
    expect(tree[0].styles[0].count).toBe(3);
    expect(tree[0].styles[0].thinkingCount).toBe(2);
  });

  it("sorts categories and styles by name", () => {
    const records = [
      rec({ category: "数学", style_id: "report" }),
      rec({ category: "国語", style_id: "dialog" }),
      rec({ category: "国語", style_id: "prose" }),
    ];
    const tree = buildOutputsTree(records);
    expect(tree.map((c) => c.category)).toEqual(["国語", "数学"]);
    expect(tree[0].styles.map((s) => s.styleId)).toEqual(["dialog", "prose"]);
  });

  it("includes records in style nodes", () => {
    const records = [
      rec({ category: "国語", style_id: "prose", prompt: "p1" }),
      rec({ category: "国語", style_id: "prose", prompt: "p2" }),
    ];
    const tree = buildOutputsTree(records);
    expect(tree[0].styles[0].records).toHaveLength(2);
    expect(tree[0].styles[0].records[0].prompt).toBe("p1");
  });

  it("resolves style label from STYLE_LABELS", () => {
    const records = [rec({ category: "国語", style_id: "prose" })];
    const tree = buildOutputsTree(records);
    expect(tree[0].styles[0].label).toBe("散文");
  });
});
