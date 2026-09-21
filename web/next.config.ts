import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  images: {
    unoptimized: true,
  },
  // Widened so Turbopack can resolve ../../shared/sql-guard, the module
  // shared between this app and worker/ (see PLAN.md's "shared TypeScript
  // module used by both the Worker and the browser"). Without this,
  // Turbopack refuses to resolve any import outside web/.
  turbopack: {
    root: path.join(__dirname, ".."),
  },
};

export default nextConfig;
