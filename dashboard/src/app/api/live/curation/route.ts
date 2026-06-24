import { readFile } from "fs/promises";
import path from "path";

export const dynamic = "force-dynamic";

const NO_STORE = {
  "Cache-Control": "no-store, no-cache, must-revalidate",
};

export async function GET() {
  const filePath = path.join(process.cwd(), "public", "curation.json");
  try {
    const text = await readFile(filePath, "utf-8");
    return new Response(text, {
      headers: { "Content-Type": "application/json", ...NO_STORE },
    });
  } catch {
    return Response.json({ total: 0, accepted: 0 }, { headers: NO_STORE });
  }
}
