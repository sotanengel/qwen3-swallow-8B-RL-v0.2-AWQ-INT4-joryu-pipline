import { describe, expect, it } from "vitest";

import { isSeedGenJobActive, parseSeedGenJobRecord, seedGenStatusLabel } from "./seed-gen-jobs";

describe("parseSeedGenJobRecord", () => {
  it("normalizes seed-gen job payload", () => {
    const row = parseSeedGenJobRecord({
      id: "abc",
      kind: "seed_gen",
      spec: {
        bank: "data/prompts/training_prompts.jsonl",
        domains_config: "src/joryu/seed_gen/domains.yaml",
        domain: "math",
        target_total: 1000,
        mode: "check",
        resume: true,
        sim_threshold: 0.9,
        batch_size: 4,
        config: "config.yaml",
      },
      status: "queued",
      created_at: "2026-01-01T00:00:00Z",
      started_at: null,
      finished_at: null,
      exit_code: null,
      error: null,
    });
    expect(row.kind).toBe("seed_gen");
    expect(row.spec.domain).toBe("math");
    expect(row.spec.mode).toBe("check");
    expect(row.spec.sim_threshold).toBe(0.9);
  });

  it("defaults mode to create when missing", () => {
    const row = parseSeedGenJobRecord({
      id: "def",
      kind: "seed_gen",
      spec: {},
      status: "queued",
      created_at: "2026-01-01T00:00:00Z",
      started_at: null,
      finished_at: null,
      exit_code: null,
      error: null,
    });
    expect(row.spec.mode).toBe("create");
  });
});

describe("seedGenStatusLabel", () => {
  it("maps running status", () => {
    expect(seedGenStatusLabel("running")).toBe("実行中");
  });
});

describe("isSeedGenJobActive", () => {
  it("returns true for queued and running", () => {
    expect(isSeedGenJobActive("queued")).toBe(true);
    expect(isSeedGenJobActive("running")).toBe(true);
    expect(isSeedGenJobActive("succeeded")).toBe(false);
  });
});
