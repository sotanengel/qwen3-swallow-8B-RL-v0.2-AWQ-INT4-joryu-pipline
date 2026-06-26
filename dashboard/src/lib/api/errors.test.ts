import { describe, expect, it } from "vitest";

import { checkResponse, JobActiveError } from "./errors";

describe("checkResponse", () => {
  it("throws JobActiveError on 409", async () => {
    const res = new Response("conflict", { status: 409 });
    await expect(checkResponse(res)).rejects.toThrow(JobActiveError);
  });

  it("throws Error on other non-ok status", async () => {
    const res = new Response("bad", { status: 500 });
    await expect(checkResponse(res)).rejects.toThrow("API 500");
  });

  it("returns response on success", async () => {
    const res = new Response("{}", { status: 200 });
    const out = await checkResponse(res);
    expect(out).toBe(res);
  });
});
