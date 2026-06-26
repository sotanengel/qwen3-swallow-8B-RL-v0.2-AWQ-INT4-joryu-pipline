import type { NextRequest } from "next/server";

import { buildProxyUrl, resolveApiTarget } from "@/lib/api-proxy";

export const dynamic = "force-dynamic";

type RouteCtx = { params: Promise<{ path: string[] }> };

const SSE_HEADERS: Record<string, string> = {
  "Cache-Control": "no-cache, no-transform",
  "X-Accel-Buffering": "no",
};

async function proxyRequest(req: NextRequest, pathSegments: string[]): Promise<Response> {
  const fullPath = ["api", "chat", ...pathSegments];
  const url = buildProxyUrl(resolveApiTarget(), fullPath, req.nextUrl.search);
  const headers = new Headers(req.headers);
  headers.delete("host");
  headers.delete("connection");

  const init: RequestInit & { duplex?: "half" } = {
    method: req.method,
    headers,
    cache: "no-store",
  };

  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = req.body;
    init.duplex = "half";
  }

  const upstream = await fetch(url, init);
  const outHeaders = new Headers(upstream.headers);
  if (upstream.headers.get("content-type")?.includes("text/event-stream")) {
    for (const [k, v] of Object.entries(SSE_HEADERS)) {
      outHeaders.set(k, v);
    }
  }
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: outHeaders,
  });
}

async function handle(req: NextRequest, ctx: RouteCtx): Promise<Response> {
  const { path } = await ctx.params;
  return proxyRequest(req, path);
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
