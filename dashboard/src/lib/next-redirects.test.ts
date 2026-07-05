import { describe, expect, it } from "vitest";

async function loadRedirects(): Promise<Array<{ source: string; destination: string; permanent: boolean }>> {
  // @ts-expect-error - next.config.mjs is untyped
  const cfg = await import("../../next.config.mjs");
  const config = cfg.default as { redirects?: () => Promise<unknown[]> };
  if (typeof config.redirects !== "function") return [];
  return (await config.redirects()) as Array<{
    source: string;
    destination: string;
    permanent: boolean;
  }>;
}

describe("next.config.mjs redirects", () => {
  it("declares permanent redirects for legacy routes", async () => {
    const rules = await loadRedirects();
    const map = Object.fromEntries(rules.map((r) => [r.source, r]));
    expect(map["/jobs"]?.destination).toBe("/?stage=distill");
    expect(map["/prompts"]?.destination).toBe("/?stage=prompts");
    expect(map["/curation"]?.destination).toBe("/?stage=curate");
    expect(map["/distributions"]?.destination).toBe("/stats?tab=distributions");
    expect(map["/search"]?.destination).toBe("/outputs");
    for (const key of ["/jobs", "/prompts", "/curation", "/distributions", "/search"]) {
      expect(map[key]?.permanent).toBe(true);
    }
    expect(map["/screening"]).toBeUndefined();
  });
});
