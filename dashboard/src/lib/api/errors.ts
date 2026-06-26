export class JobActiveError extends Error {
  constructor() {
    super("job_active");
    this.name = "JobActiveError";
  }
}

export async function checkResponse(res: Response): Promise<Response> {
  if (res.status === 409) {
    throw new JobActiveError();
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res;
}
