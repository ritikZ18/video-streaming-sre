/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // STATIC_EXPORT=1 (the Render viewer build) emits a fully static site to ./out
  // — no Node server, deployable as a Render Static Site. Unset locally so
  // `next start` / the Docker image keep the standard build. TMDB now proxies
  // through the backend (upload-api /api/v1/tmdb), so there are no server routes
  // to exclude — the Render build command no longer needs `rm -rf app/api`.
  output: process.env.STATIC_EXPORT === "1" ? "export" : undefined,
  env: {
    NEXT_PUBLIC_API_URL: process.env.VITE_API_URL || "http://localhost:8000",
    NEXT_PUBLIC_ORIGIN_URL: process.env.VITE_ORIGIN_URL || "http://localhost:8080",
    NEXT_PUBLIC_BEACON_URL: process.env.VITE_BEACON_URL || "http://localhost:8001",
    NEXT_PUBLIC_GRAFANA_URL: process.env.VITE_GRAFANA_URL || "http://localhost:3000",
    NEXT_PUBLIC_PROMETHEUS_URL:
      process.env.VITE_PROMETHEUS_URL || "http://localhost:9090",
    // "1" ships the public viewer build (browse + play only; admin/ops hidden).
    NEXT_PUBLIC_VIEWER_ONLY: process.env.NEXT_PUBLIC_VIEWER_ONLY || "",
  },
};

export default nextConfig;

