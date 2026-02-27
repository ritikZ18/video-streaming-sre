/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    appDir: true,
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.VITE_API_URL || "http://localhost:8000",
    NEXT_PUBLIC_ORIGIN_URL: process.env.VITE_ORIGIN_URL || "http://localhost:8080",
    NEXT_PUBLIC_BEACON_URL: process.env.VITE_BEACON_URL || "http://localhost:8001",
    NEXT_PUBLIC_GRAFANA_URL: process.env.VITE_GRAFANA_URL || "http://localhost:3000",
    NEXT_PUBLIC_PROMETHEUS_URL:
      process.env.VITE_PROMETHEUS_URL || "http://localhost:9090",
  },
};

export default nextConfig;

