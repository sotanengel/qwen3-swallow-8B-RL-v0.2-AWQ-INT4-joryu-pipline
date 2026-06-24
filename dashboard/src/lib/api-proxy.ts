/** Next.js dashboard → joryu-api ランタイムプロキシ (Docker compose 対応)。 */

export function resolveApiTarget(): string {
  const raw =
    process.env.JORYU_API_PROXY_TARGET ||
    process.env.NEXT_PUBLIC_JORYU_API_URL ||
    "http://127.0.0.1:8000";
  return raw.replace(/\/$/, "");
}

export function buildProxyUrl(
  target: string,
  pathSegments: string[],
  search: string,
): string {
  const path = pathSegments.map((segment) => encodeURIComponent(segment)).join("/");
  return `${target}/${path}${search}`;
}
