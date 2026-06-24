import { describe, expect, it } from "vitest";

const ADAPTIVE_FAST_MS = 1000;
const ADAPTIVE_DURATION_MS = 30_000;

/** useIntervalPoll と同じ interval 解決ロジック (テスト用)。 */
export function resolvePollIntervalMs(
  fastPoll: boolean,
  fastUntil: number,
  intervalMs: number,
  now: number,
): number {
  return fastPoll || now < fastUntil ? ADAPTIVE_FAST_MS : intervalMs;
}

describe("resolvePollIntervalMs", () => {
  it("uses fast interval when fastPoll is true", () => {
    expect(resolvePollIntervalMs(true, 0, 3000, 1000)).toBe(1000);
  });

  it("uses fast interval while adaptive window is active", () => {
    const now = 10_000;
    const fastUntil = now + ADAPTIVE_DURATION_MS - 1;
    expect(resolvePollIntervalMs(false, fastUntil, 3000, now)).toBe(1000);
  });

  it("uses base interval when not fast and adaptive window expired", () => {
    const now = 50_000;
    expect(resolvePollIntervalMs(false, 10_000, 3000, now)).toBe(3000);
  });
});
