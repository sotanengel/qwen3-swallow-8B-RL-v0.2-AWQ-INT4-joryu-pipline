import type { NextRequest } from "next/server";

import { buildProxyUrl, resolveApiTarget } from "@/lib/api-proxy";

export const dynamic = "force-dynamic";

type RouteCtx = { params: Promise<{ path: string[] }> };

async function proxyRequest(req: NextRequest, pathSegments: string[]): Promise<Response> {
  const url = buildProxyUrl(resolveApiTarget(), pathSegments, req.nextUrl.search);
  const headers = new Headers(req.headers);
  headers.delete("host");
  headers.delete("connection");

  const init: RequestInit = {
    method: req.method,
    headers,
    cache: "no-store",
  };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.arrayBuffer();
  }

  const upstream = await fetch(url, init);
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: upstream.headers,
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
