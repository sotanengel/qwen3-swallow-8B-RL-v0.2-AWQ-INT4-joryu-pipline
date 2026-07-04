export class JobActiveError extends Error {
  constructor() {
    super("job_active");
    this.name = "JobActiveError";
  }
}

export class WrongProfileError extends Error {
  readonly detail: Record<string, unknown>;

  constructor(detail: Record<string, unknown>) {
    super("wrong_profile");
    this.name = "WrongProfileError";
    this.detail = detail;
  }
}

export class ProfileSwitchingError extends Error {
  readonly detail: Record<string, unknown>;

  constructor(detail: Record<string, unknown>) {
    super("profile_switching");
    this.name = "ProfileSwitchingError";
    this.detail = detail;
  }
}

async function readConflictDetail(res: Response): Promise<Record<string, unknown> | null> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (body.detail && typeof body.detail === "object" && !Array.isArray(body.detail)) {
      return body.detail as Record<string, unknown>;
    }
  } catch {
    /* ignore */
  }
  return null;
}

export async function checkResponse(res: Response): Promise<Response> {
  if (res.status === 409) {
    const detail = await readConflictDetail(res);
    const error = detail?.error;
    if (error === "wrong_profile" || error === "profile_starting") {
      throw new WrongProfileError(detail ?? { error });
    }
    if (error === "profile_switching") {
      throw new ProfileSwitchingError(detail ?? { error });
    }
    if (error === "job_active") {
      throw new JobActiveError();
    }
    throw new JobActiveError();
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res;
}
