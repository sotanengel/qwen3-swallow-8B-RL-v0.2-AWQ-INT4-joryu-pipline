import { describe, expect, it } from "vitest";

import {
  checkResponse,
  JobActiveError,
  ProfileSwitchingError,
  WrongProfileError,
} from "./errors";

describe("checkResponse", () => {
  it("throws JobActiveError on job_active 409", async () => {
    const res = new Response(
      JSON.stringify({ detail: { error: "job_active", running_id: "x" } }),
      { status: 409, headers: { "Content-Type": "application/json" } },
    );
    await expect(checkResponse(res)).rejects.toThrow(JobActiveError);
  });

  it("throws WrongProfileError on wrong_profile 409", async () => {
    const res = new Response(
      JSON.stringify({ detail: { error: "wrong_profile", required: "distill" } }),
      { status: 409, headers: { "Content-Type": "application/json" } },
    );
    await expect(checkResponse(res)).rejects.toThrow(WrongProfileError);
  });

  it("throws ProfileSwitchingError on profile_switching 409", async () => {
    const res = new Response(
      JSON.stringify({ detail: { error: "profile_switching", target: "distill" } }),
      { status: 409, headers: { "Content-Type": "application/json" } },
    );
    await expect(checkResponse(res)).rejects.toThrow(ProfileSwitchingError);
  });

  it("falls back to JobActiveError on unknown 409", async () => {
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
