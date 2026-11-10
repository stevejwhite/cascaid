import type { NextConfig } from "next";

const config: NextConfig = {
  poweredByHeader: false,
  experimental: { proxyTimeout: 275000 },
  async rewrites() {
    const base = process.env.API_BASE_URL ?? "http://127.0.0.1:8105";
    // Only the application API is proxied: /health and /ready stay reachable on loopback
    // alone. A request carrying the supervisor's internal header is never forwarded, so
    // that secret only works on the API's own loopback port.
    return [{
      source: "/backend/api/:path*",
      destination: `${base}/api/:path*`,
      missing: [{ type: "header", key: "x-cascaid-internal" }],
    }];
  },
};
export default config;
