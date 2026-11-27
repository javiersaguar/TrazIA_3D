import type { NextConfig } from "next";

const apiOrigin = process.env.TRAZIA_API_ORIGIN?.trim().replace(/\/+$/, "");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  devIndicators: false,
  experimental: {
    optimizePackageImports: ["lucide-react", "@radix-ui/react-tooltip"],
    // Match the catalogue's 25 MiB file limit plus the multipart envelope.
    ...(apiOrigin ? { proxyClientMaxBodySize: 26 * 1024 ** 2 } : {}),
  },
  async rewrites() {
    // Vercel routes directly to FastAPI at the edge, including multipart uploads.
    return apiOrigin && process.env.VERCEL !== "1"
      ? [{ source: "/api/trazia/:path*", destination: `${apiOrigin}/:path*` }]
      : [];
  },
};

export default nextConfig;
