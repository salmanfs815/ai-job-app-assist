/// <reference types="vitest/config" />
import { resolve } from "node:path";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": resolve(import.meta.dirname, "src") },
  },
  build: {
    rollupOptions: {
      input: {
        main: resolve(import.meta.dirname, "index.html"),
        // MSAL v5 redirect bridge: a separate page that receives the sign-in response.
        redirect: resolve(import.meta.dirname, "redirect.html"),
      },
      output: {
        // Long-lived vendor chunks: app deploys do not invalidate the browser's cached libraries.
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (/[\\/]node_modules[\\/](react|react-dom|scheduler|react-router)[\\/]/.test(id)) return "vendor-react";
          if (/[\\/]node_modules[\\/](radix-ui|@radix-ui|sonner|lucide-react)[\\/]/.test(id)) return "vendor-ui";
          return undefined;
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
    css: false,
  },
});
