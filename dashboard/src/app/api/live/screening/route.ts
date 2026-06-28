import { readFile } from "fs/promises";
import path from "path";

export const dynamic = "force-dynamic";

const NO_STORE = {
  "Cache-Control": "no-store, no-cache, must-revalidate",
};

const EMPTY = {
  total: 0,
  label_distribution: {},
  rule_violation_rates: {},
  llm_health_averages: {},
  llm_health_count: 0,
  evaluator_models: {},
  judge_comparison: null,
};

export async function GET() {
  const filePath = path.join(process.cwd(), "public", "screening.json");
  try {
    const text = await readFile(filePath, "utf-8");
    return new Response(text, {
      headers: { "Content-Type": "application/json", ...NO_STORE },
    });
  } catch {
    return Response.json(EMPTY, { headers: NO_STORE, status: 404 });
  }
}
