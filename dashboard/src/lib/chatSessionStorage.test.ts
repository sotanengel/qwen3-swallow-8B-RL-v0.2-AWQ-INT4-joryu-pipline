// @vitest-environment jsdom

import { afterEach, describe, expect, it } from "vitest";

import {
  clearActiveSessionId,
  getActiveSessionId,
  setActiveSessionId,
} from "./chatSessionStorage";

afterEach(() => {
  localStorage.clear();
});

describe("chatSessionStorage", () => {
  it("stores and retrieves active session id", () => {
    expect(getActiveSessionId()).toBeNull();
    setActiveSessionId("abc-123");
    expect(getActiveSessionId()).toBe("abc-123");
    clearActiveSessionId();
    expect(getActiveSessionId()).toBeNull();
  });
});
