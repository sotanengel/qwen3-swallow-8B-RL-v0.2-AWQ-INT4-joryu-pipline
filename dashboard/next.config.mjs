/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  async redirects() {
    return [
      { source: "/jobs", destination: "/?stage=distill", permanent: true },
      { source: "/prompts", destination: "/?stage=prompts", permanent: true },
      { source: "/curation", destination: "/?stage=curate", permanent: true },
      { source: "/distributions", destination: "/stats?tab=distributions", permanent: true },
      { source: "/search", destination: "/outputs", permanent: true },
    ];
  },
};

export default nextConfig;
