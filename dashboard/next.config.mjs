/** @type {import('next').NextConfig} */
const apiProxyTarget =
  process.env.JORYU_API_PROXY_TARGET || "http://127.0.0.1:8000";

const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/joryu-api/:path*",
        destination: `${apiProxyTarget}/:path*`,
      },
    ];
  },
};

export default nextConfig;
