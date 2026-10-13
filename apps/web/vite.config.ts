import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The built control panel is served by the API process itself (single origin → strict CSP, no CORS).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/v1": { target: "http://127.0.0.1:8000", changeOrigin: false } },
  },
  build: {
    outDir: "../api/nis/static",
    emptyOutDir: true,
    chunkSizeWarningLimit: 900,
  },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
} as never);
