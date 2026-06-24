import { readFile } from "fs/promises";
import path from "path";

export const dynamic = "force-dynamic";

const NO_STORE = {
  "Cache-Control": "no-store, no-cache, must-revalidate",
};

export async function GET() {
  const filePath = path.join(process.cwd(), "public", "responses.jsonl");
  try {
    const text = await readFile(filePath, "utf-8");
    return new Response(text, {
      headers: {
        "Content-Type": "application/x-ndjson",
        ...NO_STORE,
      },
    });
  } catch {
    return new Response("", { headers: NO_STORE });
  }
}
