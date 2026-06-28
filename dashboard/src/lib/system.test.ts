import { describe, expect, it } from "vitest";

import {
  EMPTY_SYSTEM_STATUS,
  formatSystemStatusLine,
  profileReady,
} from "./system";

describe("formatSystemStatusLine", () => {
  it("shows active distill ready", () => {
    const line = formatSystemStatusLine({
      ...EMPTY_SYSTEM_STATUS,
      status: "active",
      active: "distill",
      ready: true,
      profiles: [{ name: "distill", ready: true, port: 8100, service: "joryu", kind: "openai_v1" }],
    });
    expect(line).toBe("active=distill ready");
  });

  it("shows switching progress", () => {
    const line = formatSystemStatusLine({
      ...EMPTY_SYSTEM_STATUS,
      status: "switching",
      active: "distill",
      target: "seed_gen",
      progress: "waiting health 12s",
    });
    expect(line).toContain("switching distill→seed_gen");
  });
});

describe("profileReady", () => {
  it("returns ready flag for named profile", () => {
    const status = {
      ...EMPTY_SYSTEM_STATUS,
      profiles: [{ name: "seed_gen", ready: true, port: 8110, service: "joryu-seed", kind: "openai_v1" }],
    };
    expect(profileReady(status, "seed_gen")).toBe(true);
    expect(profileReady(status, "distill")).toBe(false);
  });
});
