import { afterEach, describe, expect, it } from "vitest";

import { buildProxyUrl, resolveApiTarget } from "./api-proxy";

describe("resolveApiTarget", () => {
  const env = process.env;

  afterEach(() => {
    process.env = env;
  });

  it("prefers JORYU_API_PROXY_TARGET", () => {
    process.env = { ...env, JORYU_API_PROXY_TARGET: "http://api:8000/" };
    expect(resolveApiTarget()).toBe("http://api:8000");
  });

  it("falls back to NEXT_PUBLIC_JORYU_API_URL then localhost", () => {
    process.env = { ...env, NEXT_PUBLIC_JORYU_API_URL: "http://localhost:9000" };
    delete process.env.JORYU_API_PROXY_TARGET;
    expect(resolveApiTarget()).toBe("http://localhost:9000");
  });

  it("defaults to localhost:8000", () => {
    process.env = { ...env };
    delete process.env.JORYU_API_PROXY_TARGET;
    delete process.env.NEXT_PUBLIC_JORYU_API_URL;
    expect(resolveApiTarget()).toBe("http://127.0.0.1:8000");
  });
});

describe("buildProxyUrl", () => {
  it("joins target, path segments, and query", () => {
    expect(
      buildProxyUrl("http://api:8000", ["api", "dashboard", "stats"], "?t=1"),
    ).toBe("http://api:8000/api/dashboard/stats?t=1");
  });
});
