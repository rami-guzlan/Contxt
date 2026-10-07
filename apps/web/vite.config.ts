import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const api = process.env.CONTXT_API ?? process.env.WORKSPACE_API ?? "http://127.0.0.1:8787";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": api,
      "/auth": api,
      "/mcp": api,
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
